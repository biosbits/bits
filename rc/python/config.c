/* -*- C -*- ***********************************************
Based on the Python Modules/config.c.in, which had:
Copyright (c) 2000, BeOpen.com.
Copyright (c) 1995-2000, Corporation for National Research Initiatives.
Copyright (c) 1990-1995, Stichting Mathematisch Centrum.
All rights reserved.

See the file "Misc/COPYRIGHT" for information on usage and
redistribution of this file, and for a DISCLAIMER OF ALL WARRANTIES.
******************************************************************/

#include "Python.h"
#include "acpimodule.h"
#include "bitsmodule.h"
#include "pyfsmodule.h"
#include "efimodule.h"
#include "smpmodule.h"

char *Py_GetExecPrefix(void)
{
    return "";
}

char *Py_GetPath(void)
{
    return "";
}

char *Py_GetPrefix(void)
{
    return "";
}

char *Py_GetProgramFullPath(void)
{
    return "";
}

void PyOS_InitInterrupts(void)
{
}

void PyOS_FiniInterrupts(void)
{
}

int PyOS_InterruptOccurred(void)
{
    return 0;
}

static int _Py_HashSecret_Initialized = 0;

/* Stub out hash randomization, since we don't have a random number generator
 * to seed it from. */
void _PyRandom_Init(void)
{
    if (_Py_HashSecret_Initialized)
        return;
    _Py_HashSecret_Initialized = 1;
    memset(&_Py_HashSecret, 0, sizeof(_Py_HashSecret_t));
}

void _PyRandom_Fini(void)
{
}

extern void PyMarshal_Init(void);
extern void initimp(void);
extern void inititertools(void);
extern void initgc(void);
extern void initarray(void);
extern void init_ast(void);
extern void initbinascii(void);
extern void initcStringIO(void);
extern void initerrno(void);
extern void initmath(void);
extern void initoperator(void);
extern void initstrop(void);
extern void initzlib(void);
extern void init_bisect(void);
extern void init_codecs(void);
extern void init_collections(void);
extern void init_csv(void);
extern void init_ctypes(void);
extern void init_functools(void);
extern void init_heapq(void);
extern void init_md5(void);
extern void init_sha(void);
extern void init_sha256(void);
extern void init_sha512(void);
extern void init_sre(void);
extern void init_struct(void);
extern void initunicodedata(void);
extern void init_weakref(void);
extern void initzipimport(void);

struct _inittab _PyImport_Inittab[] = {

    /* This module lives in marshal.c */
    {"marshal", PyMarshal_Init},

    /* This lives in import.c */
    {"imp", initimp},

    /* This lives in Python/Python-ast.c */
    {"_ast", init_ast},

    /* These entries are here for sys.builtin_module_names */
    {"__main__", NULL},
    {"__builtin__", NULL},
    {"sys", NULL},
    {"exceptions", NULL},

    /* This lives in gcmodule.c */
    {"gc", initgc},

    /* This lives in _warnings.c */
    {"_warnings", _PyWarnings_Init},

    {"errno", initerrno},
    {"_struct", init_struct},

    {"array", initarray},
    {"binascii", initbinascii},
    {"cStringIO", initcStringIO},
    {"itertools", inititertools},
    {"math", initmath},
    {"operator", initoperator},
    {"strop", initstrop},
    {"unicodedata", initunicodedata},
    {"zipimport", initzipimport},
    {"zlib", initzlib},
    {"_acpi", init_acpi_module},
    {"_bisect", init_bisect},
    {"_bits", init_bits},
    {"_codecs", init_codecs},
    {"_collections", init_collections},
    {"_csv", init_csv},
    {"_ctypes", init_ctypes},
#ifdef GRUB_MACHINE_EFI
    {"_efi", init_efi},
#endif
    {"_functools", init_functools},
    {"_heapq", init_heapq},
    {"_md5", init_md5},
    {"_pyfs", init_pyfs},
    {"_smp", init_smp_module},
    {"_sha", init_sha},
    {"_sha256", init_sha256},
    {"_sha512", init_sha512},
    {"_sre", init_sre},
    {"_weakref", init_weakref},

    /* Sentinel */
    {0, 0}
};
