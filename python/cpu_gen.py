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

"""CPU module for unknown processors"""

import bits
import testmsr
import testsuite

name = "Unknown"

def is_cpu():
    return True

def init():
    pass

def register_tests():
    testsuite.add_test("MSR consistency test", msr_test)

def msr_test():
    testmsr.rdmsr_consistent(msr_blacklist, msr_masklist)

def mwait_hint_to_cstate(hint):
    mwait_hints = {0xf0:'C0'}
    mwait_hints[0x00] = 'C1*'
    mwait_hints[0x01] = 'C1* Substate 1'
    mwait_hints[0x10] = 'C2*'
    mwait_hints[0x11] = 'C2* substate 1'
    mwait_hints[0x20] = 'C3*'
    mwait_hints[0x21] = 'C3* substate 1'
    mwait_hints[0x30] = 'C4*'
    mwait_hints[0x31] = 'C4* substate 1'
    mwait_hints[0x32] = 'C4* substate 2'
    mwait_hints[0x33] = 'C4* substate 3'
    return 'processor-specific %s' % mwait_hints.get(hint, "")

msr_blacklist = {
    0x0,        # IA32_P5_MC_ADDR
    0x1,        # IA32_P5_MC_TYPE
    0x10,       # IA32_TIME_STAMP_COUNTER
    0x34,       # MSR_SMI_COUNT
    0x39,
    0xE7,       # IA32_MPERF
    0xE8,       # IA32_APERF
    0x19c,      # IA32_THERM_STATUS
    0x1f4,
    0x1f5,
    0x309,      # IA32_FIXED_CTR0
    0x30a,      # IA32_FIXED_CTR1
    0x30b,      # IA32_FIXED_CTR2
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
