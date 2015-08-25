/*
Copyright (c) 2011, Intel Corporation
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

#include <grub/types.h>
#include <grub/disk.h>
#include <grub/dl.h>
#include <grub/env.h>
#include <grub/err.h>
#include <grub/extcmd.h>
#include <grub/misc.h>
#include <grub/fs.h>

GRUB_MOD_LICENSE("GPLv3+");
GRUB_MOD_DUAL_LICENSE("3-clause BSD");

static const struct grub_arg_option py_options_options[] = {
#undef OPTION_VERBOSE
#define OPTION_VERBOSE 0
    {"verbose", 'v', 0, "Set the Verbose level (default=0)\n"
     "    0 = No verbose details on module initialization or exit.\n"
     "    1 = Print a message each time a module is initialized, showing \n"
     "        the place (filename or built-in module) from which it is loaded.\n"
     "    2 = Print a message for each file that is checked for when searching\n"
     "        for a module. Also provides information on module cleanup at exit.",
     "NUM", ARG_TYPE_INT},
    {0, 0, 0, 0, 0, 0}
};

static grub_err_t grub_cmd_py_options(struct grub_extcmd_context *context, int argc, char **args)
{
    (void)argc;
    (void)args;

    if (context->state[OPTION_VERBOSE].set)
        Py_VerboseFlag = grub_strtoul(context->state[OPTION_VERBOSE].arg, NULL, 0);
    else
        grub_printf("Py_VerboseFlag = %u\n", Py_VerboseFlag);

    return GRUB_ERR_NONE;
}

static grub_err_t grub_cmd_py(grub_command_t cmd, int argc, char **args)
{
    (void)cmd;
    if (argc == 1)
        PyRun_SimpleString(args[0]);
    return GRUB_ERR_NONE;
}

static grub_err_t grub_cmd_python(grub_command_t cmd, int argc, char **args)
{
    (void)cmd;
    (void)argc;
    (void)args;
    grub_printf("Starting the Python interactive interpreter. Press Ctrl-D or Esc to exit.\n");
    PyRun_InteractiveLoop(stdin, "<stdin>");
    return GRUB_ERR_NONE;
}

static int pydisk_iterate(int (*hook)(const char *name), grub_disk_pull_t pull)
{
    if (pull != GRUB_DISK_PULL_NONE)
        return 0;

    if (hook("python"))
        return 1;
    return 0;
}

static grub_err_t pydisk_open(const char *name, grub_disk_t disk)
{
    if (grub_strcmp(name, "python") != 0)
        return grub_error(GRUB_ERR_UNKNOWN_DEVICE, "not a python disk");

    disk->data = grub_malloc(sizeof(unsigned char)); /* Just to get a unique ID */
    if (!disk->data)
        return grub_errno;

    disk->total_sectors = 0;
    disk->id = (unsigned long)disk->data;

    return GRUB_ERR_NONE;
}

static void pydisk_close(grub_disk_t disk)
{
    grub_free(disk->data);
}

static grub_err_t pydisk_read(grub_disk_t disk, grub_disk_addr_t sector, grub_size_t size, char *buf)
{
    (void)disk;
    (void)sector;
    (void)size;
    (void)buf;
    return GRUB_ERR_OUT_OF_RANGE;
}

static grub_err_t pydisk_write(grub_disk_t disk, grub_disk_addr_t sector, grub_size_t size, const char *buf)
{
    (void)disk;
    (void)sector;
    (void)size;
    (void)buf;
    return GRUB_ERR_OUT_OF_RANGE;
}

#define PYDISK_ID 0xB175 /* Avoid conflict with enum grub_disk_dev_id */

static struct grub_disk_dev pydisk = {
    .name = "python",
    .id = PYDISK_ID,
    .iterate = pydisk_iterate,
    .open = pydisk_open,
    .close = pydisk_close,
    .read = pydisk_read,
    .write = pydisk_write,
};

static grub_err_t pyfs_dir(grub_device_t device, const char *path,
                           int (*hook)(const char *filename, const struct grub_dirhook_info *info))
{
    if (device->disk->dev->id != PYDISK_ID)
        return grub_error(GRUB_ERR_BAD_FS, "not a python disk");

    return do_pyfs_dir(path, hook);
}

static grub_err_t pyfs_open(struct grub_file *file, const char *name)
{
    grub_err_t ret;

    if (file->device->disk->dev->id != PYDISK_ID)
        return grub_error(GRUB_ERR_IO, "not a python disk");

    ret = do_pyfs_open(name, &file->size);
    if (ret != GRUB_ERR_NONE)
        return ret;
    file->data = grub_strdup(name);
    if (!file->data)
        return GRUB_ERR_OUT_OF_MEMORY;
    return GRUB_ERR_NONE;
}

static grub_ssize_t pyfs_read(grub_file_t file, char *buf, grub_size_t len)
{
    return do_pyfs_read(file->data, file->offset, buf, len);
}

static grub_err_t pyfs_close(grub_file_t file)
{
    grub_free(file->data);
    return GRUB_ERR_NONE;
}

static struct grub_fs pyfs = {
    .name = "pyfs",
    .dir = pyfs_dir,
    .open = pyfs_open,
    .read = pyfs_read,
    .close = pyfs_close,
};

static grub_command_t cmd_py;
static grub_extcmd_t cmd_py_options;

GRUB_MOD_INIT(python)
{
    __asm__ __volatile__ ("finit");
    Py_DontWriteBytecodeFlag = 1;
    Py_NoSiteFlag = 1;
    Py_InspectFlag = 1;
    Py_Initialize();
    cmd_py = grub_register_command("python", grub_cmd_python, "\"Python interpreter\"", "Start the standard Python interpreter.");
    cmd_py = grub_register_command("py", grub_cmd_py, "\"Python program\"", "Evaluate Python given on the command line.");
    cmd_py_options = grub_register_extcmd("py_options", grub_cmd_py_options, 0,
                                          "[-v NUM]",
                                          "Set python options",
                                          py_options_options);
    grub_disk_dev_register(&pydisk);
    grub_fs_register(&pyfs);
}

GRUB_MOD_FINI(python)
{
    grub_fs_unregister(&pyfs);
    grub_disk_dev_unregister(&pydisk);
    grub_unregister_command(cmd_py);
    grub_unregister_extcmd(cmd_py_options);
    Py_Finalize();
}
