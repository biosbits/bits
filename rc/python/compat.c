/*
Copyright (c) 2014, Intel Corporation
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

/* Implementations of C and POSIX functions, for use by Python. */

#include "pyconfig.h"

#define OPEN_MAX 256

static FILE *fd_table[OPEN_MAX] = { stdin, stdout, stderr };

static int high_water_mark = 2;

/* Convert an integer file descriptor to a FILE *; on failure, sets errno and
 * returns NULL.  Only valid on file descriptors previously returned from
 * file_to_fd. */
static FILE *fd_to_file(int fd)
{
    if (fd < 0 || fd >= OPEN_MAX)
        return NULL;
    return fd_table[fd];
}

/* Convert a FILE * to an integer file descriptor; on failure, sets errno and
 * returns -1.  Will handle files never-before assigned an fd.
 *
 * This is a linear search for simplicity, but high_water_mark keeps it
 * reasonable for small numbers of files. */
static int file_to_fd(FILE *file)
{
    int fd;
    int unused_fd = -1;
    for (fd = 0; fd <= high_water_mark; fd++) {
        if (fd_table[fd] == file)
            return fd;
        if (unused_fd == -1 && !fd_table[fd])
            unused_fd = fd;
    }
    if (unused_fd == -1) {
        if (high_water_mark == (OPEN_MAX - 1))
            return -1;
        unused_fd = ++high_water_mark;
    }
    fd_table[unused_fd] = file;
    return unused_fd;
}

/* Record file closure, to stop tracking it for file<->fd conversions. */
static void note_file_closure(FILE *file)
{
    int fd = file_to_fd(file);
    if (fd <= 2)
        return;
    fd_table[fd] = NULL;
    if (fd == high_water_mark)
        while (--high_water_mark >= 0)
            if (fd_table[high_water_mark])
                break;
}

#undef abort
__attribute__((noreturn)) void abort(void)
{
    grub_fatal("Internal error: Python called abort()\n");
}

void _assert(const char *filename, unsigned line, int condition, const char *condition_str)
{
    if (!condition)
        grub_fatal("%s:%u: Python assertion failure: assert(%s)\n", filename, line, condition_str);
}

int atoi(const char *str)
{
    grub_errno = GRUB_ERR_NONE;
    return grub_strtol(str, NULL, 10);
}

void clearerr(FILE *stream)
{
    (void)stream;
    grub_errno = GRUB_ERR_NONE;
}

int dlclose(void *handle)
{
    (void)handle;
    return 0;
}

char *dlerror(void)
{
    return "dlopen and dlsym not supported";
}

void *dlopen(const char *filename, int flag)
{
    (void)flag;
    /* Support dlopen of NULL by returning a "valid" handle, which just won't have
     * any symbols. */
    return filename ? NULL : (void *)1;
}

void *dlsym(void *handle, const char *symbol)
{
    (void)handle;
    (void)symbol;
    return NULL;
}

__attribute__((noreturn)) void exit(int status)
{
    grub_fatal("Internal error: Python tried to exit with status %d\n", status);
}

int fclose(FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdin || stream == stdout || stream == stderr) {
        grub_printf("Internal error: Python attempted to close stdin, stdout, or stderr.\n");
        return -1;
    }
    note_file_closure(stream);
    return (grub_file_close(stream) == GRUB_ERR_NONE) ? 0 : EOF;
}

int feof(FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdin || stream == stdout || stream == stderr)
        return 0;
    return stream->offset == stream->size;
}

int ferror(FILE *stream)
{
    (void)stream;
    grub_errno = GRUB_ERR_NONE;
    return 0;
}

int fflush(FILE *stream)
{
    (void)stream;
    grub_errno = GRUB_ERR_NONE;
    return 0;
}

int fgetc(FILE *stream)
{
    unsigned char c;
    grub_errno = GRUB_ERR_NONE;
    return fread(&c, 1, 1, stream) ? c : EOF;
}

char *fgets(char *s, int size, FILE *stream)
{
    char *ret = s;
    grub_errno = GRUB_ERR_NONE;
    while (--size) {
        int c = fgetc(stream);
        if (c == EOF) {
            if (s == ret)
                return NULL;
            break;
        }
        *s++ = c;
        if (c == '\n')
            break;
    }
    *s = '\0';
    return ret;
}

int fileno(FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    return file_to_fd(stream);
}

FILE *fopen(const char *path, const char *mode)
{
    grub_errno = GRUB_ERR_NONE;
    if (grub_strcmp(mode, "r") != 0 && grub_strcmp(mode, "rb") != 0) {
        grub_printf("Internal error: Python attempted to open a file with unsupported mode \"%s\"\n", mode);
        return NULL;
    }
    return grub_file_open(path);
}

int fprintf(FILE *stream, const char *format, ...)
{
    va_list args;
    int ret;
    grub_errno = GRUB_ERR_NONE;
    va_start(args, format);
    ret = vfprintf(stream, format, args);
    va_end(args);
    return ret;
}

int fputc(int c, FILE *stream)
{
    const char s[] = { (unsigned char)c, '\0' };
    grub_errno = GRUB_ERR_NONE;
    if (stream != stdout && stream != stderr) {
        grub_printf("Internal error: Python attempted to write to a file.\n");
        return EOF;
    }
    grub_xputs(s);
    return (unsigned char)c;
}

int fputs(const char *s, FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream != stdout && stream != stderr) {
        grub_printf("Internal error: Python attempted to write to a file.\n");
        return EOF;
    }
    grub_xputs(s);
    return 1;
}

size_t fread(void *ptr, size_t size, size_t nmemb, FILE *stream)
{
    ssize_t read_return;
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdout || stream == stderr) {
        grub_printf("Internal error: Python attempted to fread from stdout or stderr.\n");
        return 0;
    }
    if (stream == stdin) {
        size_t i, j;
        unsigned char *bytes = ptr;
        for (i = 0; i < nmemb; i++)
            for (j = 0; j < size; j++)
                *bytes++ = grub_getkey();
        return nmemb;
    }

    read_return = grub_file_read(stream, ptr, size * nmemb);
    if (read_return <= 0)
        return 0;
    return read_return / size;
}

int fseek(FILE *stream, long offset, int whence)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdin || stream == stdout || stream == stderr) {
        grub_printf("Internal error: Python attempted to seek on stdin, stdout, or stderr.\n");
        return -1;
    }
    switch (whence)
    {
        case SEEK_SET:
            break;
        case SEEK_CUR:
            offset += stream->offset;
            break;
        case SEEK_END:
            offset += stream->size;
            break;
        default:
            return -1;
    }
    return (grub_file_seek(stream, offset) == -1ULL) ? -1 : 0;
}

int fstat(int fd, struct stat *buf)
{
    grub_errno = GRUB_ERR_NONE;
    buf->st_mtime = 0;
    if (fd >= 0 && fd < 3) {
        buf->st_mode = S_IFCHR | 0777;
        buf->st_size = 0;
    } else {
        grub_file_t file = fd_to_file(fd);
        if (!file)
            return -1;
        buf->st_mode = S_IFREG | 0777;
        buf->st_size = grub_file_size(file);
    }
    return 0;
}

long ftell(FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdin || stream == stdout || stream == stderr)
        return 0;
    return grub_file_tell(stream);
}

size_t fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream != stdout && stream != stderr) {
        grub_printf("Internal error: Python attempted to write to a file.\n");
        return 0;
    }
    if (size > GRUB_INT_MAX || nmemb > GRUB_INT_MAX || (uint64_t)size * (uint64_t)nmemb > GRUB_INT_MAX) {
        grub_error(GRUB_ERR_OUT_OF_RANGE, "Internal error: Python attempted to write more than 2GB to stdout or stderr.\n");
        return 0;
    }
    return grub_printf("%.*s", (int)(size * nmemb), (char *)ptr);
}

char *getenv(const char *name)
{
    grub_errno = GRUB_ERR_NONE;
    return (char *)grub_env_get(name);
}

int isatty(int fd)
{
    grub_errno = GRUB_ERR_NONE;
    return fd >= 0 && fd < 3;
}

void iterate_directory(const char *dirname, int (*callback)(const char *filename, const struct grub_dirhook_info *info))
{
    char *device_name;
    grub_device_t device;
    grub_errno = GRUB_ERR_NONE;
    device_name = grub_file_get_device_name(dirname);
    device = grub_device_open(device_name);
    if (device) {
        grub_fs_t fs = grub_fs_probe(device);
        if (fs)
            fs->dir(device, dirname, callback);
        grub_device_close(device);
    }
    grub_free(device_name);
}

static const char *is_directory_filename;
static int is_directory_result;

static int is_directory_callback(const char *filename, const struct grub_dirhook_info *info)
{
    if ((info->case_insensitive ? grub_strcasecmp : grub_strcmp)(is_directory_filename, filename) == 0) {
        is_directory_result = !!info->dir;
        return 1;
    }
    return 0;
}

int is_directory(const char *filename)
{
    char *basename;
    char *dirname;
    size_t i;
    char *copy;

    if (grub_strcmp(filename, "/") == 0)
        return 1;

    copy = grub_strdup(filename);
    if (!copy)
        return 0;
    dirname = copy;
    i = grub_strlen(dirname);
    while (i && dirname[i - 1] == '/')
        dirname[--i] = '\0';
    basename = grub_strrchr(dirname, '/');
    if (basename)
        *basename++ = '\0';
    else
        basename = "/";
    if (*dirname == '\0')
        dirname = "/";

    is_directory_filename = basename;
    is_directory_result = 0;
    iterate_directory(dirname, is_directory_callback);

    grub_free(copy);
    return is_directory_result;
}

struct lconv *localeconv(void)
{
    static char grouping[] = { CHAR_MAX };
    static struct lconv lconv = { .decimal_point = ".", .thousands_sep = "", .grouping = grouping };
    grub_errno = GRUB_ERR_NONE;
    return &lconv;
}

off_t lseek(int fd, off_t offset, int whence)
{
    grub_file_t file;

    if (fd >= 0 && fd < 3)
        grub_printf("Internal error: Python attempted to seek on stdin, stdout, or stderr.\n");
        return (off_t)-1;

    file = fd_to_file(fd);
    if (!file)
        return (off_t)-1;
    grub_errno = GRUB_ERR_NONE;
    if (fseek(file, offset, whence) < 0)
        return (off_t)-1;
    return file->offset;
}

time_t mktime(struct tm *tm)
{
    (void)tm;
    return 0;
}

int printf(const char *format, ...)
{
    va_list args;
    int ret;
    grub_errno = GRUB_ERR_NONE;
    va_start(args, format);
    ret = grub_vprintf(format, args);
    va_end(args);
    return ret;
}

static void qsort_swap_mem(void *a, void *b, size_t size)
{
    void *temp = __builtin_alloca(size);
    memcpy(temp, a, size);
    memcpy(a, b, size);
    memcpy(b, temp, size);
}

void qsort(void *base_void, size_t nmemb, size_t size, int(*compar)(const void *, const void *))
{
    char *base = base_void;
    size_t i;
    size_t last = 0;
    grub_errno = GRUB_ERR_NONE;
    if (nmemb <= 1)
        return;
    for (i = 1; i < nmemb; i++)
        if (compar(base + i*size, base) < 0)
            qsort_swap_mem(base + (++last)*size, base + i*size, size);
    qsort_swap_mem(base, base + last*size, size);
    qsort(base, last, size, compar);
    qsort(base + (last + 1)*size, nmemb - (last + 1), size, compar);
}

void rewind(FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    fseek(stream, 0L, SEEK_SET);
}

void setbuf(FILE *stream, char *buf)
{
    (void)stream;
    (void)buf;
    grub_errno = GRUB_ERR_NONE;
}

sighandler_t signal(int signum, sighandler_t handler)
{
    (void)signum;
    (void)handler;
    grub_errno = GRUB_ERR_NONE;
    return SIG_ERR;
}

int snprintf(char *str, size_t size, const char *format, ...)
{
    int ret;
    va_list args;
    grub_errno = GRUB_ERR_NONE;
    va_start(args, format);
    ret = grub_vsnprintf(str, size, format, args);
    va_end(args);
    return ret;
}

int sprintf(char *str, const char *format, ...)
{
    int ret;
    va_list args;
    grub_errno = GRUB_ERR_NONE;
    va_start(args, format);
    ret = grub_vsnprintf(str, GRUB_ULONG_MAX, format, args);
    va_end(args);
    return ret;
}

int stat(const char *path, struct stat *buf)
{
    FILE *file;
    grub_errno = GRUB_ERR_NONE;
    file = grub_file_open(path);
    if (file) {
        buf->st_size = grub_file_size(file);
        grub_file_close(file);
        buf->st_mode = S_IFREG | 0777;
    } else {
        if (grub_errno == GRUB_ERR_BAD_FILE_TYPE && is_directory(path)) {
            grub_errno = GRUB_ERR_NONE;
            buf->st_size = 0;
            buf->st_mode = S_IFDIR | 0777;
        } else {
            return -1;
        }
    }
    buf->st_mtime = 0;
    return 0;
}

char *strdup(const char *s)
{
    grub_errno = GRUB_ERR_NONE;
    return grub_strdup(s);
}

char *strerror(int errnum)
{
    static char buf[sizeof("GRUB error 4294967296")];
    grub_errno = GRUB_ERR_NONE;
    grub_snprintf(buf, sizeof(buf), "GRUB error %u", errnum);
    return buf;
}

char *strpbrk(const char *s, const char *accept)
{
    grub_errno = GRUB_ERR_NONE;
    while (*s) {
        if (strchr(accept, *s) != NULL)
            return (char *)s;
        s++;
    }
    return NULL;
}

char *strrchr(const char *s, int c)
{
    grub_errno = GRUB_ERR_NONE;
    return grub_strrchr(s, c);
}

int ungetc(int c, FILE *stream)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream == stdout || stream == stderr) {
        grub_printf("Internal error: Python attempted to ungetc on stdout or stderr.\n");
        return EOF;
    }
    if (stream == stdin) {
        grub_printf("Internal error: Python attempted to ungetc on stdin.\n");
        return EOF;
    }
    if (stream->offset == 0) {
        grub_printf("Internal error: Python attempted to ungetc at the beginning of a file.\n");
        return EOF;
    }
    grub_file_seek(stream, stream->offset-1);
    if (fgetc(stream) != c) {
        grub_printf("Internal error: Python attempted to ungetc a character it didn't getc.\n");
        return EOF;
    }
    grub_file_seek(stream, stream->offset-1);
    return c;
}

int unlink(const char *pathname)
{
    grub_errno = GRUB_ERR_NONE;
    grub_printf("Internal error: Python attempted to unlink a file.\n");
    return -1;
}

int vfprintf(FILE *stream, const char *format, va_list args)
{
    grub_errno = GRUB_ERR_NONE;
    if (stream != stdout && stream != stderr) {
        grub_printf("Internal error: Python attempted to write to a file.\n");
        return -1;
    }
    return grub_vprintf(format, args);
}

int vsnprintf(char *str, size_t size, const char *format, va_list ap)
{
    grub_errno = GRUB_ERR_NONE;
    return grub_vsnprintf(str, size, format, ap);
}

size_t wcslen(const wchar_t *s)
{
    size_t len = 0;
    while (*s++)
        len++;
    return len;
}
