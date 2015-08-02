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

"""Test SMRR module."""

import bits
import testmsr
import testsuite

def register_tests():
    testsuite.add_test("SMRR configuration", test_smrr)

def test_smrr():
    """Test the SMRR-related configuration"""
    cpus = sorted(bits.cpus())
    if not testmsr.test_msr_consistency(text='IA32_MTRRCAP Bit [11] (SMRR Supported) must be consistent', first_msr=0xfe, shift=11, mask=1):
        return
    ia32_mtrrcap = bits.rdmsr(cpus[0], 0xfe)
    if ia32_mtrrcap is not None and not ia32_mtrrcap & (1 << 11):
        return
    if testmsr.msr_available(0x1f2) and testmsr.msr_available(0x1f3):
        MSR_SMRR_PHYS_BASE = 0x1f2
        MSR_SMRR_PHYS_MASK = 0x1f3
    elif testmsr.msr_available(0xa0) and testmsr.msr_available(0xa1):
        MSR_SMRR_PHYS_BASE = 0xa0
        MSR_SMRR_PHYS_MASK = 0xa1
        return
    else:
        return
    testmsr.test_msr_consistency(text='SMRR must be consistent across all processors', first_msr=MSR_SMRR_PHYS_BASE, last_msr=MSR_SMRR_PHYS_MASK)
    for apicid in cpus:
        smrr_physbase, smrr_physbase_str = testmsr.MSR('SMRR Physbase', apicid, MSR_SMRR_PHYS_BASE, 31, 12)
        smrr_type, smrr_type_str = testmsr.MSR('SMRR Type', apicid, MSR_SMRR_PHYS_BASE, 2, 0)
        smrr_physmask, smrr_physmask_str = testmsr.MSR('SMRR Physmask', apicid, MSR_SMRR_PHYS_MASK, 31, 12)
        smrr_valid, smrr_valid_str = testmsr.MSR('SMRR Valid', apicid, MSR_SMRR_PHYS_MASK, 11, 11)
        testsuite.test('SMRR_PHYSBASE must be aligned on an 8MB boundary', (smrr_physbase % 0x800) == 0)
        testsuite.print_detail(smrr_physbase_str)
        testsuite.print_detail('SMRR_PHYSBASE % 0x800 must be 0')
        testsuite.test('SMRR Type must be Write-Back (Best performance)', smrr_type == 6)
        testsuite.print_detail(smrr_type_str)
        testsuite.print_detail('SMRR Type must be 6')
        testsuite.test('SMRR size must be at least 8MB', smrr_physmask >= 0x800)
        testsuite.print_detail(smrr_physmask_str)
        testsuite.print_detail('SMRR Physmask must be >= 0x800')
        testsuite.test('SMRR Valid bit must be 1', smrr_valid)
        testsuite.print_detail(smrr_valid_str)
