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

#include <grub/command.h>
#include <grub/datetime.h>
#include <grub/disk.h>
#include <grub/env.h>
#include <grub/partition.h>
#include <grub/term.h>
#include <grub/time.h>

#include "bitsmodule.h"
#include "datatype.h"

static PyObject *pyblocklist = NULL;
static grub_disk_addr_t partition_start_sector = 0;

static void NESTED_FUNC_ATTR disk_blocks_read_hook(grub_disk_addr_t sector, unsigned offset, unsigned length)
{
    PyObject *tuple;
    if (!pyblocklist)
        return;
    tuple = Py_BuildValue("(KII)", sector - partition_start_sector, offset, length);
    if (!tuple || PyList_Append(pyblocklist, tuple) == -1)
        Py_CLEAR(pyblocklist);
    Py_XDECREF(tuple);
}

static PyObject *bits_file_data_and_disk_blocks(PyObject *self, PyObject *args)
{
    PyObject *pyfile, *pystr;
    grub_file_t file;
    grub_ssize_t bytes_read;

    if (!PyArg_ParseTuple(args, "O!:file_data_and_disk_blocks", &PyFile_Type, &pyfile))
        return NULL;

    file = PyFile_AsFile(pyfile);
    if (!file->device->disk)
        return PyErr_Format(PyExc_RuntimeError, "Can't get disk blocks from non-disk-backed file");

    partition_start_sector = grub_partition_get_start(file->device->disk->partition);

    pyblocklist = PyList_New(0);
    if (!pyblocklist)
        return NULL;
    pystr = PyString_FromStringAndSize(NULL, grub_file_size(file));
    if (!pystr) {
        Py_CLEAR(pyblocklist);
        return NULL;
    }

    file->read_hook = disk_blocks_read_hook;
    bytes_read = grub_file_read(file, PyString_AsString(pystr), grub_file_size(file));
    file->read_hook = NULL;
    if ((grub_off_t)bytes_read != grub_file_size(file)) {
        Py_CLEAR(pyblocklist);
        Py_DECREF(pystr);
        return PyErr_Format(PyExc_RuntimeError, "Failed to read from file");
    }
    if (!pyblocklist) {
        Py_DECREF(pystr);
        return PyErr_NoMemory();
    }

    return Py_BuildValue("(NN)", pystr, pyblocklist);
}

static PyObject *bits_disk_read(PyObject *self, PyObject *args)
{
    PyObject *pyfile, *pystr;
    grub_file_t file;
    grub_disk_addr_t sector;
    unsigned offset, length;

    if (!PyArg_ParseTuple(args, "O!KII:disk_read", &PyFile_Type, &pyfile, &sector, &offset, &length))
        return NULL;

    file = PyFile_AsFile(pyfile);
    if (!file->device->disk)
        return PyErr_Format(PyExc_RuntimeError, "Can't get disk device from non-disk-backed file");

    pystr = PyString_FromStringAndSize(NULL, length);
    if (!pystr)
        return PyErr_NoMemory();

    if (grub_disk_read(file->device->disk, sector, offset, length, PyString_AsString(pystr)) != GRUB_ERR_NONE) {
        Py_DECREF(pystr);
        return PyErr_SetFromErrno(PyExc_IOError);
    }

    return pystr;
}

static PyObject *bits_disk_write(PyObject *self, PyObject *args)
{
    PyObject *pyfile;
    grub_file_t file;
    grub_disk_addr_t sector;
    const char *data;
    unsigned offset;
    int length;

    if (!PyArg_ParseTuple(args, "O!KIs#:disk_write", &PyFile_Type, &pyfile, &sector, &offset, &data, &length))
        return NULL;

    file = PyFile_AsFile(pyfile);
    if (!file->device->disk)
        return PyErr_Format(PyExc_RuntimeError, "Can't get disk device from non-disk-backed file");

    if (grub_disk_write(file->device->disk, sector, offset, length, data) != GRUB_ERR_NONE)
        return PyErr_SetFromErrno(PyExc_IOError);

    return Py_BuildValue("");
}

static PyObject *os_error_with_filename(int errno_val, const char *path)
{
    errno = errno_val;
    PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    errno = 0;
    return NULL;
}

static PyObject *bits__getenv(PyObject *self, PyObject *args)
{
    const char *key, *default_value = NULL;
    const char *value;
    if (!PyArg_ParseTuple(args, "s|s:getenv", &key, &default_value))
        return NULL;
    value = grub_env_get(key);
    return Py_BuildValue("s", value ? value : default_value);
}

static PyObject *getenvdict_result;

static int getenvdict_callback(struct grub_env_var *var)
{
    const char *value = var->read_hook ? var->read_hook(var, var->value) : var->value;
    PyDict_SetItem(getenvdict_result, PyString_FromString(var->name), PyString_FromString(value));
    return 0;
}

static PyObject *bits__getenvdict(PyObject *self, PyObject *args)
{
    PyObject *result;
    getenvdict_result = PyDict_New();
    grub_env_iterate(getenvdict_callback);
    result = getenvdict_result;
    getenvdict_result = NULL;
    return result;
}

static PyObject *listdir_result;

static int listdir_callback(const char *filename, const struct grub_dirhook_info *info)
{
    PyObject *path;
    if (strcmp(filename, ".") == 0 || strcmp(filename, "..") == 0)
        return 0;
    path = Py_BuildValue("s", filename);
    PyList_Append(listdir_result, path);
    Py_XDECREF(path);
    return 0;
}

static PyObject *bits__listdir(PyObject *self, PyObject *args)
{
    PyObject *result;
    const char *path;
    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;
    if (!is_directory(path))
        return os_error_with_filename(ENOTDIR, path);

    listdir_result = PyList_New(0);
    iterate_directory(path, listdir_callback);
    result = listdir_result;
    listdir_result = NULL;
    return result;
}

static PyObject *bits__localtime(PyObject *self, PyObject *args)
{
    struct grub_datetime datetime;
    int weekday;
    PyObject *seconds = NULL;

    if (!PyArg_ParseTuple(args, "|O", &seconds))
        return NULL;

    if (!seconds || seconds == Py_None)
        grub_get_datetime(&datetime);
    else {
        long s = PyFloat_AsDouble(seconds);
        if (PyErr_Occurred())
            return NULL;
        grub_unixtime2datetime(s, &datetime);
    }

    // Get weekday and convert from Sunday=0 to Monday=0
    weekday = (grub_get_weekday(&datetime) + 6) % 7;

    return Py_BuildValue("HBBBBBiii", datetime.year, datetime.month,
                                      datetime.day, datetime.hour,
                                      datetime.minute, datetime.second,
                                      weekday, -1, -1);
}

static char *memory_keywords[] = { "address", "length", "writable", NULL };

static PyObject *bits_memory(PyObject *self, PyObject *args, PyObject *keywds)
{
    unsigned long address;
    Py_ssize_t length;
    PyObject *writable_obj = NULL;
    int writable = 0;

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "kn|O:memory", memory_keywords, &address, &length, &writable_obj))
        return NULL;
    if (writable_obj) {
        writable = PyObject_IsTrue(writable_obj);
        if (writable < 0)
            return NULL;
    }

    return (writable ? PyBuffer_FromReadWriteMemory : PyBuffer_FromMemory)((void *)address, length);
}

static PyObject *bits_memory_addr(PyObject *self, PyObject *args)
{
    PyObject *mem;
    void *addr;
    if (!PyArg_ParseTuple(args, "O!:memory_addr", &PyBuffer_Type, &mem))
        return NULL;
    if (mem->ob_type->tp_as_buffer->bf_getreadbuffer(mem, 0, &addr) == -1)
        return NULL;
    return Py_BuildValue("k", (unsigned long)addr);
}

static PyObject *bits__putenv(PyObject *self, PyObject *args)
{
    const char *key, *value;
    if (!PyArg_ParseTuple(args, "ss:putenv", &key, &value))
        return NULL;
    if (grub_env_set(key, value) != GRUB_ERR_NONE || grub_env_export(key) != GRUB_ERR_NONE)
        return PyErr_SetFromErrno(PyExc_OSError);
    return Py_BuildValue("");
}

static PyObject *bits__stat(PyObject *self, PyObject *args)
{
    const char *path;
    struct stat st;
    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;
    if (stat(path, &st) < 0)
        return os_error_with_filename(ENOENT, path);
    return Py_BuildValue("(I,K)", st.st_mode, st.st_size);
}

static PyObject *bits__time(PyObject *self, PyObject *args)
{
    return Py_BuildValue("d", grub_get_time_ms() / 1000.0);
}

static PyObject *bits__unsetenv(PyObject *self, PyObject *args)
{
    const char *key;
    if (!PyArg_ParseTuple(args, "s:unsetenv", &key))
        return NULL;
    grub_env_unset(key);
    return Py_BuildValue("");
}

static PyObject *grub_command_callback;

static grub_err_t grub_cmd_pydispatch(grub_command_t cmd, int argc, char **args)
{
    PyObject *pyargs, *pyret;
    grub_err_t ret;
    unsigned ndx;

    pyargs = PyList_New(argc+1);
    if (!pyargs)
        return GRUB_ERR_OUT_OF_MEMORY;

    PyList_SET_ITEM(pyargs, 0, PyString_FromString(cmd->name));
    for (ndx = 0; ndx < argc; ndx++)
        PyList_SET_ITEM(pyargs, ndx+1, PyString_FromString(args[ndx]));

    pyret = PyObject_CallFunctionObjArgs(grub_command_callback, pyargs, NULL);
    Py_DECREF(pyargs);

    if (pyret == NULL)
        return grub_error(GRUB_ERR_IO, "Internal error: Failed to call Python command callback, or it threw an exception");

    if (pyret == Py_None || PyObject_IsTrue(pyret))
        ret = GRUB_ERR_NONE;
    else
        ret = GRUB_ERR_TEST_FAILURE;
    Py_DECREF(pyret);

    return ret;
}

static PyObject *bits_register_grub_command(PyObject *self, PyObject *args)
{
    const char *cmd, *summary, *description;
    char *cmd_copy, *summary_copy, *description_copy;

    if (!grub_command_callback)
        return PyErr_Format(PyExc_RuntimeError, "Internal error: attempted to register grub command before setting callback.");

    if (!PyArg_ParseTuple(args, "sss:register_grub_command", &cmd, &summary, &description))
        return NULL;

    cmd_copy = grub_strdup(cmd);
    summary_copy = grub_strdup(summary);
    description_copy = grub_strdup(description);
    if (!cmd_copy || !summary_copy || !description_copy) {
        grub_free(cmd_copy);
        grub_free(summary_copy);
        grub_free(description_copy);
        return PyErr_NoMemory();
    }

    grub_register_command(cmd_copy, grub_cmd_pydispatch, summary_copy, description_copy);

    return Py_BuildValue("");
}

static PyObject *bits_set_grub_command_callback(PyObject *self, PyObject *args)
{
    PyObject *callable;
    if (!PyArg_ParseTuple(args, "O:set_grub_command_callback", &callable))
        return NULL;

    if (!PyCallable_Check(callable))
        return PyErr_Format(PyExc_TypeError, "expected a callable");

    Py_XDECREF(grub_command_callback);
    Py_XINCREF(callable);
    grub_command_callback = callable;

    return Py_BuildValue("");
}

static PyObject *readline_callback;

/* Note that this always assumes in and out are sys.stdin and sys.stdout. */
static char *bits_readline_function(FILE *in, FILE *out, char *prompt)
{
    PyObject *pyret;
    Py_ssize_t len;
    char *temp;
    char *ret;

    (void)in;
    (void)out;

    pyret = PyObject_CallFunction(readline_callback, "s", prompt);

    if (!pyret)
        return NULL;
    if (!PyString_Check(pyret)) {
        PyErr_Format(PyExc_TypeError, "Python readline callback returned a non-string");
        return NULL;
    }
    temp = PyString_AsString(pyret);
    if (!temp)
        return NULL;
    len = PyString_Size(pyret);
    ret = PyMem_Malloc(len+1);
    if (!ret) {
        PyErr_NoMemory();
        return NULL;
    }
    return memcpy(ret, temp, len+1);
}

static PyObject *bits_set_readline_callback(PyObject *self, PyObject *args)
{
    PyObject *callable;
    if (!PyArg_ParseTuple(args, "O:set_readline_callback", &callable))
        return NULL;

    if (callable == Py_None) {
        PyOS_ReadlineFunctionPointer = NULL;
        Py_XDECREF(readline_callback);
        readline_callback = Py_BuildValue("");
        return Py_BuildValue("");
    }

    if (!PyCallable_Check(callable))
        return PyErr_Format(PyExc_TypeError, "expected a callable");

    Py_XDECREF(readline_callback);
    Py_XINCREF(callable);
    readline_callback = callable;
    PyOS_ReadlineFunctionPointer = bits_readline_function;

    return Py_BuildValue("");
}

static PyObject *bits_get_key(PyObject *self, PyObject *args)
{
    return Py_BuildValue("i", grub_getkey());
}

static PyObject *bits_clear_screen(PyObject *self, PyObject *args)
{
    grub_cls();
    return Py_BuildValue("");
}

/* GRUB keeps terminals in a linked list, and this family of functions exposes
 * them via an index.  That makes the resulting Python code O(N^2), but since N
 * is generally no more than 2... */
static PyObject *bits_get_term_count(PyObject *self, PyObject *args)
{
    grub_term_output_t term;
    unsigned count = 0;

    FOR_ACTIVE_TERM_OUTPUTS(term)
        count++;

    return Py_BuildValue("I", count);
}

static char *term_keyword[] = {"term", NULL};

static PyObject *bits_get_width_height(PyObject *self, PyObject *args, PyObject *keywds)
{
    unsigned term_num = 0;
    unsigned current = 0;
    grub_term_output_t term;

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "I", term_keyword, &term_num))
        return NULL;

    FOR_ACTIVE_TERM_OUTPUTS(term) {
        if (current == term_num) {
            U16 temp = term->getwh(term);
            return Py_BuildValue("BB", (temp >> 8) & 0xff, temp & 0xff);
        }
        current++;
    }

    return PyErr_Format(PyExc_ValueError, "term (%u) must be less than %u.", term_num, current);
}

static PyObject *bits_get_xy(PyObject *self, PyObject *args, PyObject *keywds)
{
    unsigned term_num;
    unsigned current = 0;
    grub_term_output_t term;

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "I", term_keyword, &term_num))
        return NULL;

    FOR_ACTIVE_TERM_OUTPUTS(term) {
        if (current == term_num) {
            U16 temp = term->getxy(term);
            return Py_BuildValue("BB", (temp >> 8) & 0xff, temp & 0xff);
        }
        current++;
    }

    return PyErr_Format(PyExc_ValueError, "term (%u) must be less than %u.", term_num, current);
}

static char *xy_keywords[] = {"x", "y", "term", NULL};

static PyObject *bits_goto_xy(PyObject *self, PyObject *args, PyObject *keywds)
{
    unsigned term_num;
    unsigned current = 0;
    grub_term_output_t term;
    U8 x, y;

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "BBI", xy_keywords, &x, &y, &term_num))
        return NULL;

    FOR_ACTIVE_TERM_OUTPUTS(term) {
        if (current == term_num) {
            term->gotoxy(term, x, y);
            return Py_BuildValue("");
        }
        current++;
    }

    return PyErr_Format(PyExc_ValueError, "term (%u) must be less than %u.", term_num, current);
}

static char *puts_keywords[] = {"str", "term", NULL};

static PyObject *bits_puts(PyObject *self, PyObject *args, PyObject *keywds)
{
    unsigned term_num;
    unsigned current = 0;
    grub_term_output_t term;
    char *str;

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "sI", puts_keywords, &str, &term_num))
        return NULL;

    FOR_ACTIVE_TERM_OUTPUTS(term) {
        if (current == term_num) {
            grub_puts_terminal(str, term);
            return Py_BuildValue("");
        }
        current++;
    }

    return PyErr_Format(PyExc_ValueError, "term (%u) must be less than %u.", term_num, current);
}

static PyMethodDef bitsMethods[] = {
    {"clear_screen", bits_clear_screen, METH_NOARGS, "clear_screen() -> clear the screen"},
    {"disk_read", (PyCFunction)bits_disk_read, METH_VARARGS, "disk_read(file, sector, offset, length) -> data. Uses file to identify disk."},
    {"disk_write", (PyCFunction)bits_disk_write, METH_VARARGS, "disk_write(file, sector, offset, data). Uses file to identify disk."},
    {"file_data_and_disk_blocks", (PyCFunction)bits_file_data_and_disk_blocks, METH_VARARGS, "file_data_and_disk_blocks(file) -> (data, [(sector, offset, length), ...])"},
    {"_getenv",  bits__getenv, METH_VARARGS, "_getenv(key, default=None) -> value of environment variable \"key\", or default if it doesn't exist"},
    {"_getenvdict",  bits__getenvdict, METH_NOARGS, "_getenvdict() -> environment dictionary"},
    {"_get_key", bits_get_key, METH_NOARGS, "_get_key() -> keycode"},
    {"get_term_count", bits_get_term_count, METH_NOARGS, "get_term_count() -> number of terminals"},
    {"get_width_height", (PyCFunction)bits_get_width_height, METH_KEYWORDS, "get_width_height(term) -> (width, height)" },
    {"get_xy", (PyCFunction)bits_get_xy, METH_KEYWORDS, "get_xy(term) -> (cursor_x, cursor_y)"},
    {"goto_xy", (PyCFunction)bits_goto_xy, METH_KEYWORDS, "goto_xy(x, y, term)) -> position cursor at these coordinates"},
    {"_listdir",  bits__listdir, METH_VARARGS, "_listdir() -> list of pathnames"},
    {"_localtime", bits__localtime, METH_VARARGS, "_localtime([seconds]) -> tuple (internal implementation details of localtime)"},
    {"memory", (PyCFunction)bits_memory, METH_KEYWORDS, "memory(address, length[, writable=False]) -> buffer"},
    {"memory_addr", bits_memory_addr, METH_VARARGS, "memory_addr(mem) -> address of mem, which must have been returned by bits.memory"},
    {"puts", (PyCFunction)bits_puts, METH_KEYWORDS, "puts(string, term)) -> puts string to specified terminal"},
    {"_putenv",  bits__putenv, METH_VARARGS, "_putenv(key, value): Set an environment variable"},
    {"_register_grub_command", bits_register_grub_command, METH_VARARGS, "register_grub_command(name, summary, description)"},
    {"_set_grub_command_callback", bits_set_grub_command_callback, METH_VARARGS, "set_grub_command_callback(callable)"},
    {"_set_readline_callback", bits_set_readline_callback, METH_VARARGS, "_set_readline_callback(callable)"},
    {"_stat", bits__stat, METH_VARARGS, "_stat(path) -> tuple (internal implementation details of stat)"},
    {"_time", bits__time, METH_NOARGS, "_time() -> time in seconds (accurate for relative use only)"},
    {"_unsetenv",  bits__unsetenv, METH_VARARGS, "_unsetenv(key): Unset an environment variable"},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC init_bits(void)
{
    (void) Py_InitModule("_bits", bitsMethods);
}
