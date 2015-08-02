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

#include <grub/extcmd.h>
#include <grub/types.h>
#include <grub/misc.h>
#include <grub/time.h>
#include <grub/mm.h>
#include <grub/err.h>
#include <grub/dl.h>
#include <grub/file.h>
#include "datatype.h"
#include "smp.h"
#include "mcu.h"

GRUB_MOD_LICENSE("GPLv3+");
GRUB_MOD_DUAL_LICENSE("3-clause BSD");

typedef struct buffer_info {
    void *buf;
    U32 bufsize;
} BUFFER_INFO;

typedef enum exit_code {
    EXIT_CODE_FAILURE = 0,
    EXIT_CODE_SUCCESS = 1,
    EXIT_CODE_ERROR_TOTAL_SIZE_FIELD = 2,
    EXIT_CODE_ERROR_EXTENDED_SIGNATURE_CHECKUM = 3,
    EXIT_CODE_EXTENDED_SIGNATURE_HEADER_CHECKSUM = 4,
} EXIT_CODE;

typedef struct update_cpu_options {
    const BUFFER_INFO *buf_info;
    PROC_INFO *proc_info;
    UPDATE_INFO *update_info;
    U32 return_status; // Uses EXIT_CODE
    U32 action; // 1 = mcu load, 0 = no load mcu
    U32 revision_check; // 1 = force revision check, 0 = no revision check
} UPDATE_CPU_OPTIONS;

typedef struct find_update_options {
    const BUFFER_INFO *buf_info;
    PROC_INFO *proc_info;
    UPDATE_INFO *update_info;
    U32 return_status; // Uses EXIT_CODE
} FIND_UPDATE_OPTIONS;

typedef struct msr_regs {
    U32 num;
    U64 value;
    U32 status;
} MSR_REGS;

static const struct grub_arg_option options[] = {
#define OPTION_VERBOSE 0
    {"verbose", 'v', 0, "Verbose output (default=disabled)", 0, 0},
    {0, 0, 0, 0, 0, 0}
};

struct {
    BUFFER_INFO *buf_info;
    grub_file_t file;

} clean_info;

static int verbose;

static U32 ncpus;

// Forward declarations and prototypes
static grub_err_t WriteUpdatesToCpus(int action, const BUFFER_INFO * const buf_info, const CPU_INFO * const cpu);
static void updateCpuCallBack(void *param);
static void GetProcInfoCallBack(void *param);
static void FindUpdateCallBack(void *param);
static U32 ChecksumMem(U32 * ptr, const U32 byte_count);
static int GenuineIntel(void);
void read_msr(void *param);
void write_msr(void *param);

static grub_err_t do_microcode(int action, struct buffer_info buf_info)
{
    const CPU_INFO *cpu;

    if (!GenuineIntel())
        return grub_error(GRUB_ERR_IO, "Don't know how to load microcode on non-Intel CPUs");

    ncpus = smp_init();
    if (!ncpus)
        return grub_error(GRUB_ERR_IO, "Failed to initialize SMP");

    grub_dprintf("mcu", "Number of logical processors = %u\n", ncpus);

    cpu = smp_read_cpu_list();
    if (!cpu)
        grub_dprintf("mcu", "Failed smp_read_cpu_list()\n");

    return WriteUpdatesToCpus(action, &buf_info, cpu);
}

static void iterate_directory(const char *dirname, int (*callback)(const char *filename, const struct grub_dirhook_info *info))
{
    char *device_name = grub_file_get_device_name(dirname);
    grub_device_t device = grub_device_open(device_name);
    if (device) {
        grub_fs_t fs = grub_fs_probe(device);
        if (fs)
            fs->dir(device, dirname, callback);
        grub_device_close(device);
    }
    grub_free(device_name);
}

static const char *is_directory_filename;
static bool is_directory_result;

static int is_directory_callback(const char *filename, const struct grub_dirhook_info *info)
{
    if ((info->case_insensitive ? grub_strcasecmp : grub_strcmp)(is_directory_filename, filename) == 0) {
        is_directory_result = !!info->dir;
        return 1;
    }
    return 0;
}

static bool is_directory(const char *filename)
{
    char *basename;
    char *dirname;
    char *copy = grub_strdup(filename);

    if (!copy)
        return false;
    dirname = copy;
    while (dirname[grub_strlen(dirname) - 1] == '/')
        dirname[grub_strlen(dirname) - 1] = '\0';
    basename = grub_strrchr(dirname, '/');
    if (basename)
        *basename++ = '\0';
    else
        basename = "/";
    if (*dirname == '\0')
        dirname = "/";

    is_directory_filename = basename;
    is_directory_result = false;
    iterate_directory(dirname, is_directory_callback);

    grub_free(copy);
    return is_directory_result;
}

static grub_off_t get_file_size(const char *filename)
{
    grub_off_t size;
    grub_file_t file = grub_file_open(filename);
    if (!file) {
        grub_error(GRUB_ERR_FILE_READ_ERROR, "Failed to open file: %s", filename);
        return 0;
    }
    size = grub_file_size(file);
    grub_file_close(file);
    return size;
}

static const char *accumulate_size_dirname;
static U32 accumulate_size_result;
static U32 accumulate_size_max;

static int accumulate_size_callback(const char *filename, const struct grub_dirhook_info *info)
{
    if (!info->dir) {
        U32 file_size;
        char *full_filename = grub_xasprintf("%s/%s", accumulate_size_dirname, filename);
        file_size = get_file_size(full_filename);
        grub_free(full_filename);
        accumulate_size_result += file_size;
        accumulate_size_max = file_size > accumulate_size_max ? file_size : accumulate_size_max;
    }
    return 0;
}

static grub_off_t parse_microcode(const char *filename, void *buf, void *filebuf)
{
    grub_file_t file;
    grub_ssize_t bytes_read;
    grub_off_t file_size;
    U32 i;
    char *current, *end;
    U32 *out;

    file = grub_file_open(filename);
    if (!file) {
        grub_error(GRUB_ERR_FILE_READ_ERROR, "Failed to open file: %s", filename);
        return 0;
    }

    file_size = grub_file_size(file);
    bytes_read = grub_file_read(file, filebuf, file_size);
    if (bytes_read < 0 || (grub_off_t) bytes_read != file_size) {
        grub_error(GRUB_ERR_FILE_READ_ERROR, "Couldn't read file: %s", filename);
        grub_file_close(file);
        return 0;
    }

    grub_file_close(file);

    grub_dprintf("mcu", "Reading microcode from \"%s\"\n", filename);

    /* If we have any '\0's in the first 48-byte header, assume binary; otherwise assume text. */
    for (i = 0; i < 48; i++)
        if (((char *)filebuf)[i] == '\0') {
            grub_memcpy(buf, filebuf, file_size);
            return file_size;
        }

    grub_dprintf("mcu", "\"%s\" doesn't smell like binary; assuming text\n", filename);

    current = filebuf;
    current[file_size] = '\0';
    end = filebuf;
    end += file_size;
    out = buf;
    while (current < end) {
        switch (*current) {
        case ';':
        case '/':
            while (current < end && *current != '\r' && *current != '\n')
                current++;
            break;

            /* "dd " would parse as a hex number if not special-cased */
        case 'd':
        case 'D':
            if (current + 2 < end && (current[1] == 'd' || current[1] == 'D') && current[2] == ' ')
                current += 3;
            /* Fall through */

        default:
            {
                U32 value;
                char *value_end;

                grub_errno = GRUB_ERR_NONE;
                value = grub_strtoul(current, &value_end, 16);
                if (grub_errno != GRUB_ERR_NONE) {
                    grub_errno = GRUB_ERR_NONE;
                    current++;
                    break;
                }
                current = value_end;
                if (((char *)out + 4) > ((char *)buf + file_size)) {
                    grub_error(GRUB_ERR_IO, "Failed to parse text microcode: got more binary data than the size of the text file");
                    return 0;
                }
                *out++ = value;
                break;
            }
        }
    }

    grub_dprintf("mcu", "Read text microcode from \"%s\" and converted into %u bytes of binary microcode\n", filename, (char *)out - (char *)buf);

    return (char *)out - (char *)buf;
}

static const char *parse_microcode_dirname;
static void *parse_microcode_buf;
static void *parse_microcode_filebuf;
static U32 parse_microcode_result;

static int parse_microcode_callback(const char *filename, const struct grub_dirhook_info *info)
{
    if (!info->dir) {
        char *full_filename = grub_xasprintf("%s/%s", parse_microcode_dirname, filename);
        parse_microcode_result += parse_microcode(full_filename, (char *)parse_microcode_buf + parse_microcode_result, parse_microcode_filebuf);
        grub_free(full_filename);
    }
    return 0;
}

static struct buffer_info parse_microcodes(int argc, char **args)
{
    struct buffer_info buf_info = { .buf = NULL, .bufsize = 0 };
    void *filebuf = NULL;
    int i;
    U32 bufsize = 0;
    U32 maxsize = 0; /* Remember the largest file size, to allocate filebuf. */

    for (i = 0; i < argc; i++) {
        char *filename = args[i];
        bool dir = is_directory(filename);
        U32 file_size;

        if (grub_errno != GRUB_ERR_NONE)
            return buf_info;

        if (dir) {
            accumulate_size_dirname = filename;
            accumulate_size_result = 0;
            accumulate_size_max = 0;
            iterate_directory(filename, accumulate_size_callback);
            if (grub_errno != GRUB_ERR_NONE)
                return buf_info;
            bufsize += accumulate_size_result;
            maxsize = accumulate_size_max > maxsize ? accumulate_size_max : maxsize;
            continue;
        }

        file_size = get_file_size(filename);
        bufsize += file_size;
        maxsize = file_size > maxsize ? file_size : maxsize;
        if (grub_errno != GRUB_ERR_NONE)
            return buf_info;
    }

    if (bufsize == 0)
        return buf_info;

    filebuf = grub_malloc(maxsize + 1); /* + 1 for a '\0' on the end to simplify use of strtoul */
    buf_info.buf = grub_malloc(bufsize);
    if (!filebuf || !buf_info.buf) {
        grub_error(GRUB_ERR_OUT_OF_MEMORY, "Failed to allocate memory for %u bytes of microcode data", bufsize);
        grub_free(filebuf);
        return buf_info;
    }

    for (i = 0; i < argc; i++) {
        char *filename = args[i];
        bool dir = is_directory(filename);

        if (grub_errno != GRUB_ERR_NONE) {
            grub_free(filebuf);
            return buf_info;
        }

        if (dir) {
            parse_microcode_dirname = filename;
            parse_microcode_buf = (char *)buf_info.buf + buf_info.bufsize;
            parse_microcode_filebuf = filebuf;
            parse_microcode_result = 0;
            iterate_directory(filename, parse_microcode_callback);
            if (grub_errno != GRUB_ERR_NONE) {
                grub_free(filebuf);
                return buf_info;
            }
            buf_info.bufsize += parse_microcode_result;
            continue;
        }

        buf_info.bufsize += parse_microcode(filename, (char *)buf_info.buf + buf_info.bufsize, filebuf);
        if (grub_errno != GRUB_ERR_NONE) {
            grub_free(filebuf);
            return buf_info;
        }
    }

    grub_free(filebuf);
    return buf_info;
}

static void free_buffer_info(struct buffer_info buf_info)
{
    grub_free(buf_info.buf);
}

static grub_err_t grub_cmd_mcu_load(struct grub_extcmd_context *context, int argc, char **args)
{
    grub_err_t ret;
    struct buffer_info buf_info;
    struct grub_arg_list *state = context->state;
    verbose = state[OPTION_VERBOSE].set;

    buf_info = parse_microcodes(argc, args);
    if (buf_info.bufsize == 0)
        return grub_error(GRUB_ERR_BAD_ARGUMENT, "No microcodes available");

    ret = do_microcode(1, buf_info);

    free_buffer_info(buf_info);

    return ret;
}

static grub_err_t grub_cmd_mcu_status(struct grub_extcmd_context *context, int argc, char **args)
{
    grub_err_t ret;
    struct buffer_info buf_info;
    struct grub_arg_list *state = context->state;
    verbose = state[OPTION_VERBOSE].set;

    buf_info = parse_microcodes(argc, args);

    ret = do_microcode(0, buf_info);

    free_buffer_info(buf_info);

    return ret;
}

static grub_extcmd_t cmd1;
static grub_extcmd_t cmd2;

GRUB_MOD_INIT(mcu)
{
    cmd1 = grub_register_extcmd("mcu_load", grub_cmd_mcu_load, 0,
                                "[-v] [file | directory]...",
                                "Find and load microcode update.",
                                options);
    cmd2 = grub_register_extcmd("mcu_status", grub_cmd_mcu_status, 0,
                                "[-v] [file | directory]...",
                                "Show CPU microcode status.",
                                options);
}

GRUB_MOD_FINI(mcu)
{
    grub_unregister_extcmd(cmd1);
    grub_unregister_extcmd(cmd2);
}

// GenuineIntel()
// Returns: 0 = Failure 1 = Success
// Description:
//    This program should not run on NON-Intel processors.
//    This function executes CPUID(eax=0) and compares the string returned
//    in the 3 processor registers (EBX, EDX, ECX) with 'GenuineIntel'.
//    Success is returned if they match.  Otherwise failure is returned.
static int GenuineIntel(void)
{
    U32 eax, ebx, ecx, edx;

    cpuid32(0, &eax, &ebx, &ecx, &edx);

    return ebx == 0x0756E6547 && ecx == 0x06C65746E && edx == 0x049656E69;
}

/********************************************************************/
//* Routine Description: void ChecksumMem()
//* This function performs a dword checksum on the memory data.
//* The memory is accessed as dwords.
//*
//* Parameters:
//* ptr - pointer to memory block to checksum
//* byte_count - count of bytes in memory to checksum
//*
//* Return Value:
//* Dword checksum of memory
/********************************************************************/
static U32 ChecksumMem(U32 * ptr, const U32 byte_count)
{
    U32 i;
    U32 sum = 0;

    for (i = 0; i < (byte_count / sizeof(U32)); i++)
        sum += ptr[i];

    return (sum);
}

static void PrintHeaderRow(void)
{
    if (verbose)
        grub_printf("ApicID   | Signature| PlatformID| Prev Rev | Avail Rev | New Rev\n");
}

static void PrintProcInfo(const PROC_INFO * const before, const UPDATE_INFO * const update, const PROC_INFO * const after)
{
    if (!verbose)
        return;

    grub_printf("%08x", before->apic_id);
    grub_printf(" | %08x", before->signature);
    grub_printf(" | %08x ", before->platform_id);
    grub_printf(" | %08x", before->ucode_rev);
    if (update->valid)
        grub_printf(" | %08x ", update->revision);
    else
        grub_printf(" | %-8s ", "None");
    grub_printf(" | %08x \n", after->ucode_rev);
}

typedef struct unique {
    U32 count;
    U32 signature;
    U32 platform_id;
    U32 before_rev;
    U32 update_valid;
    U32 update_rev;
    U32 after_rev;
} UNIQUE;

static grub_err_t WriteUpdatesToCpus(int action, const BUFFER_INFO * const buf_info, const CPU_INFO * const cpu)
{
    U32 i;
    U32 j;
    U32 replaced = 0;
    U32 RevisionCheckEnable = 1;
    UNIQUE *unique;
    U32 unique_count = 0;

    grub_dprintf("mcu", "[Operation] Write updates directly to processors\n");
    grub_dprintf("mcu", "buf_info.bufsize = %d\n", buf_info->bufsize);

    unique = grub_zalloc(ncpus * sizeof(*unique));
    if (!unique)
        return grub_error(GRUB_ERR_OUT_OF_MEMORY, "Out of memory");

    PrintHeaderRow();

    for (i = 0; i < ncpus; i++) {
        PROC_INFO proc_info;
        PROC_INFO new_proc_info;
        UPDATE_INFO update_info;
        UPDATE_CPU_OPTIONS update_opt;

        update_opt.buf_info = buf_info;
        update_opt.proc_info = &proc_info;
        update_opt.proc_info->apic_id = cpu[i].apicid;
        update_opt.update_info = &update_info;
        update_opt.action = action;
        update_opt.revision_check = RevisionCheckEnable;
        smp_function(cpu[i].apicid, updateCpuCallBack, &update_opt);
        smp_function(cpu[i].apicid, GetProcInfoCallBack, &new_proc_info);

        if (proc_info.ucode_rev != new_proc_info.ucode_rev)
            replaced++;

        PrintProcInfo(&proc_info, &update_info, &new_proc_info);

        {
            int found = 0;
            for (j = 0; j < unique_count; j++) {
                if ((unique[j].signature == proc_info.signature) &&
                    (unique[j].platform_id == proc_info.platform_id) &&
                    (unique[j].before_rev == proc_info.ucode_rev) &&
                    (unique[j].update_rev == update_info.revision) &&
                    (unique[j].after_rev == new_proc_info.ucode_rev)) {
                    unique[j].count++;
                    found = 1;
                    break;
                }
            }
            if (!found) {
                unique[unique_count].count = 1;
                unique[unique_count].signature = proc_info.signature;
                unique[unique_count].platform_id = proc_info.platform_id;
                unique[unique_count].before_rev = proc_info.ucode_rev;
                unique[unique_count].update_valid = update_info.valid;
                unique[unique_count].update_rev = update_info.revision;
                unique[unique_count].after_rev = new_proc_info.ucode_rev;
                unique_count++;
            }
        }
    }

    grub_printf("Count | Signature| PlatformID| Prev Rev | Avail Rev | New Rev  | Status\n");
    for (j = 0; j < unique_count; j++) {
        grub_printf("%-5u", unique[j].count);
        grub_printf(" | %08x", unique[j].signature);
        grub_printf(" | %08x ", unique[j].platform_id);
        grub_printf(" | %08x", unique[j].before_rev);
        if (unique[j].update_valid)
            grub_printf(" | %08x ", unique[j].update_rev);
        else
            grub_printf(" | %-8s ", "None");
        grub_printf(" | %08x", unique[j].after_rev);
        grub_printf(" | %-9s\n", unique[j].before_rev == unique[j].after_rev ? "No Change" : "Updated");
    }
    grub_printf("Replaced microcode on %u of %u CPUs.\n", replaced, ncpus);

    grub_free(unique);

    return GRUB_ERR_NONE;
}

static void updateCpuCallBack(void *param)
{
    UPDATE_CPU_OPTIONS *opt = param;
    FIND_UPDATE_OPTIONS find_update_opt;

    // Get cpu information
    GetProcInfoCallBack(opt->proc_info);

    {
        find_update_opt.buf_info = opt->buf_info;
        find_update_opt.proc_info = opt->proc_info;
        find_update_opt.update_info = opt->update_info;
        find_update_opt.update_info->valid = false;
        FindUpdateCallBack(&find_update_opt);
        opt->return_status = find_update_opt.return_status;
    }

    if (find_update_opt.update_info->valid) {
        // Two conditions for microcode update load into cpu are as follows:
        // (1) Revision check is disabled
        // (2) Revision check specified by BWG is satisfied

        // Revision check algorithm from the BWG
        // Z = Revision from microcode update header
        // X = Revision currently in processor (MSR 8Bh[63:32])
        // IF ((Z < 0) OR ((Z > 0) AND (Z > X)))
        // THEN load microcode
        // Else do nothing

        signed long z = (signed long)find_update_opt.update_info->revision;
        signed long x = (signed long)opt->proc_info->ucode_rev;

        if (!opt->revision_check || ((z < 0) || ((z > 0) && (z > x)))) {
            if (opt->action) {
                // Load Microcode
                MSR_REGS msr_regs;
                msr_regs.num = 0x79;
                msr_regs.value = (U32) opt->buf_info->buf + opt->update_info->offset + sizeof(pep_hdr_t);

                write_msr(&msr_regs);
            }
        }
    }
}

static void FindUpdateCallBack(void *param)
{
    FIND_UPDATE_OPTIONS *opt = param;
    void *current = (void *)opt->buf_info->buf;
    void *end = (U8 *) opt->buf_info->buf + opt->buf_info->bufsize;
    pep_hdr_t *pep_hdr;
    ext_sig_hdr_t *ext_sig_hdr;
    ext_sig_t *ext_sig;
    bool found = false;
    U32 len;
    U32 i;
    U32 data_csum;
    U32 ext_sig_hdr_csum;
    U32 partial_csum;
    U32 update_offset;

    while ((U8 *) current < (U8 *) end) {
        pep_hdr = current;
        update_offset = (U32) current - (U32) opt->buf_info->buf;
        current = (U8 *) current + sizeof(pep_hdr_t);

        len = (pep_hdr->data_size == 0) ? 2000 : pep_hdr->data_size;

        current = (U8 *) current + len;
        if (current > end) {
            opt->return_status = EXIT_CODE_ERROR_TOTAL_SIZE_FIELD;
            return;
        }
        data_csum = ChecksumMem((U32 *) pep_hdr, len);

        ext_sig_hdr_csum = 0;

        if ((pep_hdr->processor == opt->proc_info->signature) && (pep_hdr->flags & opt->proc_info->platform_id))
            found = true;

        if (pep_hdr->data_size && (pep_hdr->total_size < pep_hdr->data_size + sizeof(pep_hdr_t))) {
            opt->return_status = EXIT_CODE_ERROR_TOTAL_SIZE_FIELD;
            return;
        }

        if (pep_hdr->data_size && (pep_hdr->total_size > pep_hdr->data_size + sizeof(pep_hdr_t))) {
            U32 correct_csum;

            partial_csum = ChecksumMem((U32 *) pep_hdr, sizeof(pep_hdr_t));
            partial_csum += data_csum;
            partial_csum -= pep_hdr->processor + pep_hdr->checksum + pep_hdr->flags;

            ext_sig_hdr = current;
            current = (U8 *) current + sizeof(ext_sig_hdr_t);

            ext_sig_hdr_csum = ChecksumMem((U32 *) &ext_sig_hdr, sizeof(ext_sig_hdr_t));

            for (i = 0; i < ext_sig_hdr->count; i++) {
                ext_sig = current;
                current = (U8 *) current + sizeof(ext_sig_t);

                if ((ext_sig->processor == opt->proc_info->signature) && (ext_sig->flags & opt->proc_info->platform_id))
                    found = true;

                correct_csum = ~(partial_csum + ext_sig->processor + ext_sig->flags) + 1;
                if (ext_sig->checksum != correct_csum) {
                    opt->return_status = EXIT_CODE_ERROR_EXTENDED_SIGNATURE_CHECKUM;
                    return;
                }
                ext_sig_hdr_csum += ChecksumMem((U32 *) &ext_sig, sizeof(ext_sig_t));
            }

            if (ext_sig_hdr_csum) {
                opt->return_status = EXIT_CODE_EXTENDED_SIGNATURE_HEADER_CHECKSUM;
                return;
            }
        }

        if (found) {
            opt->update_info->offset = update_offset;
            opt->update_info->revision = pep_hdr->revision;
            opt->update_info->processor = pep_hdr->processor;
            opt->update_info->flags = pep_hdr->flags;
            opt->update_info->valid = true;
            opt->return_status = EXIT_CODE_SUCCESS;
            return;
        }
    }

    opt->return_status = EXIT_CODE_FAILURE;
    return;
}

static void GetProcInfoCallBack(void *param)
{
    U32 eax, dummy;
    PROC_INFO *proc_info = param;
    MSR_REGS msr_regs;

    msr_regs.num = 0x8b;
    msr_regs.value = 0;
    write_msr(&msr_regs);

    cpuid32(1, &eax, &dummy, &dummy, &dummy);
    proc_info->signature = eax;

    msr_regs.num = 0x8b;
    read_msr(&msr_regs);
    proc_info->ucode_rev = msr_regs.value >> 32;

    msr_regs.num = 0x17;
    read_msr(&msr_regs);
    proc_info->platform_id = 1 << ((msr_regs.value >> 50) & 3);
}

//-----------------------------------------------------------------------------
void read_msr(void *param)
{
    MSR_REGS *msr_regs = param;
    rdmsr64(msr_regs->num, &msr_regs->value, &msr_regs->status);
}

//-----------------------------------------------------------------------------
void write_msr(void *param)
{
    MSR_REGS *msr_regs = param;
    wrmsr64(msr_regs->num, msr_regs->value, &msr_regs->status);
}
