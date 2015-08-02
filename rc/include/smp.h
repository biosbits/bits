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

#ifndef smp_h
#define smp_h

#include "datatype.h"
#include "smprc.h"

/* smp_init returns the number of CPUs, or 0 on error. */
U32 smp_init(void);

/* smp_phantom_init is required after any module uses an init-sipi-sipi sequence */
void smp_phantom_init(void);

U32 smp_read_bclk(void);

/* Returns the internal array of CPU_INFO structures, or NULL on error.
 *
 * The returned pointer has const for a reason: do not modify the result
 * without copying it.
 */
const CPU_INFO *smp_read_cpu_list(void);

U32 smp_function(U32 apicid, CALLBACK function, void *param);

bool smp_get_mwait(U32 apicid, bool *use_mwait, U32 *mwait_hint, U32 *int_break_event);
void smp_set_mwait(U32 apicid, bool use_mwait, U32 mwait_hint, U32 int_break_event);

/* Sleep for the specified number of microseconds. */
void smp_sleep(U32 microseconds);

#endif // smp_h
