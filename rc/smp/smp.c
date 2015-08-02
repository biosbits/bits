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

#include "smprc.h"
#include "smp.h"
#include "portable.h"

#include <grub/dl.h>
#include <grub/machine/memory.h>
#include <grub/memory.h>
#include <grub/mm.h>

GRUB_MOD_LICENSE("GPLv3+");
GRUB_MOD_DUAL_LICENSE("3-clause BSD");

static void *global_working_memory = NULL;
static void *global_page_below_1M = NULL;
static void *global_reserved_mwait_memory = NULL;

U32 smp_init(void)
{
    int handle;

    if (!global_working_memory) {
        global_working_memory = grub_memalign(SMP_WORKING_MEMORY_ALIGN, SMP_WORKING_MEMORY_SIZE);
        if (!global_working_memory) {
            dprintf("smp", "Failed to allocate working memory\n");
            return 0;
        }
        grub_memset(global_working_memory, 0, SMP_WORKING_MEMORY_SIZE);
    }

    if (!global_page_below_1M) {
        global_page_below_1M = grub_mmap_malign_and_register(SMP_LOW_MEMORY_ALIGN, SMP_LOW_MEMORY_SIZE, &handle, GRUB_MEMORY_AVAILABLE, GRUB_MMAP_MALLOC_LOW);
        if (!global_page_below_1M) {
            dprintf("smp", "Failed to allocate a page below 1M\n");
            return 0;
        } else if ((grub_addr_t)global_page_below_1M >= 1048576) {
            dprintf("smp", "Attempted to allocate a page below 1M, but got %p\n", global_page_below_1M);
            return 0;
        }
    }

    if (!global_reserved_mwait_memory) {
        global_reserved_mwait_memory = grub_mmap_malign_and_register(SMP_RESERVED_MEMORY_ALIGN, SMP_RESERVED_MEMORY_SIZE, &handle, GRUB_MEMORY_RESERVED, 0);
        if (!global_reserved_mwait_memory) {
            dprintf("smp", "Failed to allocate reserved MWAIT memory\n");
            return 0;
        }
    }

    return smp_init_with_memory(global_working_memory, global_page_below_1M, global_reserved_mwait_memory);
}

U32 smp_read_bclk(void)
{
    return smp_read_bclk_with_memory(global_working_memory);
}

const CPU_INFO *smp_read_cpu_list(void)
{
    return smp_read_cpu_list_with_memory(global_working_memory);
}

void smp_phantom_init(void)
{
    smp_phantom_init_with_memory(global_working_memory);
}

bool smp_get_mwait(U32 apicid, bool *use_mwait, U32 *mwait_hint, U32 *int_break_event)
{
    return smp_get_mwait_with_memory(global_working_memory, apicid, use_mwait, mwait_hint, int_break_event);
}

void smp_set_mwait(U32 apicid, bool use_mwait, U32 mwait_hint, U32 int_break_event)
{
    smp_set_mwait_with_memory(global_working_memory, apicid, use_mwait, mwait_hint, int_break_event);
}

U32 smp_function(U32 apicid, CALLBACK function, void *param)
{
    return smp_function_with_memory(global_working_memory, apicid, function, param);
}

void smp_sleep(U32 microseconds)
{
    smp_sleep_with_memory(global_working_memory, microseconds);
}

GRUB_MOD_INIT(smp)
{
}

GRUB_MOD_FINI(smp)
{
}
