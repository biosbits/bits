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

"""Tests and helpers for PCI."""

import bits
import testsuite

def pci_read_helper(bus, dev, fn, reg, pci_read_func, bytes=None, mask=~0, shift=0, **extra_args):
    size = bits.addr_alignment(reg)
    if bytes is not None:
        size = bytes

    value = pci_read_func(bus, dev, fn, reg, bytes=size, **extra_args)
    value = (value >> shift) & mask

    desc = "PCI {:#04x}:{:#04x}.{:#03x} ".format(bus, dev, fn)
    if mask == ~0:
        if shift == 0:
            desc += "reg {:#04x} = {:#x}".format(reg, value)
        else:
            desc += "(reg {:#04x}) >> {} = {:#x}".format(reg, shift, value)
    else:
        desc += "((reg {:#04x}) >> {}) & {:#x} = {:#x}".format(reg, shift, mask, value)

    return value, desc

def test_pci(text, bus, dev, fn, reg, expected_value, bytes=None, mask=~0, shift=0):
    value, desc = pci_read_helper(bus, dev, fn, reg, pci_read_func=bits.pci_read, bytes=bytes, mask=mask, shift=shift)
    status = value == expected_value
    desc += " (Expected {:#x})".format(expected_value)
    if text:
        testsuite.test(text, status)
        testsuite.print_detail(desc)
    else:
        testsuite.test(desc, status)
    return status
