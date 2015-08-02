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

"""testing module."""

import bits
from cpudetect import cpulib
import testsuite
import unittest

def f(x):
    """Test function in a test module."""
    for i in range(x):
        print ("Hello from a function in a module, for the %dth time" % i)

# Save the list of CPUs
cpulist = bits.cpus()

# Build a reverse mapping from APIC ID to CPU number
apicid_index = dict([(apicid, i) for (i, apicid) in enumerate(cpulist)])

def rdmsr_test():
    """Test the rdmsr function"""
    for cpu in cpulist:
        for msr in [0x10, 0x40000000]:
            value = bits.rdmsr(cpu, msr)
            if value is None:
                print "CPU 0x%x MSR 0x%x: GPF" % (cpu, msr)
            else:
                print "CPU 0x%x MSR 0x%x: 0x%x" % (cpu, msr, value)

def ppm_test1():
    pciexbase = bits.pci_read(0, 5, 0, 0x84, 4) & 0xfc000000
    bits.pcie_set_base(pciexbase)
    print 'pciexbase = 0x%x' % bits.pcie_get_base()
    for bus in (0x3f, 0x7f, 0xbf, 0xff):
      print 'bus 0x%x devhide_0 = 0x%x' % (bus, bits.pcie_read(bus, 11, 3, 0xb0, 4))

def ppm_test2():
    pciexbase = bits.pci_read(0, 5, 0, 0x84, 4) & 0xfc000000
    bits.pcie_set_base(pciexbase)
    print 'pciexbase = 0x%x' % bits.pcie_get_base()
    for bus in (0x3f, 0x7f, 0xbf, 0xff):
      print 'bus 0x%x Interrupt Configuration Reg = 0x%x' % (bus, bits.pcie_read(bus, 11, 0, 0x48, 4))

class TestExperiment1(unittest.TestCase):
    def setUp(self):
        self.seq = range(10)

    def testPass(self):
        self.assertEqual(self.seq[0], 0)

    def testFail(self):
        self.assertEqual(self.seq[1], 0)

def experiment1():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestExperiment1)
    unittest.TextTestRunner(verbosity=2).run(suite)
