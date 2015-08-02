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

#include "Python.h"
#include "pyunconfig.h"

#include <grub/cpu/io.h>
#include <grub/mm.h>

#include "smpmodule.h"
#include "smp.h"

struct dword_regs {
    U32 eax;
    U32 ebx;
    U32 ecx;
    U32 edx;
};

struct memop {
    unsigned long addr;
    U64 value;
};

static PyObject *bits_bclk(PyObject *self, PyObject *args)
{
    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    return Py_BuildValue("I", smp_read_bclk());
}

static U32 bsp_apicid(void) {
    const CPU_INFO *cpu;
    cpu = smp_read_cpu_list();
    return cpu[0].apicid;
}

static void blocking_sleep_callback(void *param)
{
    U32 *usec = param;
    smp_sleep(*usec);
}

static PyObject *bits_blocking_sleep(PyObject *self, PyObject *args)
{
    U32 usec;

    if (!PyArg_ParseTuple(args, "I", &usec))
        return NULL;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    smp_function(smp_read_cpu_list()[0].apicid, blocking_sleep_callback, &usec);
    return Py_BuildValue("");
}

static void cpuid_callback(void *param)
{
    struct dword_regs *r = param;
    cpuid32_indexed(r->eax, r->ecx, &r->eax, &r->ebx, &r->ecx, &r->edx);
}

/* Returns true for success, false for failure. */
static bool smp_cpuid(U32 apicid, struct dword_regs *regs)
{
    return !!smp_function(apicid, cpuid_callback, regs);
}

static PyObject *bits_cpuid(PyObject *self, PyObject *args)
{
    struct dword_regs regs = { .ecx=0 };
    unsigned apicid;
    int ncpus;

    if (!PyArg_ParseTuple(args, "II|I", &apicid, &regs.eax, &regs.ecx))
        return NULL;

    ncpus = smp_init();
    if (!ncpus)
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    if (!smp_cpuid(apicid, &regs))
        return PyErr_Format(PyExc_RuntimeError, "SMP function returned an error; does apicid 0x%x exist?", apicid);
    return Py_BuildValue("IIII", regs.eax, regs.ebx, regs.ecx, regs.edx);
}

static PyObject *bits_cpus(PyObject *self, PyObject *args)
{
    int ncpus;
    int ndx;
    PyObject *apicid_list;
    const CPU_INFO *cpu;

    ncpus = smp_init();
    if (!ncpus)
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    apicid_list = PyList_New(ncpus);
    cpu = smp_read_cpu_list();
    for (ndx = 0; ndx < ncpus; ndx++)
        PyList_SET_ITEM(apicid_list, ndx, Py_BuildValue("i", cpu[ndx].apicid));
    return Py_BuildValue("N", apicid_list);
}

struct msr {
    U32 num;
    U32 status;
    U64 value;
};

static void rdmsr_callback(void *param)
{
    struct msr *m = param;
    rdmsr64(m->num, &m->value, &m->status);
}

/* Returns true for success, false for failure. */
static bool smp_rdmsr(U32 apicid, struct msr *msr)
{
    msr->status = -1;
    smp_function(apicid, rdmsr_callback, msr);
    return !msr->status;
}

static PyObject *bits_rdmsr(PyObject *self, PyObject *args)
{
    struct msr msr;
    unsigned apicid;
    int ncpus;

    if (!PyArg_ParseTuple(args, "II", &apicid, &msr.num))
        return NULL;

    ncpus = smp_init();
    if (!ncpus)
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    if (!smp_rdmsr(apicid, &msr))
        return Py_BuildValue("");
    return Py_BuildValue("K", msr.value);
}

static void wrmsr_callback(void *param)
{
    struct msr *m = param;
    wrmsr64(m->num, m->value, &m->status);
}

/* Returns true for success, false for failure. */
static bool smp_wrmsr(U32 apicid, struct msr *msr)
{
    msr->status = -1;
    smp_function(apicid, wrmsr_callback, msr);
    return !msr->status;
}

static PyObject *bits_wrmsr(PyObject *self, PyObject *args)
{
    struct msr msr;
    unsigned apicid;
    int ncpus;

    if (!PyArg_ParseTuple(args, "IIK", &apicid, &msr.num, &msr.value))
        return NULL;

    ncpus = smp_init();
    if (!ncpus)
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    if (!smp_wrmsr(apicid, &msr))
        return Py_BuildValue("");
    return PyBool_FromLong(!msr.status);
}

struct control_register {
    unsigned long value;
    U32 status;
};

static void read_cr0_callback(void *param)
{
    struct control_register *r = param;
    read_cr0(&r->value, &r->status);
}

static void read_cr2_callback(void *param)
{
    struct control_register *r = param;
    read_cr2(&r->value, &r->status);
}

static void read_cr3_callback(void *param)
{
    struct control_register *r = param;
    read_cr3(&r->value, &r->status);
}

static void read_cr4_callback(void *param)
{
    struct control_register *r = param;
    read_cr4(&r->value, &r->status);
}

#ifdef GRUB_TARGET_CPU_X86_64
static void read_cr8_callback(void *param)
{
    struct control_register *r = param;
    read_cr8(&r->value, &r->status);
}
#endif

static PyObject *bits_read_cr(PyObject *self, PyObject *args)
{
    struct control_register r = { .status = -1 };
    unsigned apicid;
    unsigned num;

    if (!PyArg_ParseTuple(args, "II", &apicid, &num))
        return NULL;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    switch (num) {
    case 0: smp_function(apicid, read_cr0_callback, &r); break;
    case 2: smp_function(apicid, read_cr2_callback, &r); break;
    case 3: smp_function(apicid, read_cr3_callback, &r); break;
    case 4: smp_function(apicid, read_cr4_callback, &r); break;
#ifdef GRUB_TARGET_CPU_X86_64
    case 8: smp_function(apicid, read_cr8_callback, &r); break;
#endif
    default:
        return PyErr_Format(PyExc_ValueError, "Invalid control register cr%u", num);
        break;
    }
    if (r.status)
        Py_RETURN_NONE;
    return Py_BuildValue("k", r.value);
}

static void write_cr0_callback(void *param)
{
    struct control_register *r = param;
    write_cr0(r->value, &r->status);
}

static void write_cr2_callback(void *param)
{
    struct control_register *r = param;
    write_cr2(r->value, &r->status);
}

static void write_cr3_callback(void *param)
{
    struct control_register *r = param;
    write_cr3(r->value, &r->status);
}

static void write_cr4_callback(void *param)
{
    struct control_register *r = param;
    write_cr4(r->value, &r->status);
}

#ifdef GRUB_TARGET_CPU_X86_64
static void write_cr8_callback(void *param)
{
    struct control_register *r = param;
    write_cr8(r->value, &r->status);
}
#endif

static PyObject *bits_write_cr(PyObject *self, PyObject *args)
{
    struct control_register r;
    unsigned apicid;
    unsigned num;

    if (!PyArg_ParseTuple(args, "IIk", &apicid, &num, &r.value))
        return NULL;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");

    switch (num) {
    case 0: smp_function(apicid, write_cr0_callback, &r); break;
    case 2: smp_function(apicid, write_cr2_callback, &r); break;
    case 3: smp_function(apicid, write_cr3_callback, &r); break;
    case 4: smp_function(apicid, write_cr4_callback, &r); break;
#ifdef GRUB_TARGET_CPU_X86_64
    case 8: smp_function(apicid, write_cr8_callback, &r); break;
#endif
    default:
        return PyErr_Format(PyExc_ValueError, "Invalid control register cr%u", num);
        break;
    }
    if (r.status)
        Py_RETURN_NONE;
    Py_RETURN_TRUE;
}

static void inb_callback(void *param)
{
    struct memop *m = param;
    m->value = grub_inb(m->addr);
}

static char *in_keywords[] = {"port", "apicid", NULL};

static PyObject *bits_inb(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "H|I", in_keywords, &port, &apicid))
        return NULL;
    m.addr = port;

    if (!smp_function(apicid, inb_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("B", (U8)m.value);
}

static void inw_callback(void *param)
{
    struct memop *m = param;
    m->value = grub_inw(m->addr);
}

static PyObject *bits_inw(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "H|I", in_keywords, &port, &apicid))
        return NULL;
    m.addr = port;

    if (!smp_function(apicid, inw_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("H", (U16)m.value);
}

static void inl_callback(void *param)
{
    struct memop *m = param;
    m->value = grub_inl(m->addr);
}

static PyObject *bits_inl(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "H|I", in_keywords, &port, &apicid))
        return NULL;
    m.addr = port;

    if (!smp_function(apicid, inl_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("I", (U32)m.value);
}

static void outb_callback(void *param)
{
    struct memop *m = param;
    grub_outb(m->value, m->addr);
}

static char *out_keywords[] = {"port", "value", "apicid", NULL};

static PyObject *bits_outb(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    U8 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "HB|I", out_keywords, &port, &value, &apicid))
        return NULL;
    m.addr = port;
    m.value = value;

    smp_function(apicid, outb_callback, &m);
    return Py_BuildValue("");
}

static void outw_callback(void *param)
{
    struct memop *m = param;
    grub_outw(m->value, m->addr);
}

static PyObject *bits_outw(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    U16 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "HH|I", out_keywords, &port, &value, &apicid))
        return NULL;
    m.addr = port;
    m.value = value;

    smp_function(apicid, outw_callback, &m);
    return Py_BuildValue("");
}

static void outl_callback(void *param)
{
    struct memop *m = param;
    grub_outl(m->value, m->addr);
}

static PyObject *bits_outl(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 port;
    U32 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "HI|I", out_keywords, &port, &value, &apicid))
        return NULL;
    m.addr = port;
    m.value = value;

    smp_function(apicid, outl_callback, &m);
    return Py_BuildValue("");
}

static void readb_callback(void *param)
{
    struct memop *m = param;
    m->value = *(U8 *)(m->addr);
}

static char *read_keywords[] = {"address", "apicid", NULL};

static PyObject *bits_readb(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "k|I", read_keywords, &m.addr, &apicid))
        return NULL;

    if (!smp_function(apicid, readb_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("B", (U8)m.value);
}

static void readw_callback(void *param)
{
    struct memop *m = param;
    m->value = *(U16 *)(m->addr);
}

static PyObject *bits_readw(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "k|I", read_keywords, &m.addr, &apicid))
        return NULL;

    if (!smp_function(apicid, readw_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("H", (U16)m.value);
}

static void readl_callback(void *param)
{
    struct memop *m = param;
    m->value = *(U32 *)(m->addr);
}

static PyObject *bits_readl(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "k|I", read_keywords, &m.addr, &apicid))
        return NULL;

    if (!smp_function(apicid, readl_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("I", (U32)m.value);
}

static void readq_callback(void *param)
{
    struct memop *m = param;
    m->value = *(U64 *)m->addr;
}

static PyObject *bits_readq(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "k|I", read_keywords, &m.addr, &apicid))
        return NULL;

    if (!smp_function(apicid, readq_callback, &m))
        return Py_BuildValue("");
    return Py_BuildValue("K", m.value);
}

static void writeb_callback(void *param)
{
    struct memop *m = param;
    *(U8 *)(m->addr) = m->value;
}

static char *write_keywords[] = {"address", "value", "apicid", NULL};

static PyObject *bits_writeb(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U8 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "kB|I", write_keywords, &m.addr, &value, &apicid))
        return NULL;
    m.value = value;

    smp_function(apicid, writeb_callback, &m);
    return Py_BuildValue("");
}

static void writew_callback(void *param)
{
    struct memop *m = param;
    *(U16 *)(m->addr) = m->value;
}

static PyObject *bits_writew(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U16 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "kH|I", write_keywords, &m.addr, &value, &apicid))
        return NULL;
    m.value = value;

    smp_function(apicid, writew_callback, &m);
    return Py_BuildValue("");
}

static void writel_callback(void *param)
{
    struct memop *m = param;
    *(U32 *)(m->addr) = m->value;
}

static PyObject *bits_writel(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    U32 value;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "kI|I", write_keywords, &m.addr, &value, &apicid))
        return NULL;
    m.value = value;

    smp_function(apicid, writel_callback, &m);
    return Py_BuildValue("");
}

static void writeq_callback(void *param)
{
    struct memop *m = param;
    *(U64 *)(m->addr) = m->value;
}

static PyObject *bits_writeq(PyObject *self, PyObject *args, PyObject *keywds)
{
    struct memop m;
    unsigned apicid;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    apicid = bsp_apicid();

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "kK|I", write_keywords, &m.addr, &m.value, &apicid))
        return NULL;

    smp_function(apicid, writeq_callback, &m);
    return Py_BuildValue("");
}

#define LATENCY_RECENT_COUNT 6
struct latency_bin {
    U64 max;
    U64 total;
    U64 count;
    U32 recent_index;
    U64 recent_absolute[LATENCY_RECENT_COUNT];
};

#define MSR_SMI_COUNT 0x34
static PyObject *bits_smi_latency(PyObject *self, PyObject *args)
{
    U64 test_duration_tscs;
    PyObject *bin_maxes;
    PyObject *bin_obj = NULL;
    PyObject *recent_list = NULL;
    U32 bsp;
    struct msr smi_count1, smi_count2;
    PyObject *smi_count_obj;
    struct latency_bin *bin;
    U32 bin_len;
    U64 test_start;
    U64 tsc1, tsc2;
    U64 current;
    U32 i;
    U64 max = 0;

    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    bsp = bsp_apicid();
    smi_count1.num = smi_count2.num = MSR_SMI_COUNT;

    if (!PyArg_ParseTuple(args, "KO:smi_latency", &test_duration_tscs, &bin_maxes))
        return NULL;
    if (!PySequence_Check(bin_maxes))
        return PyErr_Format(PyExc_TypeError, "expected a sequence");
    bin_len = PySequence_Length(bin_maxes);
    if (bin_len == -1)
        return PyErr_Format(PyExc_ValueError, "failed to get length of sequence");

    bin = grub_zalloc((bin_len + 1) * sizeof(*bin));
    for (i = 0; i < bin_len; i++) {
        PyObject *bin_max_obj = PySequence_GetItem(bin_maxes, i);
        if (PyLong_Check(bin_max_obj)) {
            bin[i].max = PyLong_AsUnsignedLongLong(bin_max_obj);
        } else if (PyInt_Check(bin_max_obj)) {
            bin[i].max = PyInt_AsUnsignedLongLongMask(bin_max_obj);
        } else {
            Py_CLEAR(bin_max_obj);
            PyErr_Format(PyExc_TypeError, "expected an int or long");
            goto err;
        }
        Py_CLEAR(bin_max_obj);
        if (bin[i].max == (U64)-1)
            goto err;
    }
    bin[bin_len].max = ~0ULL;
    bin_len++;

    smp_rdmsr(bsp, &smi_count1);

    for (test_start = tsc1 = rdtsc64(), tsc2 = rdtsc64(); tsc2 - test_start < test_duration_tscs; tsc1 = tsc2, tsc2 = rdtsc64()) {
        current = tsc2 - tsc1;

        for (i = 0; i < bin_len; i++)
            if (current <= bin[i].max) {
                bin[i].count++;
                bin[i].total += current;
                if (bin[i].recent_index != LATENCY_RECENT_COUNT) {
                    bin[i].recent_absolute[bin[i].recent_index] = tsc2;
                    bin[i].recent_index++;
                }
                break;
            }

        if (current > max)
            max = current;
    }

    smp_rdmsr(bsp, &smi_count2);

    bin_obj = PyList_New(bin_len);
    if (!bin_obj)
        goto err;
    for(i = 0; i < bin_len; i++) {
        PyObject *bin_tuple;
        U32 j;
        recent_list = PyList_New(bin[i].recent_index);
        if (!recent_list)
            goto err;
        for (j = 0; j < bin[i].recent_index; j++) {
            PyObject *long_obj = PyLong_FromUnsignedLongLong(bin[i].recent_absolute[j]);
            if (!long_obj)
                goto err;
            PyList_SET_ITEM(recent_list, j, long_obj);
        }
        bin_tuple = Py_BuildValue("KKKN", bin[i].max, bin[i].total, bin[i].count, recent_list);
        if (!bin_tuple)
            goto err;
        PyList_SET_ITEM(bin_obj, i, bin_tuple);
    }

    if (smi_count1.status == 0 && smi_count2.status == 0)
        smi_count_obj = PyLong_FromUnsignedLongLong(smi_count2.value - smi_count1.value);
    else
        smi_count_obj = Py_BuildValue("");

    return Py_BuildValue("KNN", max, smi_count_obj, bin_obj);

err:
    Py_XDECREF(recent_list);
    Py_XDECREF(bin_obj);
    grub_free(bin);
    return NULL;
}

static PyObject *bits_get_mwait(PyObject *self, PyObject *args)
{
    U32 apicid;
    bool use_mwait;
    U32 hint, int_break_event;
    if (!PyArg_ParseTuple(args, "I:get_mwait", &apicid))
        return NULL;
    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    if (!smp_get_mwait(apicid, &use_mwait, &hint, &int_break_event))
        return PyErr_Format(PyExc_RuntimeError, "Failed to get mwait hint for apicid %u", apicid);
    return Py_BuildValue("NIN", PyBool_FromLong(use_mwait), hint, PyBool_FromLong(int_break_event));
}

static PyObject *bits_set_mwait(PyObject *self, PyObject *args)
{
    U32 apicid, hint = 0;
    PyObject *use_mwait_obj, *int_break_event_obj = NULL;
    if (!PyArg_ParseTuple(args, "IO|IO:set_mwait", &apicid, &use_mwait_obj, &hint, &int_break_event_obj))
        return NULL;
    if (!smp_init())
        return PyErr_Format(PyExc_RuntimeError, "SMP module failed to initialize.");
    smp_set_mwait(apicid, PyObject_IsTrue(use_mwait_obj), hint, int_break_event_obj ? PyObject_IsTrue(int_break_event_obj) : 1);
    return Py_BuildValue("");
}

static PyMethodDef smpMethods[] = {
    {"bclk", bits_bclk, METH_NOARGS, "bclk() -> bclk (in MHz)"},
    {"blocking_sleep", bits_blocking_sleep, METH_VARARGS, "sleep using mwait for the specified number of microseconds"},
    {"_cpuid", bits_cpuid, METH_VARARGS, "_cpuid(apicid, eax[, ecx]) -> eax, ebx, ecx, edx"},
    {"cpus",  bits_cpus, METH_NOARGS, "cpus() -> list of APIC IDs"},
    {"get_mwait", bits_get_mwait, METH_VARARGS, "get_mwait(apicid) -> (use_mwait, hint, int_break_event)"},
    {"inb", (PyCFunction)bits_inb, METH_KEYWORDS, "inb(port[, apicid=BSP]) -> read byte from IO port on the specified CPU"},
    {"inw", (PyCFunction)bits_inw, METH_KEYWORDS, "inw(port[, apicid=BSP]) -> read word from IO port on the specified CPU"},
    {"inl", (PyCFunction)bits_inl, METH_KEYWORDS, "inl(port[, apicid=BSP]) -> read dword from IO port on the specified CPU"},
    {"outb", (PyCFunction)bits_outb, METH_KEYWORDS, "outb(port, value[, apicid=BSP]) -> write byte to IO port on the specified CPU"},
    {"outw", (PyCFunction)bits_outw, METH_KEYWORDS, "outw(port, value[, apicid=BSP]) -> write word to IO port on the specified CPU"},
    {"outl", (PyCFunction)bits_outl, METH_KEYWORDS, "outl(port, value[, apicid=BSP]) -> write dword to IO port on the specified CPU"},
    {"rdmsr",  bits_rdmsr, METH_VARARGS, "rdmsr(apicid, msr) -> long (None if GPF)"},
    {"read_cr",  bits_read_cr, METH_VARARGS, "read_cr(apicid, cr) -> long (None if GPF)"},
    {"readb", (PyCFunction)bits_readb, METH_KEYWORDS, "readb(address[, apicid=BSP]) -> read byte from memory on the specified CPU"},
    {"readw", (PyCFunction)bits_readw, METH_KEYWORDS, "readw(address[, apicid=BSP]) -> read word from memory on the specified CPU"},
    {"readl", (PyCFunction)bits_readl, METH_KEYWORDS, "readl(address[, apicid=BSP]) -> read dword from memory on the specified CPU"},
    {"readq", (PyCFunction)bits_readq, METH_KEYWORDS, "readq(address[, apicid=BSP]) -> read qword from memory on the specified CPU"},
    {"set_mwait", bits_set_mwait, METH_VARARGS, "set_mwait(apicid, use_mwait[, hint=0[, int_break_event=True]]) -> Enable/disable MWAIT, and set hints and flags"},
    {"smi_latency", bits_smi_latency, METH_VARARGS, "smi_latency(duration, bin_maxes) -> (max_latency, smi_count_delta, [(bin_max, bin_total, bin_count, [latency])]). All times in TSC counts. smi_count_delta is None if reading MSR_SMI_COUNT GPFs."},
    {"write_cr",  bits_write_cr, METH_VARARGS, "write_cr(apicid, cr, value) -> bool (None if GPF, True otherwise)"},
    {"writeb", (PyCFunction)bits_writeb, METH_KEYWORDS, "writeb(address, value[, apicid=BSP]) -> write byte to memory on the specified CPU"},
    {"writew", (PyCFunction)bits_writew, METH_KEYWORDS, "writew(address, value[, apicid=BSP]) -> write word to memory on the specified CPU"},
    {"writel", (PyCFunction)bits_writel, METH_KEYWORDS, "writel(address, value[, apicid=BSP]) -> write dword to memory on the specified CPU"},
    {"writeq", (PyCFunction)bits_writeq, METH_KEYWORDS, "writeq(address, value[, apicid=BSP]) -> write qword to memory on the specified CPU"},
    {"wrmsr",  bits_wrmsr, METH_VARARGS, "wrmsr(apicid, msr, value) -> bool (False if GPF, True otherwise)"},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

static void noop_callback(void *param)
{
    (void)param;
}

static asmlinkage void cpu_ping(uint32_t count)
{
    uint64_t start, stop;
    unsigned i, j, ncpus, seconds = 0;
    const CPU_INFO *cpu;

    ncpus = smp_init();
    if (!ncpus)
        return;
    cpu = smp_read_cpu_list();

    start = grub_get_time_ms();
    for (j = 0; j < count; j++) {
        if (grub_getkey_noblock() == GRUB_TERM_ESC)
            break;
        stop = grub_get_time_ms();
        if (stop - start > 1000) {
            start = stop;
            seconds++;
            grub_printf("\r%u second%s (%u%%)", seconds, seconds == 1 ? "" : "s", (j * 100) / count);
        }
        for (i = 0; i != ncpus; i++)
            smp_function(cpu[i].apicid, noop_callback, NULL);
    }
    grub_printf("\r");
}

PyMODINIT_FUNC init_smp_module(void)
{
    PyObject *m = Py_InitModule("_smp", smpMethods);
    PyModule_AddObject(m, "cpu_ping", PyLong_FromVoidPtr(cpu_ping));
    PyModule_AddObject(m, "rdtsc", PyLong_FromVoidPtr(rdtsc64));
}
