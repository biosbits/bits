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

#ifndef smpasm_h
#define smpasm_h

#include "datatype.h"
#include "portable.h"
#include "smpequ.h"

typedef struct dword_regs {
    U32 _eax;
    U32 _ebx;
    U32 _ecx;
    U32 _edx;
} DWORD_REGS;

typedef asmlinkage void (*ASM_CALLBACK)(void *);

asmlinkage void gpfHandler(void);
asmlinkage void intHandler_asm(void);
asmlinkage void switch_stack_and_call(void *function, void *param, void *stack_addr) attr_noreturn;
asmlinkage void ApStart(void);
asmlinkage void pm32(void);
extern U32 pm32_size;
asmlinkage void wait_for_control_asm(U32 * control, U32 value, U32 use_mwait, U32 mwait_hint, U32 int_break_event);
extern U32 wait_for_control_asm_size;

#endif /* smpasm_h */
