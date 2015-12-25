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
#
# Portions based on site.py from Python 2.6, under the Python license.

"""Python initialization, to run at BITS startup."""

import _bits

start = _bits._time()

def current_time():
    global start
    return _bits._time()-start

def time_prefix():
    return "[{:02.02f}]".format(current_time())

class import_annotation(object):
    def __init__(self, modname):
        self.modname = modname

    # Context management protocol
    def __enter__(self):
        print "{} Import {}".format(time_prefix(), self.modname)

    def __exit__(self, exc_type, exc_val, exc_tb):
        print "{} Import {} done".format(time_prefix(), self.modname)

class init_annotation(object):
    def __init__(self, modname):
        self.modname = modname

    # Context management protocol
    def __enter__(self):
        print "{} Init {}".format(time_prefix(), self.modname)

    def __exit__(self, exc_type, exc_val, exc_tb):
        print "{} Init {} done".format(time_prefix(), self.modname)

def early_init():
    # Set up redirection first, before importing anything else, so that any
    # errors in subsequent imports will get captured into the log.
    with import_annotation("redirect"):
        import redirect
    with init_annotation("redirect"):
        redirect.redirect()

    # Parse the ACPI SPCR and automatically set up the serial port if present
    with init_annotation("serial port redirection"):
        serial_cmd = "false"
        try:
            with import_annotation("acpi"):
                import acpi
            spcr = acpi.parse_table("SPCR")
            if spcr is not None:
                addr = spcr.base_address
                speed = acpi.baud.get(spcr.baud_rate)
                if addr.address_space_id == acpi.ASID_SYSTEM_IO and addr.register_bit_width == 8 and addr.address != 0 and speed is not None:
                    port = addr.address
                    serial_cmd = "serial --port={:#x} --speed={}".format(port, speed)
        except Exception as e:
            print "Error parsing Serial Port Console Redirect (SPCR) table:"
            print e

    with import_annotation("os"):
        import os
    with init_annotation("os"):
        os.environ["serial_cmd"] = serial_cmd

pydoc_initialized = False

def init_pydoc():
    global pydoc_initialized
    if not pydoc_initialized:
        import redirect
        with redirect.nolog():
            print "Initializing pydoc..."
        import pydoc
        import ttypager
        pydoc.getpager = ttypager.getpager
        pydoc_initialized = True

class _Helper(object):
    """Define the built-in 'help'."""

    def __repr__(self):
        return "Type help() for interactive help, " \
               "or help(object) for help about object."
    def __call__(self, *args, **kwds):
        init_pydoc()
        import pydoc
        import redirect
        with redirect.nolog():
            return pydoc.help(*args, **kwds)

def init():
    with import_annotation("bitsconfig"):
        import bitsconfig
    with init_annotation("bitsconfig"):
        bitsconfig.init()

    with import_annotation("grubcmds"):
        import grubcmds
    with init_annotation("grubcmds"):
        grubcmds.register()

    with import_annotation("bits"):
        import bits

    with import_annotation("os"):
        import os

    with import_annotation("sys"):
        import sys
    sys.argv = []

    with init_annotation("PCI Express MCFG detection"):
        try:
            import acpi
            mcfg = acpi.parse_table("MCFG")
            if mcfg is None:
                print 'No ACPI MCFG Table found. This table is required for PCI Express.'
            else:
                for mcfg_resource in mcfg.resources:
                    if mcfg_resource.segment == 0:
                        if mcfg_resource.address >= (1 << 32):
                            print "Error: PCI Express base above 32 bits is unsupported by BITS"
                            break
                        bits.pcie_set_base(mcfg_resource.address)
                        os.putenv('pciexbase', '{:#x}'.format(mcfg_resource.address))
                        os.putenv('pcie_startbus', '{:#x}'.format(mcfg_resource.start_bus))
                        os.putenv('pcie_endbus', '{:#x}'.format(mcfg_resource.end_bus))
                        break
                else:
                    print "Error initializing PCI Express base from MCFG: no resource with segment 0"
        except Exception as e:
            print "Error occurred initializing PCI Express base from MCFG:"
            print e

    with import_annotation("readline"):
        import readline
    with init_annotation("readline"):
        readline.init()
    with import_annotation("rlcompleter_extra"):
        import rlcompleter_extra

    with import_annotation("testacpi"):
        import testacpi
    with init_annotation("testacpi"):
        testacpi.register_tests()

    if sys.platform == "BITS-EFI":
        with import_annotation("testefi"):
            import testefi
        with init_annotation("testefi"):
            testefi.register_tests()

    with import_annotation("testsmrr"):
        import testsmrr
    with init_annotation("testsmrr"):
        testsmrr.register_tests()

    with import_annotation("smilatency"):
        import smilatency
    with init_annotation("smilatency"):
        smilatency.register_tests()

    with import_annotation("mptable"):
        import mptable
    with init_annotation("mptable"):
        mptable.register_tests()

    with import_annotation("cpulib"):
        from cpudetect import cpulib
    with init_annotation("cpulib"):
        cpulib.register_tests()

    with import_annotation("testsuite"):
        import testsuite
    with init_annotation("testsuite"):
        testsuite.finalize_cfgs()

    with import_annotation("sysinfo"):
        import sysinfo
    with init_annotation("sysinfo"):
        sysinfo.log_sysinfo()

    with import_annotation("smbios"):
        import smbios
    with init_annotation("smbios"):
        smbios.log_smbios_info()

    if sys.platform == "BITS-EFI":
        with import_annotation("efi"):
            import efi
        with init_annotation("efi"):
            efi.log_efi_info()
            efi.register_keyboard_interrupt_handler()

    batch = bitsconfig.config.get("bits", "batch").strip()
    if batch:
        import redirect
        print "\nBatch mode enabled:", batch
        for batch_keyword in batch.split():
            print "\nRunning batch operation", batch_keyword
            try:
                if batch_keyword == "test":
                    testsuite.run_all_tests()
                with redirect.logonly():
                    if batch_keyword == "acpi":
                        import acpi
                        print acpi.dumptables()
                    if batch_keyword == "smbios":
                        import smbios
                        smbios.dump_raw()
            except:
                print "\nError in batch operation", batch_keyword
                import traceback
                traceback.print_exc()

        print "\nBatch mode complete\n"
        redirect.write_logfile("/boot/bits-log.txt")

    with import_annotation("cpumenu"):
        import cpumenu
    with init_annotation("cpumenu"):
        cpumenu.generate_cpu_menu()

    with import_annotation("bootmenu"):
        import bootmenu
    with init_annotation("bootmenu"):
        bootmenu.generate_boot_menu()

    with import_annotation("mwaitmenu"):
        import mwaitmenu
    with init_annotation("mwaitmenu"):
        mwaitmenu.generate_mwait_menu()

    with import_annotation("__builtin__"):
        import __builtin__
    with init_annotation("__builtin__"):
        __builtin__.help = _Helper()
