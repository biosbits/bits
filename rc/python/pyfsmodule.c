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

#include "pyfsmodule.h"

#include <grub/fs.h>

static PyObject *pyfs_dir_callable;
static PyObject *pyfs_open_callable;
static PyObject *pyfs_read_callable;

grub_err_t do_pyfs_dir(const char *path, int (*hook)(const char *filename, const struct grub_dirhook_info *info))
{
    PyObject *pyret;
    PyObject *iterator;
    PyObject *item;

    if (!pyfs_dir_callable)
        return GRUB_ERR_FILE_NOT_FOUND;

    pyret = PyObject_CallFunction(pyfs_dir_callable, "s", path);

    if (pyret == NULL) {
        PyErr_Print();
        return grub_error(GRUB_ERR_IO, "Internal error: Failed to call Python dir callback, or it threw an exception");
    }

    if (pyret == Py_None) {
        Py_DECREF(pyret);
        return GRUB_ERR_BAD_FILE_TYPE;
    }

    iterator = PyObject_GetIter(pyret);
    Py_DECREF(pyret);
    if (!iterator) {
        PyErr_Print();
        return grub_error(GRUB_ERR_IO, "Internal error: Python dir callback did not return a sequence");
    }

    while ((item = PyIter_Next(iterator))) {
        char *pyname;
        PyObject *pyisdir;
        if (!PyArg_ParseTuple(item, "sO", &pyname, &pyisdir)) {
            break;
        }

        {
            struct grub_dirhook_info info = {
                .dir = PyObject_IsTrue(pyisdir)
            };
            if (hook(pyname, &info))
                break;
        }
        Py_DECREF(item);
    }
    Py_XDECREF(item); /* If we broke out of the loop, handle the last item. */

    Py_DECREF(iterator);
    if (PyErr_Occurred()) {
        PyErr_Print();
        return grub_error(GRUB_ERR_IO, "Internal error: Python dir callback produced an error while iterating");
    }

    return GRUB_ERR_NONE;
}

grub_err_t do_pyfs_open(const char *name, grub_off_t *size)
{
    PyObject *pyret;
    Py_ssize_t pysize;

    if (!pyfs_open_callable)
        return GRUB_ERR_FILE_NOT_FOUND;

    pyret = PyObject_CallFunction(pyfs_open_callable, "s", name);

    if (pyret == NULL) {
        PyErr_Print();
        return grub_error(GRUB_ERR_IO, "Internal error: Failed to call Python open callback, or it threw an exception");
    }

    if (pyret == Py_None) {
        Py_DECREF(pyret);
        return GRUB_ERR_BAD_FILE_TYPE;
    }

    pysize = PyInt_AsSsize_t(pyret);
    Py_DECREF(pyret);
    if (pysize < 0) {
        if (PyErr_Occurred())
            PyErr_Print();
        return grub_error(GRUB_ERR_IO, "Internal error: Python open callback returned a bad or negative size");
    }

    *size = (grub_off_t)pysize;
    return GRUB_ERR_NONE;
}

grub_ssize_t do_pyfs_read(const char *name, grub_off_t offset, void *buf, grub_size_t len)
{
    PyObject *pyret;
    char *pybuf;
    Py_ssize_t pylen;

    if (!pyfs_read_callable)
        return -1;

    pyret = PyObject_CallFunction(pyfs_read_callable, "sKK", name, (unsigned long long)offset, (unsigned long long)len);

    if (pyret == NULL) {
        PyErr_Print();
        grub_error(GRUB_ERR_IO, "Internal error: Failed to call Python read callback, or it threw an exception");
        return -1;
    }
    if (!PyString_Check(pyret) || PyString_AsStringAndSize(pyret, &pybuf, &pylen) < 0) {
        if (PyErr_Occurred())
            PyErr_Print();
        Py_DECREF(pyret);
        grub_error(GRUB_ERR_IO, "Internal error: Python read callback returned a bad string");
        return -1;
    }
    if ((grub_off_t)pylen != len) {
        Py_DECREF(pyret);
        grub_error(GRUB_ERR_IO, "Internal error: Expected %llu bytes but Python read callback returned %llu", (unsigned long long)len, (unsigned long long)pylen);
        return -1;
    }

    grub_memcpy(buf, pybuf, pylen);
    Py_DECREF(pyret);
    return pylen;
}

static PyObject *set_pyfs_callbacks(PyObject *self, PyObject *args)
{
    PyObject *pyfs_dir_callable_temp, *pyfs_open_callable_temp, *pyfs_read_callable_temp;
    if (!PyArg_ParseTuple(args, "OOO:_set_pyfs_callbacks", &pyfs_dir_callable_temp, &pyfs_open_callable_temp, &pyfs_read_callable_temp))
        return NULL;

    if (!PyCallable_Check(pyfs_dir_callable_temp))
        return PyErr_Format(PyExc_TypeError, "expected a callable for pyfs_dir");
    if (!PyCallable_Check(pyfs_open_callable_temp))
        return PyErr_Format(PyExc_TypeError, "expected a callable for pyfs_open");
    if (!PyCallable_Check(pyfs_read_callable_temp))
        return PyErr_Format(PyExc_TypeError, "expected a callable for pyfs_read");

    Py_XDECREF(pyfs_dir_callable);
    Py_XINCREF(pyfs_dir_callable_temp);
    pyfs_dir_callable = pyfs_dir_callable_temp;

    Py_XDECREF(pyfs_open_callable);
    Py_XINCREF(pyfs_open_callable_temp);
    pyfs_open_callable = pyfs_open_callable_temp;

    Py_XDECREF(pyfs_read_callable);
    Py_XINCREF(pyfs_read_callable_temp);
    pyfs_read_callable = pyfs_read_callable_temp;

    return Py_BuildValue("");
}

PyDoc_STRVAR(set_pyfs_callbacks_doc,
"_set_pyfs_callbacks(pyfs_dir, pyfs_open, pyfs_read)\n"
"\n"
"Set the callbacks implementing the (python) filesystem.\n"
"These callbacks should be callables with the following signatures:\n"
"\n"
"pyfs_dir(dirname):\n"
"    return an iterable of (filename, is_directory) pairs, or None if\n"
"    not a directory\n"
"pyfs_open(filename):\n"
"    return the file size, or None if the file does not exist\n"
"pyfs_read(filename, offset, size):\n"
"    return size bytes starting at offset, as a string\n"
);

static PyMethodDef pyfsMethods[] = {
    {"_set_pyfs_callbacks", set_pyfs_callbacks, METH_VARARGS, set_pyfs_callbacks_doc},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC init_pyfs(void)
{
    (void) Py_InitModule("_pyfs", pyfsMethods);
}
