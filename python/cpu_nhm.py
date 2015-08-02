# Copyright (c) 2012, Intel Corporation
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

"""CPU module for Nehalem"""

import bitfields
import bits
from cpu_gen import mwait_hint_to_cstate
import cstate_residency
from collections import namedtuple
import pstate
import testmsr
import testpci
import testsuite
import ttypager

name = 'Nehalem'

def is_cpu():
    return bits.cpuid(bits.bsp_apicid(),1).eax & ~0xf == 0x106a0

def init():
    pass

def register_tests():
    testsuite.add_test("MSR consistency test", msr_test)
    testsuite.add_test("Power management test suite, generic profile", test_pm_generic_profile)
    testsuite.add_test("C-state residency test", lambda: cstate_residency.test(*residency_params))
    testsuite.add_test("C-state residency test with USB disabled via BIOS handoff", lambda: cstate_residency.test_with_usb_disabled(*residency_params), runall=False)
    testsuite.add_test("Test hardware P-state ratios", lambda: pstate.test_hardware_pstates(pstate.turbo_max_plus_one))

def msr_test():
    testmsr.rdmsr_consistent(msr_blacklist, msr_masklist)

msr_blacklist = {
    0x0,        # IA32_P5_MC_ADDR
    0x1,        # IA32_P5_MC_TYPE
    0x10,       # IA32_TIME_STAMP_COUNTER
    0x34,       # MSR_SMI_COUNT
    0x39,
    0xE7,       # IA32_MPERF
    0xE8,       # IA32_APERF
    0x198,      # MSR_PERF_STATUS
    0x19c,      # IA32_THERM_STATUS
    0x1c9,      # MSR_LASTBRANCH_TOS
    0x1dd,      # MSR_LER_FROM_LIP
    0x1de,      # MSR_LER_TO_LIP
    0x1d9,      # IA32_DEBUGCTL
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
    0x680,      # MSR_LAST_BRANCH_0_FROM_IP
    0x681,      # MSR_LAST_BRANCH_1_FROM_IP
    0x682,      # MSR_LAST_BRANCH_2_FROM_IP
    0x683,      # MSR_LAST_BRANCH_3_FROM_IP
    0x684,      # MSR_LAST_BRANCH_4_FROM_IP
    0x685,      # MSR_LAST_BRANCH_5_FROM_IP
    0x686,      # MSR_LAST_BRANCH_6_FROM_IP
    0x687,      # MSR_LAST_BRANCH_7_FROM_IP
    0x688,      # MSR_LAST_BRANCH_8_FROM_IP
    0x689,      # MSR_LAST_BRANCH_9_FROM_IP
    0x68a,      # MSR_LAST_BRANCH_A_FROM_IP
    0x68b,      # MSR_LAST_BRANCH_B_FROM_IP
    0x68c,      # MSR_LAST_BRANCH_C_FROM_IP
    0x68d,      # MSR_LAST_BRANCH_D_FROM_IP
    0x68e,      # MSR_LAST_BRANCH_E_FROM_IP
    0x68f,      # MSR_LAST_BRANCH_F_FROM_IP
    0x6c0,      # MSR_LAST_BRANCH_0_TO_LIP
    0x6c1,      # MSR_LAST_BRANCH_1_TO_LIP
    0x6c2,      # MSR_LAST_BRANCH_2_TO_LIP
    0x6c3,      # MSR_LAST_BRANCH_3_TO_LIP
    0x6c4,      # MSR_LAST_BRANCH_4_TO_LIP
    0x6c5,      # MSR_LAST_BRANCH_5_TO_LIP
    0x6c6,      # MSR_LAST_BRANCH_6_TO_LIP
    0x6c7,      # MSR_LAST_BRANCH_7_TO_LIP
    0x6c8,      # MSR_LAST_BRANCH_8_TO_LIP
    0x6c9,      # MSR_LAST_BRANCH_9_TO_LIP
    0x6ca,      # MSR_LAST_BRANCH_A_TO_LIP
    0x6cb,      # MSR_LAST_BRANCH_B_TO_LIP
    0x6cc,      # MSR_LAST_BRANCH_C_TO_LIP
    0x6cd,      # MSR_LAST_BRANCH_D_TO_LIP
    0x6ce,      # MSR_LAST_BRANCH_E_TO_LIP
    0x6cf,      # MSR_LAST_BRANCH_F_TO_LIP
}

msr_masklist = {
    0x1b: ~(1 << 8), # IA_APIC_BASE, mask out the BSP bit
}

residency_counters = namedtuple("residency_counters", ("pc3", "pc6", "pc7", "cc3", "cc6", "cc7"))
residency_counter_msr = residency_counters(pc3=0x3F8, pc6=0x3F9, pc7=0x3FA, cc3=0x3FC, cc6=0x3FD, cc7=0x3FE)
residency_tests = [(["cc3", "pc3"], 0x10), (["cc6", "pc6"], 0x20), (["cc7"], 0x30)]
residency_params = (residency_tests, residency_counter_msr, residency_counters)

def test_pm_generic_profile():
    testmsr.test_msr_consistency("Max non-turbo ratio must be consistent", 0xce, mask=0xff00)
    testpci.test_pci("Bus master disable", 0, 31, 0, 0xa9, bytes=1, shift=2, mask=1, expected_value=1)
    testmsr.test_msr("C1 Auto Demotion Enable", 0xe2, shift=26, mask=1, expected_value=1)
    testmsr.test_msr("C3 Auto Demotion Enable", 0xe2, shift=25, mask=1, expected_value=1)
    testmsr.test_msr("IO MWAIT Redirection Enable", 0xe2, shift=10, mask=1, expected_value=1)
    testmsr.test_msr("C1E Enable", 0x1fc, shift=1, mask=1, expected_value=1)
    testmsr.test_msr("EIST Enable", 0x1a0, shift=16, mask=1, expected_value=1)
    testmsr.test_msr("Turbo Enable", 0x1a0, shift=38, mask=1, expected_value=0)
    testmsr.test_msr("EIST Hardware Coordination Enable", 0x1aa, mask=1, expected_value=0)
    testmsr.test_msr_consistency("IO Capture C-state Range Consistent", 0xe4, shift=16, mask=7)
    io_capture_range, io_capture_range_str = testmsr.MSR("IO Capture C-state Range", bits.bsp_apicid(), 0xe4, 18, 16)
    testsuite.test("IO Capture C-state Range <= 2", io_capture_range <= 2)
    testsuite.print_detail(io_capture_range_str)

def generate_mwait_menu():
    cfg = ""
    cfg += 'menuentry "Current state of C1 and C3 autodemotion" {\n'
    cfg += "    py 'import cpu_nhm; cpu_nhm.show_autodemotion()'\n"
    cfg += '}\n\n'
    cfg += 'menuentry "Toggle C1 and C3 autodemotion" {\n'
    cfg += "    py 'import cpu_nhm; cpu_nhm.toggle_autodemotion()'\n"
    cfg += '}\n\n'
    return cfg

def show_autodemotion():
    with ttypager.page():
        if bitfields.getbits(bits.rdmsr(bits.bsp_apicid(), 0xe2), 26, 25) == 0x3:
            print("C1 and C3 autodemotion are enabled")
        else:
            print("C1 and C3 autodemotion are disabled")

def toggle_autodemotion():
    value = bits.rdmsr(bits.bsp_apicid(), 0xe2)
    if bitfields.getbits(value, 26, 25) == 0x3:
        fieldvalue = 0
    else:
        fieldvalue = 0x3
    value = bitfields.setbits(value, fieldvalue, 26, 25)
    for cpu in bits.cpus():
        bits.wrmsr(cpu, 0xe2, value)
    show_autodemotion()
