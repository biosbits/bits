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

static PyObject *set_callback(PyObject **global, PyObject *temp)
{
    if (!PyCallable_Check(temp))
        return PyErr_Format(PyExc_TypeError, "expected a callable");

    Py_XDECREF(*global);
    Py_XINCREF(temp);
    *global = temp;

    Py_RETURN_NONE;
}

static PyObject *event_callback;

static PyObject *set_event_callback(PyObject *self, PyObject *args)
{
    PyObject *temp;
    if (!PyArg_ParseTuple(args, "O:_set_event_callback", &temp))
        return NULL;
    return set_callback(&event_callback, temp);
}

PyDoc_STRVAR(set_event_callback_doc,
"_set_event_callback(event_callback)\n"
"\n"
"Set the callback for an event, which must be a callable with the following\n"
"signature:\n"
"\n"
"event_callback(event):\n"
"    event is an EFI_EVENT.  No return value.  If this function raises an\n"
"    exception, that exception will propagate to the main thread.\n"
);

static PyObject *key_callback;
static unsigned long sizeof_EFI_KEY_DATA;

static PyObject *set_key_callback(PyObject *self, PyObject *args)
{
    PyObject *temp;
    if (!PyArg_ParseTuple(args, "Ok:_set_key_callback", &temp, &sizeof_EFI_KEY_DATA))
        return NULL;
    return set_callback(&key_callback, temp);
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
    {"_set_event_callback", set_event_callback, METH_VARARGS, set_event_callback_doc},
    {"_set_key_callback", set_key_callback, METH_VARARGS, set_key_callback_doc},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

static int call_callback(PyObject *callback, void *arg)
{
    PyObject *ret;
    ret = PyObject_CallFunction(callback, "O&", PyLong_FromVoidPtr, arg);
    Py_XDECREF(ret);
    if (PyErr_Occurred())
        return -1;
    return 0;
}

static int call_event_callback(void *event)
{
    return call_callback(event_callback, event);
}

static __attribute__((ms_abi)) void c_event_callback(void *event, void *context)
{
    Py_AddPendingCall(call_event_callback, event);
}

static int call_key_callback(void *key_data)
{
    return call_callback(key_callback, key_data);
}

struct EFI_KEY_DATA {
    U16 ScanCode;
    U16 UnicodeChar;
    U32 KeyShiftState;
    U8 KeyToggleState;
};

#define EFI_SHIFT_STATE_VALID  0x80000000
#define EFI_SHIFT_STATE_MASK   0x000003ff
#define EFI_TOGGLE_STATE_VALID 0x80
#define EFI_SCROLL_LOCK_ACTIVE 0x01
#define EFI_NUM_LOCK_ACTIVE    0x02
#define EFI_CAPS_LOCK_ACTIVE   0x04
#define EFI_KEY_STATE_EXPOSED  0x40

static __attribute__((ms_abi)) unsigned long c_key_callback(struct EFI_KEY_DATA *key_data)
{
    unsigned long data;
    if (key_data->UnicodeChar)
        data = key_data->UnicodeChar;
    else
        data = (1UL << 16) | (unsigned long)key_data->ScanCode;
    if (key_data->KeyShiftState & EFI_SHIFT_STATE_VALID)
        data |= (key_data->KeyShiftState & EFI_SHIFT_STATE_MASK) << 17;
    if (key_data->KeyToggleState & EFI_TOGGLE_STATE_VALID) {
        if (key_data->KeyToggleState & EFI_SCROLL_LOCK_ACTIVE)
            data |= 1 << 28;
        if (key_data->KeyToggleState & EFI_NUM_LOCK_ACTIVE)
            data |= 1 << 29;
        if (key_data->KeyToggleState & EFI_CAPS_LOCK_ACTIVE)
            data |= 1 << 30;
        if (key_data->KeyToggleState & EFI_KEY_STATE_EXPOSED)
            data |= 1 << 31;
    }
    Py_AddPendingCall(call_key_callback, (void *)data);
    return 0;
}

PyMODINIT_FUNC init_efi(void)
{
    PyObject *m = Py_InitModule("_efi", efiMethods);
    PyModule_AddObject(m, "_system_table", PyLong_FromVoidPtr(grub_efi_system_table));
    PyModule_AddObject(m, "_image_handle", PyLong_FromVoidPtr(grub_efi_image_handle));
    PyModule_AddObject(m, "_c_event_callback", PyLong_FromVoidPtr(c_event_callback));
    PyModule_AddObject(m, "_c_key_callback", PyLong_FromVoidPtr(c_key_callback));
}
