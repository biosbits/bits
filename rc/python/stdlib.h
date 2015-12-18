#ifndef STDLIB_H
#define STDLIB_H

#include <lib/posix_wrap/stdlib.h>

#define abort() grub_fatal("%s:%u: Internal error: Python called abort()\n", __FILE__, __LINE__)

#endif /* STDLIB_H */
