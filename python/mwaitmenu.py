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

"""MWAIT menu"""

from __future__ import print_function
from _smp import cpu_ping
import bits
from cpudetect import cpulib
from ctypes import *
import time
import ttypager

cpu_ping = CFUNCTYPE(None, c_uint32)(cpu_ping)

def test_latency(count=0x10000):
    start = time.time()
    cpu_ping(count)
    stop = time.time()
    elapsed_ms = int((stop - start) * 1000)
    try:
        itermsg = "with {0} iteration/ms".format(int(round(count / elapsed_ms)))
    except ZeroDivisionError:
        itermsg = "cannot compute iterations/ms"
    with ttypager.page():
        print("elapsed time = {} ms; {}".format(elapsed_ms, itermsg))

created_mwait_menu = False

def generate_mwait_menu():
    global created_mwait_menu
    global supported_mwaits_msg
    if created_mwait_menu:
        return

    cfg = ""
    cfg += 'menuentry "Test round-trip latency via MWAIT" {\n'
    cfg += "    py 'import mwaitmenu; mwaitmenu.test_latency()'\n"
    cfg += '}\n\n'

    cfg += 'menuentry "MWAIT disable" {\n'
    cfg += "    py 'import mwaitmenu; mwaitmenu.mwait_callback(False)'\n"
    cfg += '}\n\n'
    cfg += 'menuentry "MWAIT enable C0" {\n'
    cfg += """    py 'import mwaitmenu; mwaitmenu.mwait_callback(True, "C0", 0xf)'\n"""
    cfg += '}\n\n'

    edx = 0
    if bits.cpuid(bits.bsp_apicid(), 0).eax >= 5:
        edx = bits.cpuid(bits.bsp_apicid(), 5).edx

    mwait_table = (
        ("C1", 0, 4, 1),
        ("C1E", 1, 4, 2),
        ("*C2", 0x10, 8, 1),
        ("*C3", 0x20, 12, 1),
        ("*C4", 0x30, 16, 1),
        ("*C5", 0x40, 20, 1),
        ("*C6", 0x50, 24, 1),
    )

    supported_mwaits_msg = ""
    for name, hint, shift, n in mwait_table:
        if ((edx >> shift) & 0xf) >= n:
            cfg += 'menuentry "MWAIT enable {}" {{\n'.format(name)
            cfg += """    py 'import mwaitmenu; mwaitmenu.mwait_callback(True, "{}", {})'\n""".format(name, hint)
            cfg += '}\n\n'
            supported_mwaits_msg += "MWAIT {} is supported\n".format(name)
        else:
            supported_mwaits_msg += "MWAIT {} is not supported\n".format(name)

    supported_mwaits_msg += "For more information, see the Intel Software Developers Manual, CPUID leaf 5\n"

    cfg += 'menuentry "* MWAIT C-state naming is per CPUID leaf 5 & not processor-specific!" {'
    cfg += "    py 'import mwaitmenu; mwaitmenu.show_supported_mwaits()'\n"
    cfg += '}\n\n'

    cfg += 'menuentry "Current state of Interrupt Break Event" {\n'
    cfg += "    py 'import mwaitmenu; mwaitmenu.show_interrupt_break_event()'\n"
    cfg += '}\n\n'
    cfg += 'menuentry "Toggle Interrupt Break Event" {\n'
    cfg += "    py 'import mwaitmenu; mwaitmenu.toggle_interrupt_break_event()'\n"
    cfg += '}\n\n'

    try:
        cfg += cpulib.generate_mwait_menu()
    except AttributeError as e:
        pass

    bits.pyfs.add_static("mwaitmenu.cfg", cfg)
    created_mwait_menu = True

int_break_event = True

def mwait_callback(use_mwait, name="", hint=0):
    for cpu in bits.cpus():
        bits.set_mwait(cpu, use_mwait, hint, int_break_event)
    with ttypager.page():
        if use_mwait:
            print("MWAIT enabled: {}".format(name))
        else:
            print("MWAIT disabled")

def show_supported_mwaits():
    ttypager.ttypager(supported_mwaits_msg)

def show_interrupt_break_event():
    with ttypager.page():
        if int_break_event:
            print("Interrupt Break Event is enabled")
        else:
            print("Interrupt Break Event is disabled")

def toggle_interrupt_break_event():
    global int_break_event
    int_break_event = not int_break_event
    show_interrupt_break_event()
