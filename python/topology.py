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

"""Compute and display processor socket/core/thread topologies."""

import bits
import bitfields
import ttypager
from collections import OrderedDict

def _apickey(apicid):
    """Key function to sort the BSP APIC ID first."""
    if apicid == bits.bsp_apicid():
        return -1
    return apicid

def _display_apicid(apicid):
    """Format APIC IDs to display in hex. Indicate if the APIC ID is the BSP APIC ID"""
    s = '{:#x}'.format(apicid)
    if apicid == bits.bsp_apicid():
        return s + ' (BSP)'
    return s

def topology():
    """Return a dictionary relating each socket APIC ID to its cores' APIC IDs, and each core to its threads' APIC IDs.

    Raises RuntimeError if CPUID leaf 0xb not supported."""
    socket_dict = OrderedDict()
    prev_socket_num = None

    for apicid in sorted(bits.cpus(), key=_apickey):
        current_socket_num, current_core_num, apicid = thread(apicid)

        if current_socket_num != prev_socket_num:
            core_dict = OrderedDict()
            socket_dict[apicid] = core_dict
            prev_core_num = None
        if current_core_num != prev_core_num:
            thread_list = []
            core_dict[apicid] = thread_list
        thread_list.append(apicid)
        prev_socket_num = current_socket_num
        prev_core_num = current_core_num
    return socket_dict

def display():
    """Print processor topology to the screen via pager."""
    with ttypager.page():
        socket_dict = topology()
        for socket, core_dict in socket_dict.iteritems():
            print 'socket {}'.format(_display_apicid(socket))
            for core, threads in core_dict.iteritems():
                print '| core {}'.format(_display_apicid(core))
                for thread in threads:
                    print '| | thread {}'.format(_display_apicid(thread))
            print

def socket(socketid):
    """Return socket ID and IDs of all cores and threads within the socket."""
    core_dict = topology()[socketid]
    return socketid, core_dict.keys(), sum(core_dict.values(), [])

def core(coreid):
    """Return APIC ID of the socket in which the core resides, and all APIC IDs of threads within the core."""
    for socket, core_dict in topology().iteritems():
        try:
            return socket, coreid, core_dict[coreid]
        except KeyError:
            pass
    raise KeyError("Core with APIC ID {:#x} does not exist".format(coreid))

def thread(apicid):
    """Return the thread APIC ID, and the APIC IDs of the core and socket in which the thread resides.

    Raises RuntimeError if CPUID leaf 0xb not supported."""
    if bits.cpuid(apicid, 0).eax < 0xb:
        raise RuntimeError("Cannot compute topology; CPUID leaf 0xb not supported.")
    coreid = apicid >> bitfields.getbits(bits.cpuid(apicid, 0xb, 0).eax, 4, 0)
    socketid = apicid >> bitfields.getbits(bits.cpuid(apicid, 0xb, 1).eax, 4, 0)
    return socketid, coreid, apicid
