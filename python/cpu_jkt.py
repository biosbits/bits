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

"""CPU module for Jaketown"""

import bits
import pstate
import testacpi
import testmsr
import testsuite

name = 'Jaketown'

def register_tests():
    testsuite.add_test("MSR consistency test", msr_test)
    testsuite.add_test("_PSD (P-State Dependency) test", testacpi.test_psd_thread_scope, submenu="ACPI Tests")
    power_profile_submenu="Power optimization, profile specific tests"
    testsuite.add_test("Power optimization, Performance profile", power_opt_perf_profile, submenu=power_profile_submenu, runall=False)
    testsuite.add_test("Power optimization, Balance with Performance Bias profile", power_opt_bal_perf_bias_profile, submenu=power_profile_submenu, runall=False)
    testsuite.add_test("Power optimization, Balance with Energy Bias profile", power_opt_bal_energy_bias_profile, submenu=power_profile_submenu, runall=False)
    testsuite.add_test("Power optimization, Low Power profile", power_opt_low_power_profile, submenu=power_profile_submenu, runall=False)
    testsuite.add_test("Test hardware P-state ratios", lambda: pstate.test_hardware_pstates(pstate.turbo_msr))

msr_blacklist = {
    0x0,        # IA32_P5_MC_ADDR
    0x1,        # IA32_P5_MC_TYPE
    0x10,       # IA32_TIME_STAMP_COUNTER
    0x34,       # MSR_SMI_COUNT
    0x39,
    0xE7,       # IA32_MPERF
    0xE8,       # IA32_APERF
    0x198,      # MSR_PERF_STATUS
    0x199,      # IA32_PERF_CTL
    0x19c,      # IA32_THERM_STATUS
    0x1b1,      # IA32_PACKAGE_THERM_STATUS
    0x1c9,      # MSR_LASTBRANCH_TOS
    0x1d9,      # IA32_DEBUGCTL
    0x1dd,      # MSR_LER_FROM_LIP
    0x1de,      # MSR_LER_TO_LIP
    0x1f4,
    0x1f5,
    0x300,
    0x309,      # IA32_FIXED_CTR0
    0x30A,      # IA32_FIXED_CTR1
    0x30B,      # IA32_FIXED_CTR2
    0x3f8,      # Package C-state residency
    0x3f9,      # Package C-state residency
    0x3fa,      # Package C-state residency
    0x3fc,      # Core C-state residency
    0x3fd,      # Core C-state residency
    0x3fe,      # Core C-state residency
    0x60d,      # MSR_PKG_C2_RESIDENCY
    0x611,      # PKG_ENERGY_STATUS
    0x613,      # PACKAGE_RAPL_PERF_STATUS
    0x614,      # PKG_POWER_SKU
    0x619,      # DRAM_ENERGY_STATUS
    0x639,      # PP0_ENERGY_STATUS
    0x63b,      # MSR_PP0_PERF_STATUS
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

def is_cpu():
    return bits.cpuid(bits.bsp_apicid(),1).eax & ~0xf == 0x206d0

def init():
    pass

def msr_test():
    testmsr.rdmsr_consistent(msr_blacklist, msr_masklist)

def mwait_hint_to_cstate(hint):
    """Returns the CPU name and cpu-specific C-state for the encoded MWAIT hint provided."""
    mwait_hints = {0xf0:'C0', 0x00:'C1', 0x01:'C1E', 0x10:'C3', 0x20:'C6', 0x30:'C7', 0x31:'C7S'}
    return '%s %s' % (name, mwait_hints[hint])

def power_opt_perf_profile():
    # If CPUID.06H:ECX.SETBH[bit 3] is set, then the processor supports
    # performance-energy bias preference and IA32_ENERGY_PERF_BIAS (1B0H) MSR
    setbh = (bits.cpuid(bits.bsp_apicid(),6).ecx >> 3) & 1
    if not setbh:
        return
    testmsr.test_msr_consistency("Energy Performance Bias", 0x1b0, mask=0xf)
    testmsr.test_msr("Energy Performance Bias 0-3", 0x1b0, expected_value=0, shift=2, mask=3)

def power_opt_bal_perf_bias_profile():
    # If CPUID.06H:ECX.SETBH[bit 3] is set, then the processor supports
    # performance-energy bias preference and IA32_ENERGY_PERF_BIAS (1B0H) MSR
    setbh = (bits.cpuid(bits.bsp_apicid(),6).ecx >> 3) & 1
    if not setbh:
        return
    testmsr.test_msr_consistency("Energy Performance Bias", 0x1b0, mask=0xf)
    testmsr.test_msr("Energy Performance Bias 4-7", 0x1b0, expected_value=1, shift=2, mask=3)

def power_opt_bal_energy_bias_profile():
    # If CPUID.06H:ECX.SETBH[bit 3] is set, then the processor supports
    # performance-energy bias preference and IA32_ENERGY_PERF_BIAS (1B0H) MSR
    setbh = (bits.cpuid(bits.bsp_apicid(),6).ecx >> 3) & 1
    if not setbh:
        return
    testmsr.test_msr_consistency("Energy Performance Bias", 0x1b0, mask=0xf)
    testmsr.test_msr("Energy Performance Bias 8-11", 0x1b0, expected_value=2, shift=2, mask=3)

def power_opt_low_power_profile():
    # If CPUID.06H:ECX.SETBH[bit 3] is set, then the processor supports
    # performance-energy bias preference and IA32_ENERGY_PERF_BIAS (1B0H) MSR
    setbh = (bits.cpuid(bits.bsp_apicid(),6).ecx >> 3) & 1
    if not setbh:
        return
    testmsr.test_msr_consistency("Energy Performance Bias", 0x1b0, mask=0xf)
    testmsr.test_msr("Energy Performance Bias 12-15", 0x1b0, expected_value=3, shift=2, mask=3)
