/*
Copyright (c) 2013, Intel Corporation
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of Intel Corporation nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

#include <grub/cpu/io.h>
#include <grub/misc.h>

#include "barrier.h"
#include "portable.h"
#include "smprc.h"
#include "smpasm.h"
#include "smpequ.h"

#include "acpica.h"

#define MAX_STACK_SIZE 512

// Memory-mapped APIC Offsets
#define APIC_LOCAL_APIC_ID 0x020
#define APIC_EOI 0xB0
#define APIC_ICR_LO 0x300
#define APIC_ICR_HI 0x310
#define APIC_TMR_LVT 0x320
#define APIC_LINT0_LVT 0x350
#define APIC_TMR_INITIAL_CNT 0x380
#define APIC_TMR_CURRENT_CNT 0x390
#define APIC_TMR_DIVIDE_CFG 0x3E0

#define MSR_APIC_BASE 0x1B
#define MSR_EXT_XAPIC_LOGICAL_APIC_ID 0x802
#define MSR_APIC_EOI 0x80B
#define MSR_EXT_XAPIC_ICR 0x830
#define MSR_APIC_TMR_LVT 0x832
#define MSR_APIC_LINT0_LVT 0x835
#define MSR_APIC_TMR_INITIAL_CNT 0x838
#define MSR_APIC_TMR_CURRENT_CNT 0x839
#define MSR_APIC_TMR_DIVIDE_CFG 0x83E

typedef struct cpu_data {
    U32 stack[MAX_STACK_SIZE];
    U32 use_mwait;
    U32 mwait_hint;
    U32 int_break_event;
    U32 status;
    CALLBACK function;
    void *param;
} CPU_DATA;

struct gate {
    U16 offset_15_0;
    U16 selector;
    U16 flags;
    U16 offset_31_16;
#ifdef GRUB_TARGET_CPU_X86_64
    U32 offset_63_32;
    U32 reserved;
#endif
};

static const struct gate EMPTY_GATE;

typedef struct idtr {
    U16 limit;
    struct gate *base;
} attr_packed IDTR;

typedef struct exception_info {
    U16 gpf_idtr_installed;
    IDTR idt_descriptor;
    struct gate idt_table[0x40];
} EXCEPTION_INFO;

#define SMP_MAGIC 0x69534D50

typedef struct smp_host {
    U32 initialized;
    void *mem_region_below_1M;
    U32 logical_processor_count;
    U32 expected_processor_count;
    U32 bclk;
    EXCEPTION_INFO bsp_exception_info;
    EXCEPTION_INFO ap_exception_info;
    asmlinkage void (*wait_for_control)(U32 *, U32, U32, U32, U32);
    U8 *control;
    CPU_INFO cpu[SMP_MAX_LOGICAL_CPU];
    CPU_DATA cpu_data[SMP_MAX_LOGICAL_CPU];
    U8 control_region[SMP_MWAIT_ALIGN * SMP_MAX_LOGICAL_CPU + SMP_MWAIT_ALIGN];
} SMP_HOST;

static void read_apicid(void *param);
static asmlinkage void find_logical_processors(void *param) attr_noreturn;
static asmlinkage void mp_worker(void *param) attr_noreturn;
static void prepare_mp_worker(void *param) attr_noreturn;
static void ap_park(void *param);

static U32 find_processor_id_for_this_cpu(U32 * processor_id, SMP_HOST * host);
static U32 find_processor_id_for_this_apicid(U32 apicid, U32 * processor_id, SMP_HOST * host);

static const IDTR real_mode_idtr = { .limit = 0x3ff, .base = 0 };

#ifdef GRUB_TARGET_CPU_X86_64
static U64 get_cr3(void)
{
    U64 ret;
    __asm__ __volatile__ ("mov %%cr3, %[ret]" : [ret] "=r" (ret));
    return ret;
}
#endif

static void InitSipiCode(void *output_address, void *function, void *param)
{
    // Move SIPI code below 1M
    memcpy(output_address, pm32, pm32_size);

    *(volatile void **)((char *)output_address + FUNCTIONPTR) = function;
    *(volatile void **)((char *)output_address + PARAM) = param;
    *(volatile U32 *)((char *)output_address + BLOCK) = 0;
    *(volatile U32 *)((char *)output_address + ASLEEP) = 0;
#ifdef GRUB_TARGET_CPU_X86_64
    *(volatile U32 *)((char *)output_address + PAGETABLE) = (U32)get_cr3();
#endif
}

static void get_idtr(IDTR *idt)
{
    __asm__ __volatile__ ("sidt %[idt]" : [idt] "=m" (*idt));
}

static void set_idtr(const IDTR *idt)
{
    __asm__ __volatile__ ("lidt %[idt]" : : [idt] "m" (*idt));
}

static U16 my_cs(void)
{
    U16 ret;
    __asm__ __volatile__ ("mov %%cs, %[ret]" : [ret] "=g" (ret));
    return ret;
}

static void *get_gate_offset(struct gate *gate)
{
    return (void *)(
#ifdef GRUB_TARGET_CPU_X86_64
        ((unsigned long)gate->offset_63_32 << 32) |
#endif
        ((unsigned long)gate->offset_31_16 << 16) | gate->offset_15_0);
}

static void set_gate_offset(struct gate *gate, void *offset)
{
    gate->offset_15_0 = (U16)(unsigned long)offset;
    gate->offset_31_16 = (U16)((unsigned long)offset >> 16);
#ifdef GRUB_TARGET_CPU_X86_64
    gate->offset_63_32 = (U32)((unsigned long)offset >> 32);
#endif
}

static void get_gate(unsigned gate_number, struct gate *gate)
{
    IDTR idt;
    get_idtr(&idt);
    memcpy(gate, &idt.base[gate_number], sizeof(*gate));
}

static void set_gate(unsigned gate_number, const struct gate *gate)
{
    IDTR idt;
    get_idtr(&idt);
    memcpy(&idt.base[gate_number], gate, sizeof(*gate));
}

static void set_protected_mode_exception_handler(unsigned gate_number, void *handler)
{
    struct gate gate;
    gate.selector = my_cs();
    gate.flags = 0x8e00; /* interrupt gate */
    set_gate_offset(&gate, handler);
    set_gate(gate_number, &gate);
}

void cpuid32(U32 func, U32 *eax, U32 *ebx, U32 *ecx, U32 *edx)
{
    __asm__ __volatile__ ("cpuid" : "=a" (*eax), "=b" (*ebx), "=c" (*ecx), "=d" (*edx) : "0" (func));
}

void cpuid32_indexed(U32 func, U32 index, U32 *eax, U32 *ebx, U32 *ecx, U32 *edx)
{
    __asm__ __volatile__ ("cpuid" : "=a" (*eax), "=b" (*ebx), "=c" (*ecx), "=d" (*edx) : "0" (func), "2" (index));
}

static inline U8 input_u8(U16 port)
{
    U8 ret;
    __asm__ __volatile__ ("inb %[port], %[ret]" : [ret] "=a" (ret) : [port] "Nd" (port));
    return ret;
}

static inline void output_u8(U16 port, U8 val)
{
    __asm__ __volatile__ ("outb %[val], %[port]" : : [val] "a" (val), [port] "Nd" (port));
}

static void rdmsr32(U32 msr, U32 *lo_data_addr, U32 *hi_data_addr, U32 *status)
{
    __asm__ __volatile__ (
        "jmp 0f\n"
        ".long 0x58475046 # 'XGPF'\n"
        ".long 1f - 0f # offset to trap to\n"
        "0:\n"
        "rdmsr\n"
        "movl $0, %[status]\n"
        "jmp 2f\n"
        "1:\n"
        "movl $-1, %[status]\n"
        "2:\n"
        : "=&a" (*lo_data_addr), "=&d" (*hi_data_addr), [status] "=&g" (*status) : "c" (msr));
}

void rdmsr64(U32 msr, U64 * data_addr, U32 * status)
{
    U32 lo_data, hi_data;

    rdmsr32(msr, &lo_data, &hi_data, status);
    *data_addr = ((U64) hi_data << 32) + lo_data;
}

asmlinkage U64 rdtsc64(void)
{
    U32 lo_data, hi_data;

    __asm__ __volatile__ ("rdtsc" : "=a" (lo_data), "=d" (hi_data));
    return ((U64) hi_data << 32) + lo_data;
}

static void wrmsr32(U32 msr, U32 lo_data, U32 hi_data, U32 *status)
{
    __asm__ __volatile__ (
        "jmp 0f\n"
        ".long 0x58475046 # 'XGPF'\n"
        ".long 1f - 0f # offset to trap to\n"
        "0:\n"
        "wrmsr\n"
        "movl $0, %[status]\n"
        "jmp 2f\n"
        "1:\n"
        "movl $-1, %[status]\n"
        "2:\n"
        : [status] "=g" (*status) : "a" (lo_data), "d" (hi_data), "c" (msr));
}

void wrmsr64(U32 msr, U64 data, U32 * status)
{
    wrmsr32(msr, (U32) data, (U32) (data >> 32), status);
}

#define MAKE_CR(n) \
void read_cr ## n(unsigned long *data, U32 *status) \
{ \
    __asm__ __volatile__ ( \
        "jmp 0f\n" \
        ".long 0x58475046 # 'XGPF'\n" \
        ".long 1f - 0f # offset to trap to\n" \
        "0:\n" \
        "mov %%cr" #n ", %[data]\n" \
        "movl $0, %[status]\n" \
        "jmp 2f\n" \
        "1:\n" \
        "movl $-1, %[status]\n" \
        "2:\n" \
        : [data] "=r" (*data), [status] "=g" (*status)); \
} \
void write_cr ## n(unsigned long data, U32 *status) \
{ \
    __asm__ __volatile__ ( \
        "jmp 0f\n" \
        ".long 0x58475046 # 'XGPF'\n" \
        ".long 1f - 0f # offset to trap to\n" \
        "0:\n" \
        "mov %[data], %%cr" #n "\n" \
        "movl $0, %[status]\n" \
        "jmp 2f\n" \
        "1:\n" \
        "movl $-1, %[status]\n" \
        "2:\n" \
        : [status] "=g" (*status) : [data] "r" (data)); \
}

MAKE_CR(0)
MAKE_CR(2)
MAKE_CR(3)
MAKE_CR(4)
#ifdef GRUB_TARGET_CPU_X86_64
MAKE_CR(8)
#endif

static void drop_ap_lock(void *output_addr)
{
    __asm__ __volatile__ (
        "lock incl %[asleep]\n"
        "xorl %%eax, %%eax\n"
        "xchgl %%eax, %[block]\n"
        : [asleep] "=m" (*(U32 *)((unsigned long)output_addr + ASLEEP)),
          [block]  "=m" (*(U32 *)((unsigned long)output_addr + BLOCK))
        : : "eax", "memory", "cc");
}

static U32 x2apic_enabled(void)
{
    U64 temp64;
    U32 status;

    rdmsr64(MSR_APIC_BASE, &temp64, &status);

    return (U32) (temp64 & (1 << 10)) ? 1 : 0;
}

static U32 get_apicbase(void)
{
    U64 temp64;
    U32 status;

    rdmsr64(MSR_APIC_BASE, &temp64, &status);

    return (U32) (temp64 & 0xfffff000);
}

static void send_apicmsg(U32 msgdata, U32 apicid)
{
    U32 ICRHigh = 0;
    U32 ICRLow = 0;

    if (x2apic_enabled()) {
        U32 status;

        ICRHigh = apicid;
        ICRLow = msgdata;
        wrmsr32(MSR_EXT_XAPIC_ICR, ICRLow, ICRHigh, &status);
    } else {
        unsigned long ApicBase = get_apicbase();

        ICRHigh = apicid << 24;
        ICRLow = msgdata;

        *(volatile U32 *)(ApicBase + APIC_ICR_HI) = ICRHigh;
        *(volatile U32 *)(ApicBase + APIC_ICR_LO) = ICRLow;
    }

    return;
}

static U32 get_apic_ICRLow(void)
{
    if (x2apic_enabled()) {
        U64 temp64;
        U32 status;
        rdmsr64(MSR_EXT_XAPIC_ICR, &temp64, &status);
        return (U32) temp64;
    } else {
        return *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_ICR_LO);
    }
}

static void send_apic_eoi(void)
{
    U32 status;
    if (x2apic_enabled())
        wrmsr32(MSR_APIC_EOI, 0, 0, &status);
    else
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_EOI) = 0;
}

static void setup_apic(bool mask, U8 vector)
{
    U32 status;
    U32 lvt = (mask ? 1 << 16 : 0) | vector;
    if (x2apic_enabled())
        wrmsr32(MSR_APIC_TMR_LVT, lvt, 0, &status);
    else
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_LVT) = lvt;
}

static bool mask_lint0(bool mask)
{
    bool oldmask;
    U32 val, dummy;

    if (x2apic_enabled())
        rdmsr32(MSR_APIC_LINT0_LVT, &val, &dummy, &dummy);
    else
        val = *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_LINT0_LVT);
    oldmask = (val >> 16) & 1;
    val &= ~(1 << 16);
    val |= ((U32) mask) << 16;
    if (x2apic_enabled())
        wrmsr32(MSR_APIC_LINT0_LVT, val, 0, &dummy);
    else
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_LINT0_LVT) = val;
    return oldmask;
}

//-----------------------------------------------------------------------------
static void start_apic_timer(struct smp_host *host, U32 timeout_in_usecs)
{
    // APIC Timer runs at bclk MHz and by default decrements
    // the current count register at once per two clocks.
    // t = time in milliseconds
    // c = APIC Timer Initial Value
    // c = (t * 10^(-6) sec) * (bclk * 10^6 count/sec) * (1/2 clocks)
    // Notice seconds and exponents cancel out leaving count value
    // c = (t * bclk / 2)

    // Prepare to use APIC Timer
    // 1. Get APIC memory base address
    // 2. Start APIC Timer by writing inital count register
    // 3. Set APIC memory base address + APIC_TMR_INITIAL_CNT
    //    as the time in usecs * APIC timer rate / 2

    U32 status;

    if (x2apic_enabled())
        wrmsr32(MSR_APIC_TMR_INITIAL_CNT, (U32) (timeout_in_usecs * host->bclk / 2), 0, &status);
    else
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_INITIAL_CNT) = timeout_in_usecs * host->bclk / 2;

    return;
}

//-----------------------------------------------------------------------------
static U32 get_apic_timer(void)
{
    if (x2apic_enabled()) {
        U32 status, temp32, dummy;
        rdmsr32(MSR_APIC_TMR_CURRENT_CNT, &temp32, &dummy, &status);
        return temp32;
    } else
        return (*(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_CURRENT_CNT));
}

static void send_broadcast_init(struct smp_host *host)
{
    U32 temp32;
    U32 saved_cnt;
    U32 current_cnt;

    // Send the INIT assert
    temp32 = (3ul << 18) | // All excluding self
             (1ul << 14) | // LEVEL is 1
             (5ul << 8);   // INIT

    send_apicmsg(temp32, (U32) 0xff);

    if (!x2apic_enabled()) {
        // start timer 20us
        start_apic_timer(host, 20);

        // while send is still pending and timeout not expired
        saved_cnt = get_apic_timer();
        do  {
            current_cnt = get_apic_timer();
        } while ((get_apic_ICRLow() & (1ul << 12)) && current_cnt && (current_cnt <= saved_cnt));
    }

    // Send the INIT de-assert
    temp32 = (3ul << 18) | // All excluding self
             (1ul << 15) | // TRIGGER is 1
             (5ul << 8);   // INIT

    send_apicmsg(temp32, (U32) 0xff);

    if (!x2apic_enabled()) {
        // start timer 20us
        start_apic_timer(host, 20);

        saved_cnt = get_apic_timer();

        // while send is still pending and timeout not expired
        do  {
            current_cnt = get_apic_timer();
        } while ((get_apic_ICRLow() & (1 << 12)) && current_cnt && (current_cnt <= saved_cnt));
    }

    // wait for 10ms for INIT processing to complete
    //start timer 10ms
    start_apic_timer(host, 10000);
    saved_cnt = get_apic_timer();
    do  {
        current_cnt = get_apic_timer();
    } while (current_cnt && (current_cnt <= saved_cnt));

    return;
}

static void send_broadcast_sipi(struct smp_host *host, void *addr)
{
    U32 temp32;
    U32 saved_cnt;
    U32 current_cnt;

    // Send the SIPI
    temp32 = (3ul << 18) | // All excluding self
             (1ul << 14) | // LEVEL is 1
             (6ul << 8);   // SIPI
    temp32 |= ((unsigned long)addr >> 12) & 0xff;
    send_apicmsg(temp32, (U32) 0xff);

    if (!x2apic_enabled()) {
        // start timer 20us
        start_apic_timer(host, 20);
        saved_cnt = get_apic_timer();

        // While send is still pending or timeout not expired
        do  {
            current_cnt = get_apic_timer();
        } while ((get_apic_ICRLow() & (1ul << 12)) && current_cnt && (current_cnt <= saved_cnt));
    }

    // While timeout not expired
    // start timer 20us
    start_apic_timer(host, 20);
    saved_cnt = get_apic_timer();
    do  {
        current_cnt = get_apic_timer();
    } while (current_cnt && (current_cnt <= saved_cnt));

    // Send it again (MP Spec 1.4 requirement)
    send_apicmsg(temp32, (U32) 0xff);

    if (!x2apic_enabled()) {
        // start timer 20us
        start_apic_timer(host, 20);

        saved_cnt = get_apic_timer();

        // While send is still pending and timeout not expired
        do  {
            current_cnt = get_apic_timer();
        } while ((get_apic_ICRLow() & (1ul << 12)) && current_cnt && (current_cnt <= saved_cnt));
    }

    return;
}

static U32 apic_enabled(void)
{
    U64 temp64;
    U32 status;

    rdmsr64(MSR_APIC_BASE, &temp64, &status);

    return (U32) (temp64 & (1 << 11)) ? 1 : 0;
}

static inline void pause32(void)
{
    __asm__ __volatile__ ("pause");
}

//-----------------------------------------------------------------------------
static U32 do_callback(struct smp_host *host, ASM_CALLBACK function, void *param)
{
    char *addr;
    U32 thread_count = host->expected_processor_count;

    if (!apic_enabled()) {
        dprintf("smp", "APIC is not enabled, returning 1 as status\n");
        return 1;
    }

    addr = host->mem_region_below_1M;

    if (thread_count == 1)
        return 1;

    InitSipiCode(addr, function, param);
    send_broadcast_init(host);
    send_broadcast_sipi(host, addr);

    thread_count--; // We already have the BSP

    // We already know how many processors we have, so wait for that many to check in.
    while (*(volatile U32 *)(addr + ASLEEP) != thread_count)
        pause32();

    return (1);
}

//-----------------------------------------------------------------------------
void read_apicid(void *param)
{
    // Find the APIC ID
    if (x2apic_enabled()) {
        U64 temp64;
        U32 status;

        rdmsr64(MSR_EXT_XAPIC_LOGICAL_APIC_ID, &temp64, &status);
        *(U32 *) param = (U32) temp64;
    } else if (apic_enabled()) {
        *(U32 *) param = (*(volatile U32 *)(unsigned long)(get_apicbase() + APIC_LOCAL_APIC_ID)) >> 24;
    } else {
        U32 dummy;
        U32 ebx;
        cpuid32(1, &dummy, &ebx, &dummy, &dummy);
        *(U32 *) param = ebx >> 24;
    }
}

static void init_bsp_exception_handling(struct smp_host *host)
{
    struct exception_info *e = &host->bsp_exception_info;
    IDTR idt;
    get_idtr(&idt);

    // If the IDT base is zero, then a real mode IDT is still in use
    if (idt.base == 0) {
        // Create blank protected mode IDT and a descriptor that points to it
        memset(e->idt_table, 0, sizeof(e->idt_table));
        e->idt_descriptor.limit = sizeof(e->idt_table) - 1;
        e->idt_descriptor.base = e->idt_table;

        dprintf("smp", "new IDT base: %p new IDT Limit: %04x\n", e->idt_descriptor.base, e->idt_descriptor.limit);

        dprintf("smp", "IDT base: %p IDT Limit: %04x\n", idt.base, idt.limit);

        set_idtr(&e->idt_descriptor);
        set_protected_mode_exception_handler(0xd, gpfHandler);
        set_idtr(&real_mode_idtr);
        e->gpf_idtr_installed = 1;
    }
}

static void init_ap_exception_handling(struct smp_host *host)
{
    struct exception_info *e = &host->ap_exception_info;

    if (!e->gpf_idtr_installed) {
        // Create blank protected mode IDT and a descriptor that points to it
        memset(e->idt_table, 0, sizeof(e->idt_table));
        e->idt_descriptor.limit = sizeof(e->idt_table) - 1;
        e->idt_descriptor.base = e->idt_table;

        // Setup a blank protected mode IDT for use on the AP
        set_idtr(&e->idt_descriptor);
        set_protected_mode_exception_handler(0xd, gpfHandler);
        e->gpf_idtr_installed = 1;
    } else
        set_idtr(&e->idt_descriptor);
}

//-----------------------------------------------------------------------------
asmlinkage void find_logical_processors(void *param)
{
    SMP_HOST *host = param;
    U32 processor_id = 0;

    init_ap_exception_handling(host);

    if (host->logical_processor_count == host->expected_processor_count)
        while (1) {
        }

    processor_id = host->logical_processor_count++;
    read_apicid(&host->cpu[processor_id].apicid);

    host->cpu[processor_id].present = 1;

    prepare_mp_worker(param);
}

static bool mwait_supported(void)
{
    U32 eax, ecx, dummy;
    cpuid32(0, &eax, &dummy, &dummy, &dummy);
    if (eax < 5)
        return false;
    cpuid32(1, &dummy, &dummy, &ecx, &dummy);
    if (!(ecx & (1 << 3)))
        return false;
    return true;
}

static bool int_break_event_supported(void)
{
    U32 ecx, dummy;
    if (!mwait_supported())
        return false;
    cpuid32(5, &dummy, &dummy, &ecx, &dummy);
    return ecx & (1 << 1) ? true : false;
}

bool smp_get_mwait_with_memory(void *working_memory, U32 apicid, bool *use_mwait, U32 *mwait_hint, U32 *int_break_event)
{
    U32 processor_id;
    CPU_DATA *cpu_data;

    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC)
        return false;

    if (find_processor_id_for_this_apicid(apicid, &processor_id, host) == 0)
        return false;

    cpu_data = &host->cpu_data[processor_id];

    *use_mwait = cpu_data->use_mwait;
    *mwait_hint = cpu_data->mwait_hint;
    *int_break_event = cpu_data->int_break_event;

    return true;
}

void smp_set_mwait_with_memory(void *working_memory, U32 apicid, bool use_mwait, U32 mwait_hint, U32 int_break_event)
{
    U32 processor_id;
    CPU_DATA *cpu_data;

    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC)
        return;

    if (find_processor_id_for_this_apicid(apicid, &processor_id, host) == 0)
        return;

    cpu_data = &host->cpu_data[processor_id];

    cpu_data->use_mwait = use_mwait;
    cpu_data->mwait_hint = mwait_hint;
    cpu_data->int_break_event = int_break_event;
}

//-----------------------------------------------------------------------------
asmlinkage void mp_worker(void *param)
{
    SMP_HOST *host = param;
    U32 processor_id = 0;
    U32 *my_control;
    CPU_DATA *cpu_data;

    drop_ap_lock(host->mem_region_below_1M);

    if (find_processor_id_for_this_cpu(&processor_id, host) == 0)
        for (;;)
            pause32();

    cpu_data = &host->cpu_data[processor_id];
    my_control = (U32 *) (host->control + processor_id * SMP_MWAIT_ALIGN);

    for (;;) {
        /* Detect the ability to use mwait every time, just in case the function does something to disable it. */
        host->wait_for_control(my_control, AP_IN_CONTROL,
                               cpu_data->use_mwait && mwait_supported(), cpu_data->mwait_hint,
                               cpu_data->int_break_event && int_break_event_supported());

        // Do assigned function
        cpu_data->function(cpu_data->param);

        // Save results, modify flags, etc is done by the function

        set_control(my_control, BSP_IN_CONTROL);
    }
}

//-----------------------------------------------------------------------------
void prepare_mp_worker(void *param)
{
    SMP_HOST *host = param;
    U32 processor_id = 0;
    CPU_DATA *cpu_data;
    void *stack_top;

    if (find_processor_id_for_this_cpu(&processor_id, host) == 0)
        for (;;)
            pause32();

    cpu_data = &host->cpu_data[processor_id];

    cpu_data->status = 1;

    // Switch stacks
    stack_top = &host->cpu_data[processor_id].stack[MAX_STACK_SIZE];

    switch_stack_and_call(mp_worker, param, stack_top);
}

//-----------------------------------------------------------------------------
U32 find_processor_id_for_this_apicid(U32 apicid, U32 * processor_id, SMP_HOST * host)
{
    U32 i;

    for (i = 0; i < host->logical_processor_count; i++)
        if (host->cpu[i].apicid == apicid) {
            *processor_id = i;
            return 1;
        }

    return 0;
}

//-----------------------------------------------------------------------------
U32 find_processor_id_for_this_cpu(U32 * processor_id, SMP_HOST * host)
{
    U32 apicid;

    read_apicid(&apicid);

    return find_processor_id_for_this_apicid(apicid, processor_id, host);
}

//-----------------------------------------------------------------------------
void ap_park(void *param)
{
    (void)param;
}

static U32 process_madt(struct acpi_table_madt *madt)
{
    U32 count = 0;
    void *current;
    void *end;

    // Search MADT for Sub-tables with needed data
    current = madt + 1;
    end = (U8 *) madt + madt->Header.Length;

    while (current < end) {
        struct acpi_subtable_header *subtable = current;

        switch (subtable->Type) {
        case ACPI_MADT_TYPE_LOCAL_APIC:
            {
                // Process sub-tables with Type as 0: Processor Local APIC
                struct acpi_madt_local_apic *lapic = current;
                if (lapic->LapicFlags & ACPI_MADT_ENABLED)
                    count++;
                break;
            }
        case ACPI_MADT_TYPE_LOCAL_X2APIC:
            {
                // Process sub-tables with Type as 9: Processor X2APIC
                struct acpi_madt_local_x2apic *x2apic = current;
                if (x2apic->LapicFlags & ACPI_MADT_ENABLED)
                    count++;
                break;
            }
        } // switch

        current = (U8 *) subtable + subtable->Length;
    } // while

    return count;
}

static U32 madt_processor_count(void)
{
    struct acpi_table_madt *madt;

    if (!acpica_early_init())
        return GRUB_ERR_IO;

    if (AcpiGetTable((char *)"APIC", 1, (ACPI_TABLE_HEADER **)&madt) != AE_OK)
        return GRUB_ERR_IO;

    return process_madt(madt);
}

static U32 compute_bclk(void)
{
    U32 status, dummy;
    U32 start, stop;
    U8 temp8;
    U16 delay_count;
    U32 bclk;

#define DELAY_IN_US 1000

    // Compute fixed delay as time
    // delay count = desired time * PIT frequency
    // PIT frequency = 1.193182 MHz
    delay_count = 1193182 / DELAY_IN_US;

    // PIT channel 2 gate is controlled by IO port 0x61, bit 0
#define PIT_CH2_LATCH_REG 0x61
#define CH2_SPEAKER (1 << 1) // bit 1 -- 1 = speaker enabled 0 = speaker disabled
#define CH2_GATE_IN (1 << 0) // bit 0 -- 1 = gate enabled, 0 = gate disabled
#define CH2_GATE_OUT (1 << 5) // bit 5 -- 1 = gate latched, 0 = gate not latched

    // PIT Command register
#define PIT_MODE_COMMAND_REG 0x43
#define SELECT_CH2 (2 << 6)
#define ACCESS_MODE_LOBYTE_HIBYTE (3 << 4)
#define MODE0_INTERRUPT_ON_TERMINAL_COUNT 0 // Despite name, no interrupts on CH2

    // PIT Channel 2 data port
#define PIT_CH2_DATA 0x42

    // Disable the PIT channel 2 speaker and gate
    temp8 = input_u8(PIT_CH2_LATCH_REG);
    temp8 &= ~(CH2_SPEAKER | CH2_GATE_IN);
    output_u8(PIT_CH2_LATCH_REG, temp8);

    // Setup command and mode
    output_u8(PIT_MODE_COMMAND_REG, SELECT_CH2 | ACCESS_MODE_LOBYTE_HIBYTE | MODE0_INTERRUPT_ON_TERMINAL_COUNT);

    // Set time for fixed delay
    output_u8(PIT_CH2_DATA, (U8) (delay_count));
    output_u8(PIT_CH2_DATA, (U8) (delay_count >> 8));

    // Prepare to enable channel 2 gate but leave the speaker disabled
    temp8 = input_u8(PIT_CH2_LATCH_REG);
    temp8 &= ~CH2_SPEAKER;
    temp8 |= CH2_GATE_IN;

    if (x2apic_enabled()) {
        // Set APIC Timer Divide Value as 2
        wrmsr32(MSR_APIC_TMR_DIVIDE_CFG, 0, 0, &status);

        // start APIC timer with a known value
        start = ~0U;
        wrmsr32(MSR_APIC_TMR_INITIAL_CNT, start, 0, &status);
    }
    else {
        // Set APIC Timer Divide Value as 2
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_DIVIDE_CFG) = 0UL;

        // start APIC timer with a known value
        start = ~0U;
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_INITIAL_CNT) = start;
    }

    // Actually start the PIT channel 2
    output_u8(PIT_CH2_LATCH_REG, temp8);

    // Wait for the fixed delay
    while (!(input_u8(PIT_CH2_LATCH_REG) & CH2_GATE_OUT));

    if (x2apic_enabled()) {
        // read the APIC timer to determine the change that occurred over this fixed delay
        rdmsr32(MSR_APIC_TMR_CURRENT_CNT, &stop, &dummy, &status);

        // stop APIC timer
        wrmsr32(MSR_APIC_TMR_INITIAL_CNT, 0, 0, &status);
    }
    else {
        // read the APIC timer to determine the change that occurred over this fixed delay
        stop = *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_CURRENT_CNT);

        // stop APIC timer
        *(volatile U32 *)(unsigned long)(get_apicbase() + APIC_TMR_INITIAL_CNT) = 0UL;
    }

    // Disable channel 2 speaker and gate input
    temp8 = input_u8(PIT_CH2_LATCH_REG);
    temp8 &= ~(CH2_SPEAKER | CH2_GATE_IN);
    output_u8(PIT_CH2_LATCH_REG, temp8);

    bclk = (start - stop) * 2 / DELAY_IN_US;

    // Round bclk to the nearest 100/12 integer value
    bclk = ((((bclk * 24) + 100) / 200) * 200) / 24;
    dprintf("smp", "Compute bclk: %uMHz\n", bclk);
    return bclk;
}

U32 smp_init_with_memory(void *working_memory, void *page_below_1M, void *reserved_mwait_memory)
{
    struct smp_host *host = working_memory;

    /* Sanity checks on the amounts of memory our public interface claims we
       can work within. */
    if (sizeof(struct smp_host) > SMP_WORKING_MEMORY_SIZE) {
        dprintf("smp", "Internal error: SMP_WORKING_MEMORY_SIZE too small; need %u\n", sizeof(struct smp_host));
        return 0;
    }
    if (SMP_RESERVED_MEMORY_SIZE < SMP_MAX_LOGICAL_CPU * SMP_MWAIT_ALIGN + wait_for_control_asm_size) {
        dprintf("smp", "Internal error: SMP_RESERVED_MEMORY_SIZE too small; need %u\n", SMP_MAX_LOGICAL_CPU * SMP_MWAIT_ALIGN + wait_for_control_asm_size);
        return 0;
    }
    if (pm32_size > AP_CODE_MAX) {
        dprintf("smp", "Internal error: relocatable SIPI target code too large: %u > %u\n", pm32_size, AP_CODE_MAX);
        return 0;
    }
#ifdef GRUB_TARGET_CPU_X86_64
    if (get_cr3() > ~0U) {
        dprintf("smp", "Internal error: 64-bit page table above 4GB: %p\n", get_cr3());
        return 0;
    }
#endif

    if (host->initialized == SMP_MAGIC)
        return host->logical_processor_count;

    host->expected_processor_count = madt_processor_count();
    if (host->expected_processor_count == 0)
        host->expected_processor_count = 1;

    dprintf("smp", "Processor count from MADT: %u\n", host->expected_processor_count);

    if (host->expected_processor_count > SMP_MAX_LOGICAL_CPU)
        return 0;

    host->mem_region_below_1M = page_below_1M;
    host->logical_processor_count = 1;
    if (reserved_mwait_memory) {
        host->control = reserved_mwait_memory;
        host->wait_for_control = (void *)(((U8 *) reserved_mwait_memory) + SMP_MWAIT_ALIGN * SMP_MAX_LOGICAL_CPU);
        memcpy(host->wait_for_control, wait_for_control_asm, wait_for_control_asm_size);
    } else {
        host->control = (U8 *)(((unsigned long)host->control_region - 1) & (SMP_MWAIT_ALIGN - 1)) + 1;
        host->wait_for_control = wait_for_control_asm;
    }

    // Init the host structure
    {
        U32 i;
        for (i = 0; i < SMP_MAX_LOGICAL_CPU; i++) {
            host->cpu[i].present = 0;
            set_control((U32 *) (host->control + i * SMP_MWAIT_ALIGN), BSP_IN_CONTROL);
            host->cpu_data[i].use_mwait = true;
            host->cpu_data[i].mwait_hint = 0;
            host->cpu_data[i].int_break_event = 1;
            host->cpu_data[i].function = ap_park;
            host->cpu_data[i].param = NULL;
        }
    }

    host->cpu[0].present = 1;
    read_apicid(&host->cpu[0].apicid);

    host->bclk = compute_bclk();

    host->bsp_exception_info.gpf_idtr_installed = 0;
    host->ap_exception_info.gpf_idtr_installed = 0;
    init_bsp_exception_handling(host);

    if (do_callback(host, find_logical_processors, host)) {
        host->initialized = SMP_MAGIC;
        return host->logical_processor_count;
    } else
        return 0;
}

void smp_phantom_init_with_memory(void *working_memory)
{
    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC)
        return;
    host->initialized = 0;
}

U32 smp_read_bclk_with_memory(void *working_memory)
{
    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC)
        return 0;
    return host->bclk;
}

const CPU_INFO *smp_read_cpu_list_with_memory(void *working_memory)
{
    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC)
        return NULL;
    return host->cpu;
}

U32 smp_function_with_memory(void *working_memory, U32 apicid, CALLBACK function, void *param)
{
    struct smp_host *host = working_memory;
    if (!host || host->initialized != SMP_MAGIC) {
        dprintf("smp", "smp_function returning 0 because working memory not initialized\n");
        return 0;
    }

    if (!function) {
        dprintf("smp", "smp_function returning 0 because !function\n");
        return 0;
    }

    if (apicid == host->cpu[0].apicid) {
        struct exception_info *e = &host->bsp_exception_info;
        if (e->gpf_idtr_installed) {
            set_idtr(&host->bsp_exception_info.idt_descriptor);
            function(param);
            set_idtr(&real_mode_idtr);
        } else {
            struct gate old_gate;
            get_gate(0xd, &old_gate);
            set_protected_mode_exception_handler(0xd, gpfHandler);
            function(param);
            set_gate(0xd, &old_gate);
        }
    } else {
        U32 processor_id;
        CPU_DATA *cpu_data;
        U32 *my_control;

        if (find_processor_id_for_this_apicid(apicid, &processor_id, host) == 0) {
            dprintf("smp", "smp_function returning 0 because APIC ID not found\n");
            return 0;
        }

        cpu_data = &host->cpu_data[processor_id];
        my_control = (U32 *) (host->control + processor_id * SMP_MWAIT_ALIGN);

        // Check if AP is available - FIXME: this should be an assert
        if (*my_control != BSP_IN_CONTROL) {
            dprintf("smp", "smp_function returning 0 because BSP not in control\n");
            return 0;
        }
        // Assign the function and its parameter
        cpu_data->function = function;
        cpu_data->param = param;

        set_control(my_control, AP_IN_CONTROL);
        host->wait_for_control(my_control, BSP_IN_CONTROL, cpu_data[0].use_mwait && mwait_supported(), cpu_data[0].mwait_hint, cpu_data[0].int_break_event && int_break_event_supported());
    }

    return 1;
}

/* Called from smpasm directly, which won't use a C prototype, so just give one here to silence the warning. */
asmlinkage void intHandler(void);
asmlinkage void intHandler(void)
{
    struct gate gate;
    void (*func) (void *);
    void *param;

    send_apic_eoi();
    get_gate(0x31, &gate);
    func = get_gate_offset(&gate);
    get_gate(0x32, &gate);
    param = get_gate_offset(&gate);
    func(param);
}

static void set_control_callback(void *param)
{
    set_control(param, 0);
}

static inline void disable_interrupts(void)
{
    __asm__ __volatile__ ("cli");
}

static inline void enable_interrupts(void)
{
    __asm__ __volatile__ ("sti");
}

void smp_sleep_with_memory(void *working_memory, U32 microseconds)
{
    struct smp_host *host = working_memory;
    U32 processor_id;
    CPU_DATA *cpu_data;
    struct gate gate = EMPTY_GATE;
    U32 my_control[SMP_MWAIT_ALIGN / sizeof(U32)];
    bool oldmask;

    if (!host || host->initialized != SMP_MAGIC)
        return;

    if (find_processor_id_for_this_cpu(&processor_id, host) == 0)
        return;

    cpu_data = &host->cpu_data[processor_id];

    set_protected_mode_exception_handler(0x30, intHandler_asm);
    set_gate_offset(&gate, set_control_callback);
    set_gate(0x31, &gate);
    set_gate_offset(&gate, my_control);
    set_gate(0x32, &gate);

    set_control(my_control, 1);

    /* Set up the timer that puts the BSP back in control */
    oldmask = mask_lint0(1); /* Need to prevent other interrupts while sti'd */
    enable_interrupts();

    setup_apic(0, 0x30);
    start_apic_timer(host, microseconds);

    host->wait_for_control(my_control, 0,
                           cpu_data->use_mwait && mwait_supported(), cpu_data->mwait_hint,
                           cpu_data->int_break_event && int_break_event_supported());

    setup_apic(1, 0xff);

    disable_interrupts();
    mask_lint0(oldmask);
}
