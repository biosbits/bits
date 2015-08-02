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

"""USB module."""

import bits
import os
import pci
import sys
import time

CLASSC_UHCI = 0x0c0300
CLASSC_OHCI = 0x0c0310
CLASSC_EHCI = 0x0c0320
CLASSC_XHCI = 0x0c0330

EHCI_HCCPARAMS = 8
EHCI_EXTCAP_HANDOFF = 1 # Pre-OS to OS Handoff Synchronization

def find_hc():
    for name, classc in ("UHCI", CLASSC_UHCI), ("OHCI", CLASSC_OHCI), ("EHCI", CLASSC_EHCI), ("XHCI", CLASSC_XHCI):
        for dev in pci.devices_by_classcode(classc):
            print "{name} device found at {bus:#x}:{dev:#x}.{fun:#x}".format(name=name, **dev)

def do_ehci_handoff(bus, dev, fun, warntime=1, failtime=5, to_os=True):
    """Tell BIOS to hand off USB HC to or from OS; returns True if successful and all handoffs occurred in the specified timeout, or False otherwise."""
    ret = True

    os_desired = int(to_os)
    bios_desired = int(not to_os)
    handoff_desc = "from BIOS to OS" if to_os else "from OS to BIOS"

    usbbase = bits.pci_read(bus, dev, fun, pci.BAR0, bytes=4)
    # Need a valid memory resource
    if (usbbase == 0) or (usbbase & 1):
        return None

    hccparams = bits.readl(usbbase + EHCI_HCCPARAMS);
    eecp = (hccparams >> 8) & 0xff;
    count = MAX_HOST_CONTROLLERS = 64
    while eecp and count:
        extcap = bits.pci_read(bus, dev, fun, eecp, bytes=4)
        if extcap & EHCI_EXTCAP_HANDOFF:
            starttime = time.time()
            bits.pci_write(bus, dev, fun, eecp + 3, os_desired, bytes=1)
            while True:
                bios_semaphore = bits.pci_read(bus, dev, fun, eecp + 2, bytes=1)
                duration = time.time() - starttime
                if bios_semaphore == bios_desired:
                    break
                if duration > failtime:
                    ret = False
                    break
        if duration > failtime:
            print "FAIL: USB host controller at PCI {bus:#04x}:{dev:#04x}.{fun:#03x} offset {eecp:#x} failed to hand off {handoff_desc} within {failtime}s (took {duration:0.3f}s)".format(**locals())
        elif duration > warntime:
            print "WARNING: USB host controller at PCI {bus:#04x}:{dev:#04x}.{fun:#03x} offset {eecp:#x} failed to hand off {handoff_desc} within {warntime}s (took {duration:0.3f}s)".format(**locals())
        eecp = (extcap >> 8) & 0xff;
        count -= 1
    if eecp:
        print "Stopping at {} host controllers".format(MAX_HOST_CONTROLLERS)
    return ret

def ehci_handoff_to_os(bus, dev, fun, warntime=1, failtime=5):
    """Tell BIOS to hand off USB HC to OS; returns True if successful and all handoffs occurred in the specified timeout, or False otherwise."""
    return do_ehci_handoff(bus, dev, fun, warntime, failtime, True)

def handoff_to_os():
    """Perform USB handoff to OS (i.e. disable USB devices)"""
    print """
WARNING: This test asks the BIOS to stop handling USB, so if you use a
USB keyboard, you will probably lose the ability to interact with BITS
after this test completes.

You can view the results, and then reboot.

Press escape to quit, or any other key to continue."""
    c = bits.get_key()
    if c == bits.KEY_ESC:
        print 'Test aborted!'
        return False

    ret = False
    for dev in pci.devices_by_classcode(CLASSC_EHCI):
        if ehci_handoff_to_os(**dev):
            ret = True
    return ret
