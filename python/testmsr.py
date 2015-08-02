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

"""Tests for CPU Model-Specific Registers (MSRs)."""

import bits
import testsuite
import testutil

def MSR(name, apicid, msr, highbit=63, lowbit=0):
    value = bits.rdmsr(apicid, msr)
    if value is not None:
      value = (value & ((1 << (highbit + 1)) - 1)) >> lowbit
    if highbit == 63 and lowbit == 0:
        detail = "{0} (MSR {1:#x}, apicid={2:#x})".format(name, msr, apicid)
    elif highbit == lowbit:
        detail = "{0} (MSR {1:#x} [{2:d}], apicid={3:#x})".format(name, msr, highbit, apicid)
    else:
        detail = "{0} (MSR {1:#x} [{2:d}:{3:d}], apicid={4:#x})".format(name, msr, highbit, lowbit, apicid)
    detail += " = "
    if value is None:
        detail += "GPF"
    else:
        detail += "0x{0:x}".format(value)
    return value, detail

def msr_available(msr):
    """Return True if the specified MSR exists on all CPUs"""
    return all(bits.rdmsr(cpu_num, msr) is not None for cpu_num in bits.cpus())

def rdmsr_consistent(msr_blacklist=set(), msr_masklist=dict()):
    """Rdmsr for all CPU and verify consistent value"""

    cpulist = sorted(bits.cpus())
    for r in [range(0, 0x1000), range(0xC0000000, 0xC0001000)]:
        for msr in r:
            if msr in msr_blacklist:
                continue
            mask = msr_masklist.get(msr, ~0)
            uniques = {}
            for cpu in cpulist:
                value = bits.rdmsr(cpu, msr)
                if value is not None:
                    value &= mask
                uniques.setdefault(value, []).append(cpu)
            testsuite.test("MSR 0x{0:x} consistent".format(msr), len(uniques) == 1)
            # Avoid doing any extra work formatting output when not necessary
            if testsuite.show_detail():
                testsuite.print_detail("{0} unique values".format(len(uniques)))
                for value, cpus in uniques.iteritems():
                    testsuite.print_detail("{0} CPUs: {1}".format(len(cpus), ",".join(str(c) for c in cpus)))
                    if value is None:
                        testsuite.print_detail("MSR 0x{0:x}: GPF".format(msr))
                    else:
                        testsuite.print_detail("MSR 0x{0:x}: 0x{1:x}".format(msr, value))

def rdmsr_helper(msr, shift=0, mask=~0, highbit=63, lowbit=0):
    """Collate the unique values of an MSR across all CPUs.

    Returns a dict mapping MSR values to lists of APIC IDs, and a list of
    strings describing the unique values and the CPUs they occurred on.  Each
    string in the list of descriptions works as an argument to
    testsuite.print_detail, and the first string also works as a test
    description for testsuite.test if no more specific description exists."""
    if (highbit != 63 or lowbit != 0) and (shift != 0 or mask != ~0):
        raise ValueError('Input parameter usage is limited to \"highbit and lowbit\" OR \"shift and mask\".')

    uniques = {}
    for cpu in bits.cpus():
        value = bits.rdmsr(cpu, msr)
        if value is not None:
            if highbit != 63 or lowbit != 0:
                value = (value & ((1 << (highbit + 1)) - 1)) >> lowbit
            else:
                value = (value >> shift) & mask
        uniques.setdefault(value, []).append(cpu)

    msr_desc = "MSR {:#x}".format(msr)
    if shift == 0 and mask == ~0:
        if highbit == lowbit:
            msr_desc += " [{:d}]".format(highbit)
        else:
            msr_desc += " [{:d}:{:d}]".format(highbit, lowbit)
    else:
        if shift != 0:
            msr_desc += " >> {}".format(shift)
        if mask != ~0:
            msr_desc += " & {:#x}".format(mask)

    desc = []

    if len(uniques) > 1 and (None not in uniques):
        mask = testutil.find_common_mask(uniques.iterkeys(), 64)
        desc.append('MSR value is not unique across all logical processors')
        desc.append("Common bits for all processors = {0:#018x}".format(uniques.keys()[0] & mask))
        desc.append("Mask of common bits            = {0:#018x}".format(mask))

    for value in sorted(uniques.iterkeys()):
        cpus = uniques[value]
        desc.append(msr_desc + " = " + ("GPF" if value is None else "{0:#x}".format(value)))
        desc.append("On {0} CPUs: {1}".format(len(cpus), testutil.apicid_list(cpus)))

    return uniques, desc

def test_msr(text, msr, expected_value, shift=0, mask=~0, highbit=63, lowbit=0):
    """Test the value of an MSR.

    Fails if any CPU does not match expected_value.  Pass
    expected_value=None to expect a GPF."""
    uniques, desc = rdmsr_helper(msr=msr, shift=shift, mask=mask, highbit=highbit, lowbit=lowbit)
    if expected_value is None:
        desc[0] += " (Expected GPF)"
    else:
        desc[0] += " (Expected {:#x})".format(expected_value)
    if text:
        desc.insert(0, text)
    status = testsuite.test(desc[0], len(uniques) == 1 and uniques.keys()[0] == expected_value)
    for line in desc[1:]:
        testsuite.print_detail(line)
    return status

def test_msr_consistency(text, first_msr, last_msr=None, shift=0, mask=~0, highbit=63, lowbit=0):
    """Test the consistency of an MSR or range of MSRs across all CPUs."""
    if last_msr is None:
        last_msr = first_msr
    ret = True
    for msr in range(first_msr, last_msr + 1):
        uniques, desc = rdmsr_helper(msr=msr, shift=shift, mask=mask, highbit=highbit, lowbit=lowbit)
        desc[0] += " Consistency Check"
        if text:
            desc = [text] + desc
        status = testsuite.test(desc[0], len(uniques) == 1)
        for line in desc[1:]:
            testsuite.print_detail(line)
        ret = ret and status
    return ret
