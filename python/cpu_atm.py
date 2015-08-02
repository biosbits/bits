# Copyright (c) 2011, Intel Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of Intel Corporation nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""CPU module for Atom"""

import bits
from cpu_gen import mwait_hint_to_cstate
import testmsr
import testsuite

name = 'Atom'

def is_cpu():
    return bits.cpuid(bits.bsp_apicid(),1).eax & ~0xf == 0x106c0

def init():
    pass

def register_tests():
    testsuite.add_test("MSR consistency test", msr_test)

def msr_test():
    testmsr.rdmsr_consistent(msr_blacklist, msr_masklist)

msr_blacklist = {
    0x0,        # IA32_P5_MC_ADDR
    0x1,        # IA32_P5_MC_TYPE
    0x10,       # IA32_TIME_STAMP_COUNTER
    0x34,       # MSR_SMI_COUNT
    0x39,
    0x40,       # MSR_LAST_BRANCH_0_FROM_IP
    0x41,       # MSR_LAST_BRANCH_1_FROM_IP
    0x42,       # MSR_LAST_BRANCH_2_FROM_IP
    0x43,       # MSR_LAST_BRANCH_3_FROM_IP
    0x44,       # MSR_LAST_BRANCH_4_FROM_IP
    0x45,       # MSR_LAST_BRANCH_5_FROM_IP
    0x46,       # MSR_LAST_BRANCH_6_FROM_IP
    0x47,       # MSR_LAST_BRANCH_7_FROM_IP
    0x60,       # MSR_LAST_BRANCH_0_TO_LIP
    0x61,       # MSR_LAST_BRANCH_1_TO_LIP
    0x62,       # MSR_LAST_BRANCH_2_TO_LIP
    0x63,       # MSR_LAST_BRANCH_3_TO_LIP
    0x64,       # MSR_LAST_BRANCH_4_TO_LIP
    0x65,       # MSR_LAST_BRANCH_5_TO_LIP
    0x66,       # MSR_LAST_BRANCH_6_TO_LIP
    0x67,       # MSR_LAST_BRANCH_7_TO_LIP
    0xE7,       # IA32_MPERF
    0xE8,       # IA32_APERF
    0x198,      # MSR_PERF_STATUS
    0x199,      # IA32_PERF_CTL
    0x19c,      # IA32_THERM_STATUS
    0x1c9,      # MSR_LASTBRANCH_TOS
    0x1d9,      # IA32_DEBUGCTL
    0x1dd,      # MSR_LER_FROM_LIP
    0x1de,      # MSR_LER_TO_LIP
    0x1f4,
    0x1f5,
    0x309,      # IA32_FIXED_CTR0
    0x30A,      # IA32_FIXED_CTR1
    0x30B,      # IA32_FIXED_CTR2
    0x3f8,      # Package C-state residency
    0x3f9,      # Package C-state residency
    0x3fa,      # Package C-state residency
    0x3fc,      # Core C-state residency
    0x3fd,      # Core C-state residency
    0x3fe,      # Core C-state residency
}

msr_masklist = {
    0x1b: ~(1 << 8), # IA_APIC_BASE, mask out the BSP bit
}
