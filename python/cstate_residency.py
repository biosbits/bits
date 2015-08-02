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

"""Cstate Residency"""

import bits
import bits.mwait
from collections import namedtuple
import pci
import testsuite
import usb

def residency(residency_counters, residency_counter_msr, sleep_time=3):
    bsp_apicid = bits.bsp_apicid()
    sockets = dict((skt_index, min(apic_list)) for skt_index, apic_list in bits.socket_apic_ids().iteritems())
    rc = {}
    rc_start = {}
    delta = {}
    def read_rc(apic_id):
        return residency_counters(*(bits.rdmsr(apic_id, msr) for msr in residency_counter_msr))
    tsc = bits.rdmsr(bsp_apicid, 0x10)
    for apic_id in sockets.itervalues():
        rc_start[apic_id] = read_rc(apic_id)
    bits.blocking_sleep(sleep_time*1000*1000)
    tsc = float(bits.rdmsr(bsp_apicid, 0x10) - tsc)
    for apic_id in sockets.itervalues():
        rc[apic_id] = read_rc(apic_id)
    for apic_id in sockets.itervalues():
        delta[apic_id] = residency_counters(*((end - start) / tsc for end, start in zip(rc[apic_id], rc_start[apic_id])))
    return delta

def test(residency_tests, residency_counter_msr, residency_counters):
    cpus = bits.cpus()
    for states, hint in residency_tests:
        with bits.mwait.use_hint(hint):
            delta = residency(residency_counters, residency_counter_msr)
            detail = False
            for state in states:
                for apic_id, r in sorted(delta.iteritems()):
                    state_residency = getattr(r, state)
                    testsuite.test("MWAIT hint {:#x}, socket {} {} residency {:4.0%} (expected >= 85%)".format(hint, bits.socket_index(apic_id), state.upper(), state_residency), state_residency >= 0.85)
                    detail = detail or testsuite.show_detail()
            if detail:
                print testsuite.format_detail("Full residency for MWAIT hint {:#x}:".format(hint))
                print testsuite.format_detail(" SKT  APIC" + "".join("{:>6s}".format(field.upper()) for field in residency_counters._fields))
                for apic_id, r in sorted(delta.iteritems()):
                    skt_index = bits.socket_index(apic_id)
                    print testsuite.format_detail("{:4d}  {:#04x}  ".format(skt_index, apic_id) + "  ".join("{:4.0%}".format(field) for field in r))

def test_with_usb_disabled(residency_tests, residency_counter_msr, residency_counters):
    """"Test C-state Residency with USB disabled via BIOS handoff"""
    if usb.handoff_to_os():
        test(residency_tests, residency_counter_msr, residency_counters)
