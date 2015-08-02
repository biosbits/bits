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

.intel_syntax noprefix
.arch .sse3

#include <grub/symbol.h>
#include "smpequ.h"

.text

#if !defined(GRUB_TARGET_CPU_I386) && !defined(GRUB_TARGET_CPU_X86_64)
#error Unknown target CPU
#endif

#if defined(GRUB_TARGET_CPU_X86_64)
.macro pushaq
  push rax
  push rbx
  push rcx
  push rdx
  push rbp
  push rdi
  push rsi
  push r8
  push r9
  push r10
  push r11
  push r12
  push r13
  push r14
  push r15
.endm

.macro popaq
  pop r15
  pop r14
  pop r13
  pop r12
  pop r11
  pop r10
  pop r9
  pop r8
  pop rsi
  pop rdi
  pop rbp
  pop rdx
  pop rcx
  pop rbx
  pop rax
.endm
#endif

FUNCTION(gpfHandler)
#if defined(GRUB_TARGET_CPU_I386)
  push  ebp
  mov   ebp, esp
  push  eax

  # Stack at this point
  # [ebp]     Saved value of EBP register (from push EBP above)
  # [ebp+04h] Error code from gpf
  # [ebp+08h] Offset of executing instruction that caused gpf
  # [ebp+0Ch] Segment of executing instruction that caused gpf
  # [ebp+10h] Flags when executing instruction that caused gpf

  # verify gpf occurred at expected location
  mov   eax, [ebp+8]
  cmpd  [eax-8], 0x58475046  #'DWORD 'XGPF'
  jne   gpfHandler_exit

  # fix return address on stack to point at recovery code
  add   eax, dword ptr [eax-4]
  mov   [ebp+8], eax

  gpfHandler_exit:
  pop   eax
  leave
  add   esp, 4      # Remove the error code from the stack
  iretd
#elif defined(GRUB_TARGET_CPU_X86_64)
  push  rbp
  mov   rbp, rsp
  push  rax
  push  rbx

  # Stack at this point
  # [rbp]     Saved value of rbp register (from push rbp above)
  # [rbp+08h] Error code from gpf
  # [rbp+10h] Offset of executing instruction that caused gpf
  # [rbp+18h] Segment of executing instruction that caused gpf
  # [rbp+20h] Flags when executing instruction that caused gpf
  # [rbp+28h] rsp when executing instruction that caused gpf
  # [rbp+30h] ss when executing instruction that caused gpf

  # verify gpf occurred at expected location
  mov   rax, [rbp+0x10]
  cmpd  [rax-8], 0x58475046  #'DWORD 'XGPF'
  jne   gpfHandler_exit

  # fix return address on stack to point at recovery code
  mov   ebx, dword ptr [rax-4]
  add   rax, rbx
  mov   [rbp+0x10], rax

  gpfHandler_exit:
  pop   rbx
  pop   rax
  leave
  add   esp, 8      # Remove the error code from the stack
  iretq
#endif

FUNCTION(intHandler_asm)
#if defined(GRUB_TARGET_CPU_I386)
  pushad
  call EXT_C(intHandler)
  popad
  iretd
#elif defined(GRUB_TARGET_CPU_X86_64)
  pushaq
  call EXT_C(intHandler)
  popaq
  iretq
#endif

FUNCTION(switch_stack_and_call)
#if defined(GRUB_TARGET_CPU_I386)
  push  ebp
  mov   ebp, esp

  mov   ebx, [ebp+0xc]  # param
  mov   ecx, [ebp+0x8]  # mp_worker
  mov   esp, [ebp+0x10] # stack_top
  push  ebx
  call  ecx # never returns
#elif defined(GRUB_TARGET_CPU_X86_64)
  mov rsp, rdx
  xchg rdi, rsi
  call rsi # never returns
#endif

FUNCTION(ApStart)
  # On entry, ebx has the physical address of the SIPI block
  mov   eax,1
TestLock:
  cmp   dword ptr [ebx][BLOCK], 1
  jne   TryGetLock
  pause
  jmp   TestLock

TryGetLock:
  xchg  dword ptr [ebx][BLOCK], eax
  test  eax, eax
  je    LockObtained
  pause
  jmp   TestLock

LockObtained:
  mov   ecx, ebx
  add   ecx, AP_STACK

#if defined(GRUB_TARGET_CPU_I386)
  mov   esp, ecx
  push  dword ptr [ebx][PARAM]
  call  dword ptr [ebx][FUNCTIONPTR]
  # The function must not return
#elif defined(GRUB_TARGET_CPU_X86_64)
  mov   rsp, rcx
  mov   rdi, qword ptr [ebx][PARAM]
  call  qword ptr [ebx][FUNCTIONPTR]
  # The function must not return
#endif

# void wait_for_control_asm(U32 *control, U32 value, U32 use_mwait, U32 mwait_hint, U32 int_break_event)
FUNCTION(wait_for_control_asm)
#if defined(GRUB_TARGET_CPU_I386)
  push ebp
  mov ebp, esp
  pushad

  mov esi, [ebp+8]
  mov ebx, [ebp+0xc]
  mov edi, [ebp+0x14]

  cmp dword ptr [ebp+0x10], 0
  je no_mwait

  cmp dword ptr [ebp+0x18], 1
  je mwait_int_break_event

mwait_no_int_break_event:
  cmp [esi], ebx
  je done
  mov eax, esi
  xor ecx, ecx
  xor edx, edx
  monitor
  mov eax, edi
  cmp [esi], ebx
  je done
  mwait
  jmp mwait_no_int_break_event

mwait_int_break_event:
  cmp [esi], ebx
  je done
  mov eax, esi
  xor ecx, ecx
  xor edx, edx
  monitor
  mov eax, edi
  mov ecx, 1
  cmp [esi], ebx
  je done
  mwait
  jmp mwait_int_break_event

no_mwait:
  cmp [esi], ebx
  je done
  pause
  jmp no_mwait

done:
  popad
  leave
  ret
#elif defined(GRUB_TARGET_CPU_X86_64)
  pushaq

  cmp edx, 0
  je no_mwait

  mov ebx, ecx # mwait_hint

# control is in rdi
# value is in esi (want to wait for *control == value)
# mwait_hint is in ebx

mwait_loop:
  cmp [rdi], esi
  je done
  mov rax, rdi
  xor ecx, ecx
  xor edx, edx
  monitor
  mov eax, ebx
  mov rcx, r8
  cmp [rdi], esi
  je done
  mwait
  jmp mwait_loop

no_mwait:
  cmp [rdi], esi
  je done
  pause
  jmp no_mwait

done:
  popaq
  ret
#endif

VARIABLE(wait_for_control_asm_size)
    .long .-wait_for_control_asm    # Size, in bytes

.code16
#------------------------------------------------------------------------------
FUNCTION(pm32)
  #
  # Switch to Protected mode.
  #
  xor     ebx, ebx
  mov     bx, cs
  mov     ds, bx
  shl     ebx, 4   # Adjust segment into physical address format

  mov     eax,ebx
  .equ REL_SIPI_CODE_DESCRIPTOR, offset SIPI_CODE_DESCRIPTOR - offset pm32
  mov     si, REL_SIPI_CODE_DESCRIPTOR
  mov     [si+0x2], ax                       # Put lower physical address into GDT.
  shr     eax,0x10                           # High nibble of physical address only.
  mov     [si+0x4], al                       # Put high nibble physical address into GDT.

  mov     eax,ebx
  .equ REL_BootGDTtable, offset BootGDTtable - offset pm32
  add     eax, REL_BootGDTtable          # Add in offset of GDT table.
  .equ REL_GDTDescriptor, offset GDTDescriptor - offset pm32
  mov     si, REL_GDTDescriptor
  mov     [si+0x2], eax                       # Store in GDT address variable.

  .byte   0x66
  lgdt    cs:REL_GDTDescriptor

  mov     eax, cr0                         # Get control register 0
  or      eax, 0x00000003                  # Set PE bit (bit #0) & MP bit (bit #1)
  mov     cr0, eax                         # Activate protected mode
  mov     eax, cr4                         # Get control register 4
  or      eax, 0x00000600                  # Set OSFXSR bit (bit #9) & OSXMMEXCPT bit (bit #10)
  mov     cr4, eax

  # Immediately following the MOV CR0 instruction, execute a far JMP or far
  # CALL instruction. This operation is typically a far jump or call to the
  # next instruction in the instruction stream.
  .byte  0x0EA
.equ REL_jmp_target, 1f - offset pm32
  .word  REL_jmp_target
  .word  SIPI_CODE_SEL
1:

.equ REL_CpuRefCodeLinearAddress, offset CpuRefCodeLinearAddress - offset pm32

#if defined(GRUB_TARGET_CPU_X86_64)
.equ REL_ApStart32, offset ApStart32 - offset pm32
  # Fix up CpuRefCodeLinearAddress to point to ApStart32, still in this SIPI block
  mov eax, ebx
  add eax, REL_ApStart32
  mov esi, REL_CpuRefCodeLinearAddress
  mov dword ptr [esi], eax
#endif

  # Set up selectors for Protected Mode entry.
.att_syntax
  mov     $SYS_DATA_SEL, %ax
.intel_syntax noprefix
  mov     ds, ax
  mov     es, ax
  mov     fs, ax
  mov     gs, ax
  mov     ss, ax

  #
  # Go to Protected32
  #
  jmp     FWORD PTR cs:[REL_CpuRefCodeLinearAddress]

.align 4

# 16-bit Selector and 32-bit offset value for the FAR JMP to Processor Reference Code.
VARIABLE(CpuRefCodeLinearAddress)
  .long  offset ApStart
  .word  LINEAR_CODE_SEL

.align 16

# GDT[0]: 0x00: Null entry, never used.
.equ NULL_SEL, .-GDT_BASE            # Selector [0]
GDT_BASE:
VARIABLE(BootGDTtable)
  .long 0
  .long 0

# Linear code segment descriptor
.equ LINEAR_CODE_SEL, .-GDT_BASE    # Selector [0x8]
  .word 0x0FFFF # limit 0xFFFFF
  .word 0       # base 0
  .byte 0
  .byte 0x09B   # present, ring 0, code, execute/read, non-conforming, accessed
  .byte 0x0CF   # page-granular, 32-bit
  .byte 0

# System data segment descriptor
.equ  SYS_DATA_SEL, .-GDT_BASE    # Selector [0x10]
  .word 0x0FFFF # limit 0xFFFFF
  .word 0       # base 0
  .byte 0
  .byte 0x093   # present, ring 0, data, read/write, expand-up, accessed
  .byte 0x0CF   # page-granular, 32-bit
  .byte 0

# SIPI code segment descriptor
.equ  SIPI_CODE_SEL, .-GDT_BASE # Selector [0x18]
SIPI_CODE_DESCRIPTOR:
  .word 0x0FFFF # limit 0xFFFF
  .word 0x0000  # base
  .byte 0x00
  .byte 0x09B   # present, ring 0, code, execute/read, non-conforming, accessed
  .byte 0x000   # byte-granular, 16-bit
  .byte 0

#if defined(GRUB_TARGET_CPU_X86_64)
# 64-bit code segment descriptor
.equ CODE64_SEL, .-GDT_BASE
  .word 0
  .word 0
  .byte 0
  .byte 0x9B   # present, ring 0, code, execute/read, non-conforming, accessed
  .byte 0xA0   # page-granular, 64-bit
  .byte 0

# 64-bit data segment descriptor
.equ  DATA64_SEL, .-GDT_BASE
  .word 0
  .word 0
  .byte 0
  .byte 0x93   # present, ring 0, data, read/write, expand-up, accessed
  .byte 0xA0   # page-granular, 64-bit
  .byte 0
#endif

.equ  GDT_SIZE, .-BootGDTtable  # Size, in bytes

# Global Descriptor Table Descriptor
GDTDescriptor:      # GDT descriptor
  .word GDT_SIZE-1  # GDT limit
  .word 0x0000      # GDT base address
  .word 0x0000

#if defined(GRUB_TARGET_CPU_X86_64)
.code32
ApStart32:
  mov     eax, cr4
  or      eax, 0xA0
  mov     cr4, eax

  mov     eax, dword ptr [ebx][PAGETABLE]
  mov     cr3, eax

  # Enable long-mode in EFER
  mov ecx, 0xC0000080
  rdmsr
  or eax, 0x100
  wrmsr

  mov     eax, cr0
  or      eax, 0x80000000
  mov     cr0, eax

.equ REL_NextInstruction, offset 1f - offset pm32
.equ REL_NextInstructionFword, offset NextInstructionFword - offset pm32
  mov     eax, ebx
  add     eax, REL_NextInstruction
  mov     dword ptr [ebx+REL_NextInstructionFword], eax
  jmp     FWORD PTR cs:[ebx+REL_NextInstructionFword]

.align 4

VARIABLE(NextInstructionFword)
  .long  0
  .word  CODE64_SEL

1:

.code64

  # Set up 64-bit selectors
.att_syntax
  mov     $DATA64_SEL, %ax
.intel_syntax noprefix
  mov     ds, ax
  mov     es, ax
  mov     fs, ax
  mov     gs, ax
  mov     ss, ax

  movabs  rax, offset ApStart
  jmp     rax
#endif

.align 4

VARIABLE(pm32_size)
    .long .-pm32   # Size, in bytes
