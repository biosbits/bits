/*
Copyright (c) 2010, Intel Corporation
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

#ifndef smprc_h
#define smprc_h

#include "datatype.h"
#include "portable.h"

typedef struct cpu_info {
    U32 present;
    U32 apicid;
} CPU_INFO;

typedef void (*CALLBACK)(void *);

/* smp_init_with_memory returns the number of CPUs, or 0 on error. */
U32 smp_init_with_memory(void *working_memory, void *page_below_1M, void *reserved_mwait_memory);

#define SMP_MAX_LOGICAL_CPU 384
#define SMP_MWAIT_ALIGN 64
#define SMP_WORKING_MEMORY_SIZE (810*1024)
#define SMP_WORKING_MEMORY_ALIGN 16
#define SMP_LOW_MEMORY_SIZE 4096
#define SMP_LOW_MEMORY_ALIGN 4096
#define SMP_RESERVED_MEMORY_SIZE (SMP_MAX_LOGICAL_CPU*SMP_MWAIT_ALIGN + 512)
#define SMP_RESERVED_MEMORY_ALIGN SMP_MWAIT_ALIGN

/* smp_phantom_init_with_memory is required after any module uses an init-sipi-sipi sequence */
void smp_phantom_init_with_memory(void *working_memory);

U32 smp_read_bclk_with_memory(void *working_memory);

/* Returns the internal array of CPU_INFO structures, or NULL on error.
 *
 * The returned pointer has const for a reason: do not modify the result
 * without copying it.
 */
const CPU_INFO *smp_read_cpu_list_with_memory(void *working_memory);

U32 smp_function_with_memory(void *working_memory, U32 apicid, CALLBACK function, void *param);

bool smp_get_mwait_with_memory(void *working_memory, U32 apicid, bool *use_mwait, U32 *mwait_hint, U32 *int_break_event);
void smp_set_mwait_with_memory(void *working_memory, U32 apicid, bool use_mwait, U32 mwait_hint, U32 int_break_event);

void smp_sleep_with_memory(void *working_memory, U32 microseconds);

void cpuid32(U32 func, U32 * eax, U32 * ebx, U32 * ecx, U32 * edx);
void cpuid32_indexed(U32 func, U32 index, U32 * eax, U32 * ebx, U32 * ecx, U32 * edx);

void read_cr0(unsigned long *data, U32 *status);
void write_cr0(unsigned long data, U32 *status);
void read_cr2(unsigned long *data, U32 *status);
void write_cr2(unsigned long data, U32 *status);
void read_cr3(unsigned long *data, U32 *status);
void write_cr3(unsigned long data, U32 *status);
void read_cr4(unsigned long *data, U32 *status);
void write_cr4(unsigned long data, U32 *status);
#ifdef GRUB_TARGET_CPU_X86_64
void read_cr8(unsigned long *data, U32 *status);
void write_cr8(unsigned long data, U32 *status);
#endif

void rdmsr64(U32 msr, U64 * data_addr, U32 * status);
asmlinkage U64 rdtsc64(void);
void wrmsr64(U32 msr, U64 data, U32 * status);

#endif /* smprc_h */
