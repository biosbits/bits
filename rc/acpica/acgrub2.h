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

#ifndef __ACGRUB2_H__
#define __ACGRUB2_H__

#include <platform/acgcc.h>
#include <grub/misc.h>
#define GRUB_POSIX_BOOL_DEFINED 1
#include <lib/posix_wrap/sys/types.h>
#include <lib/posix_wrap/ctype.h>
#include <lib/posix_wrap/stdlib.h>
#include <lib/posix_wrap/string.h>
#include "compat.h"

#define ACPI_USE_SYSTEM_CLIBRARY

#if defined(GRUB_TARGET_CPU_I386)
#define ACPI_MACHINE_WIDTH 32
#define ACPI_32BIT_PHYSICAL_ADDRESS
#elif defined(GRUB_TARGET_CPU_X86_64)
#define ACPI_MACHINE_WIDTH 64
#else
#error Could not determine ACPI_MACHINE_WIDTH
#endif

#define ACPI_SINGLE_THREADED

// Uncomment the next three lines to add debug support
#define ACPI_DEBUG_OUTPUT
#define ACPI_DISASSEMBLER

#define ACPI_SHIFT_RIGHT_64(n_hi, n_lo) do { (n_lo) >>= 1; (n_lo) |= ((n_hi) & 1) << 31; (n_hi) >>= 1; } while(0)

static inline grub_uint32_t acpi_div_64_by_32(grub_uint32_t n_hi, grub_uint32_t n_lo, grub_uint32_t d32, grub_uint32_t *r32)
{
        grub_uint64_t q64, r64;
        q64 = grub_divmod64((((grub_uint64_t)(n_hi)) << 32) | (grub_uint64_t)(n_lo), d32, &r64);
        if (r32)
                *r32 = r64;
        return q64;
}

#define ACPI_DIV_64_BY_32(n_hi, n_lo, d32, q32, r32) do { (q32) = acpi_div_64_by_32((n_hi), (n_lo), (d32), &(r32)); } while(0)

#endif /* __ACGRUB2_H__ */
