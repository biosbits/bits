# Copyright (c) 2014, Intel Corporation
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

def import_start_msg(modname):
    print "Importing {} module...".format(modname),

def end_msg():
    print "done"

def init_start_msg(modname, oneline=True):
    if oneline:
        print "Initializing {} module...".format(modname),
    else:
        print "Initializing {} module...".format(modname)

def init_end_msg(modname):
    print "Initialization {} module done".format(modname)

def early_init():
    # Set up redirection first, before importing anything else, so that any
    # errors in subsequent imports will get captured into the log.
    import_start_msg("redirect")
    import redirect
    end_msg()
    init_start_msg("redirect")
    redirect.redirect()
    init_end_msg("redirect")

    # Parse the ACPI SPCR and automatically set up the serial port if present
    serial_cmd = "false"
    try:
        import_start_msg("acpi")
        import acpi
        end_msg()
        init_start_msg("serial port redirection", False)
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
    init_end_msg("serial port redirection")

    import_start_msg("os")
    import os
    end_msg()
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
    import_start_msg("bitsconfig")
    import bitsconfig
    end_msg()
    init_start_msg("bitsconfig")
    bitsconfig.init()
    end_msg()

    import_start_msg("grubcmds")
    import grubcmds
    end_msg()
    init_start_msg("grubcmds")
    grubcmds.register()
    end_msg()

    import_start_msg("bits")
    import bits
    end_msg()
    import os
    import sys
    try:
        import acpi
        init_start_msg("PCI Express MCFG detection", False)
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
    init_end_msg("PCI Express MCFG detection")

    import_start_msg("readline")
    import readline
    end_msg()
    init_start_msg("readline")
    readline.init()
    end_msg()
    import_start_msg("rlcompleter_extra")
    import rlcompleter_extra
    end_msg()

    import_start_msg("testacpi")
    import testacpi
    end_msg()
    init_start_msg("testacpi")
    testacpi.register_tests()
    end_msg()
    if sys.platform == "BITS-EFI":
        import_start_msg("testefi")
        import testefi
        end_msg()
        init_start_msg("testefi")
        testefi.register_tests()
        end_msg()
    import_start_msg("testsmrr")
    import testsmrr
    end_msg()
    testsmrr.register_tests()
    import_start_msg("smilatency")
    import smilatency
    end_msg()
    init_start_msg("smilatency")
    smilatency.register_tests()
    end_msg()
    import_start_msg("mptable")
    import mptable
    end_msg()
    init_start_msg("mptable")
    mptable.register_tests()
    end_msg()
    import_start_msg("cpulib")
    from cpudetect import cpulib
    end_msg()
    init_start_msg("cpulib")
    cpulib.register_tests()
    end_msg()

    import_start_msg("testsuite")
    import testsuite
    end_msg()
    init_start_msg("testsuite")
    testsuite.finalize_cfgs()
    end_msg()
    import_start_msg("sysinfo")
    import sysinfo
    end_msg()
    init_start_msg("sysinfo", False)
    sysinfo.log_sysinfo()
    init_end_msg("sysinfo")
    import_start_msg("smbios")
    import smbios
    end_msg()
    init_start_msg("smbios", False)
    smbios.log_smbios_info()
    init_end_msg("smbios")
    if sys.platform == "BITS-EFI":
        import_start_msg("efi")
        import efi
        end_msg()
        init_start_msg("efi", False)
        efi.log_efi_info()
        init_end_msg("efi")

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

    import_start_msg("cpumenu")
    import cpumenu
    end_msg()
    init_start_msg("cpumenu")
    cpumenu.generate_cpu_menu()
    end_msg()

    import_start_msg("bootmenu")
    import bootmenu
    end_msg()
    init_start_msg("bootmenu")
    bootmenu.generate_boot_menu()
    end_msg()

    import_start_msg("mwaitmenu")
    import mwaitmenu
    end_msg()
    init_start_msg("mwaitmenu")
    mwaitmenu.generate_mwait_menu()
    end_msg()

    import_start_msg("builtin")
    import __builtin__
    end_msg()
    __builtin__.help = _Helper()
