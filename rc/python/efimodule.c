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
#include "portable.h"

#include <grub/efi/efi.h>

static PyObject *key_callback;
static unsigned long sizeof_EFI_KEY_DATA;

static PyObject *set_key_callback(PyObject *self, PyObject *args)
{
    PyObject *key_callback_temp;
    if (!PyArg_ParseTuple(args, "Ok:_set_key_callback", &key_callback_temp, &sizeof_EFI_KEY_DATA))
        return NULL;
    if (!PyCallable_Check(key_callback_temp))
        return PyErr_Format(PyExc_TypeError, "expected a callable");

    Py_XDECREF(key_callback);
    Py_XINCREF(key_callback_temp);
    key_callback = key_callback_temp;

    Py_RETURN_NONE;
}

PyDoc_STRVAR(set_key_callback_doc,
"_set_key_callback(key_callback, sizeof_EFI_KEY_DATA)\n"
"\n"
"Set the callback for a keyboard key, which must be a callable with the\n"
"following signature:\n"
"\n"
"key_callback(keydata):\n"
"    keydata is a temporary pointer to EFI_KEY_DATA, freed after key_callback\n"
"    returns.  No return value.  If this function raises an exception, that\n"
"    exception will propagate to the main thread.\n"
);

static PyMethodDef efiMethods[] = {
    {"_set_key_callback", set_key_callback, METH_VARARGS, set_key_callback_doc},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

int call_key_callback(void *key_data)
{
    PyObject *ret;
    ret = PyObject_CallFunction(key_callback, "O&", PyLong_FromVoidPtr, key_data);
    Py_XDECREF(ret);
    if (PyErr_Occurred())
        return -1;
    return 0;
}

__attribute__((ms_abi)) unsigned long c_key_callback(void *key_data)
{
    void *key_data_copy = PyObject_Malloc(sizeof_EFI_KEY_DATA);
    if (!key_data_copy)
        return GRUB_EFI_OUT_OF_RESOURCES;
    memcpy(key_data_copy, key_data, sizeof_EFI_KEY_DATA);
    Py_AddPendingCall(call_key_callback, key_data_copy);
    return 0;
}

PyMODINIT_FUNC init_efi(void)
{
    PyObject *m = Py_InitModule("_efi", efiMethods);
    PyModule_AddObject(m, "_system_table", PyLong_FromVoidPtr(grub_efi_system_table));
    PyModule_AddObject(m, "_image_handle", PyLong_FromVoidPtr(grub_efi_image_handle));
    PyModule_AddObject(m, "_c_key_callback", PyLong_FromVoidPtr(c_key_callback));
}
