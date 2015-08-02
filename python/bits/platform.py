# Copyright (c) 2015, Intel Corporation
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

"""Hierarchical object-based CPU register (CPUID and MSR) decoding"""

import bits
from bits.cpuids import generate_cpuids
from bits.msrs import sample_msrs
import bits.platformbase
import ttypager

MSRS = bits.platformbase.make_MSRS(sample_msrs())

class CPU(object):
    def __init__(self, apicid):
        self.apicid = apicid
        self.msrs = MSRS(apicid)
        CPUIDS = bits.platformbase.make_CPUIDS(generate_cpuids(apicid))
        self.cpuids = CPUIDS(apicid)

cpus = dict((n, CPU(n)) for n in bits.cpus())

def dump():
    with ttypager.page():
        for num, apicid in enumerate(bits.cpus()):
            heading = "Processor {} -- APIC ID {:#x}".format(num, apicid)
            cpu = cpus[apicid]
            print "{}\n{}".format(heading, "="*len(heading))
            print "\n\n{}\n".format("".join(str(cpuid) for cpuid in cpu.cpuids))
            print "\n\n{}\n".format("".join(str(msr) for msr in cpu.msrs))
