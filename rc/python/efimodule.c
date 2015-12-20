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

#include "efimodule.h"

#include <grub/efi/efi.h>

int py_keyboard_interrupt_callback(void *arg)
{
    PyErr_SetNone(PyExc_KeyboardInterrupt);
    return -1;
}

__attribute__((ms_abi)) unsigned long c_keyboard_interrupt_callback(void *KeyData)
{
    Py_AddPendingCall(py_keyboard_interrupt_callback, NULL);
    return 0;
}

PyMODINIT_FUNC init_efi(void)
{
    PyObject *m = Py_InitModule("_efi", NULL);
    PyModule_AddObject(m, "_system_table", PyLong_FromVoidPtr(grub_efi_system_table));
    PyModule_AddObject(m, "_image_handle", PyLong_FromVoidPtr(grub_efi_image_handle));
    PyModule_AddObject(m, "_c_keyboard_interrupt_callback", PyLong_FromVoidPtr(c_keyboard_interrupt_callback));
}
