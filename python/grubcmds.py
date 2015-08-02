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

"""GRUB commands implemented in Python."""

# All of the commands and other functions in this module have no value from
# Python, only from GRUB; only .register() needs to get called, at
# initialization time.
__all__ = ["register"]

import bits, sys, os, argparse, testcpuid, testmsr, testpci, testutil

def cmd_pydoc(args):
    import init
    init.init_pydoc()
    import pydoc, os
    try:
        oldargv = sys.argv
    except AttributeError:
        oldargv = None
    oldpath = sys.path
    oldterm = os.getenv("TERM")
    try:
        sys.argv = args
        sys.path = [''] + oldpath
        os.putenv("TERM", "dumb")
        pydoc.cli()
    finally:
        if oldargv is None:
            del sys.argv
        else:
            sys.argv = oldargv
        sys.path = oldpath
        if oldterm is None:
            os.unsetenv("TERM")
        else:
            os.putenv("TERM", oldterm)

def parse_int(s, name, max_bound=None, min_bound=None):
    modified = s
    if s.endswith('h') or s.endswith('H'):
        modified = '0x' + s.rstrip('hH')
    try:
        value = int(modified, 0)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid {0} value: {1!r}".format(name, s))
    if value < 0:
        raise argparse.ArgumentTypeError("{0} value must not be negative: {1!r}".format(name, s))
    if max_bound is not None and value > max_bound:
        raise argparse.ArgumentTypeError("{0} value too large: {1!r}".format(name, s))
    if min_bound is not None and value < min_bound:
        raise argparse.ArgumentTypeError("{0} value too small: {1!r}".format(name, s))
    return value

def parse_shift(s):
    return parse_int(s, "shift", 63)

def parse_mask(s):
    return parse_int(s, "mask", 2**64 - 1)

def parse_msr(s):
    return parse_int(s, "MSR", 2**32 - 1)

def parse_msr_value(s):
    return parse_int(s, "VALUE", 2**64 - 1)

def parse_function(s):
    return parse_int(s, "FUNCTION", 2**32 - 1)

def parse_index(s):
    return parse_int(s, "INDEX", 2**32 - 1)

def parse_pciexbase(s):
    return parse_int(s, "pciexbase", 2**32 - 1, 1)

def parse_pci_bus(s):
    return parse_int(s, "BUS", 255)

def parse_pci_dev(s):
    return parse_int(s, "DEVICE", 2**5 - 1)

def parse_pci_fun(s):
    return parse_int(s, "FUNCTION", 2**3 - 1)

def parse_pci_reg(s):
    return parse_int(s, "REGISTER", 2**8 - 1)

def parse_pcie_reg(s):
    return parse_int(s, "REGISTER", 2**12 - 1)

def parse_pci_value(s):
    return parse_int(s, "VALUE", 2**64 - 1)

brandstring_argparser = argparse.ArgumentParser(prog='brandstring', description='Display brand string obtained via CPUID instruction')

def cmd_brandstring(args):
    uniques = {}
    for cpu in bits.cpus():
        uniques.setdefault(bits.brandstring(cpu), []).append(cpu)
    for value in sorted(uniques.iterkeys()):
        cpus = uniques[value]
        print 'Brandstring: "{0}"'.format(value)
        print "On {0} CPUs: {1}".format(len(cpus), testutil.apicid_list(cpus))

cpuid32_argparser = argparse.ArgumentParser(prog='cpuid32', description='Display registers returned by CPUID instruction')
cpuid32_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to values read (default=~0)')
cpuid32_argparser.add_argument('-A', '--eax-mask', default=~0, type=parse_mask, help='Mask to apply to EAX; overrides --mask (default=~0)', metavar='MASK')
cpuid32_argparser.add_argument('-B', '--ebx-mask', default=~0, type=parse_mask, help='Mask to apply to EBX; overrides --mask (default=~0)', metavar='MASK')
cpuid32_argparser.add_argument('-C', '--ecx-mask', default=~0, type=parse_mask, help='Mask to apply to ECX; overrides --mask (default=~0)', metavar='MASK')
cpuid32_argparser.add_argument('-D', '--edx-mask', default=~0, type=parse_mask, help='Mask to apply to EDX; overrides --mask (default=~0)', metavar='MASK')
cpuid32_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
cpuid32_argparser.add_argument('function', type=parse_function, help='Function number used in EAX')
cpuid32_argparser.add_argument('index', type=parse_index, help='Index number used in ECX', nargs='?')

def cmd_cpuid32(args):
    uniques, desc = testcpuid.cpuid_helper(args.function, args.index, args.shift, args.mask, args.eax_mask, args.ebx_mask, args.ecx_mask, args.edx_mask)
    print "\n".join(desc)
    return True

def do_pci_write(args, pci_read_func, pci_write_func, **extra_args):
    size = bits.addr_alignment(args.reg)
    if args.bytes is not None:
        size = args.bytes

    args.adj_value = value = (args.value & args.mask) << args.shift
    if args.rmw:
        value = value | (pci_read_func(args.bus, args.dev, args.fn, args.reg, bytes=size, **extra_args) & ~(args.mask << args.shift))
    pci_write_func(args.bus, args.dev, args.fn, args.reg, value, bytes=size, **extra_args)

    args.op = '='
    if args.rmw:
        args.op = '|='
    prefix = "PCI {bus:#04x}:{dev:#04x}.{fn:#03x} reg {reg:#04x} {op}".format(**vars(args))
    if args.mask == ~0:
        if args.shift == 0:
            print prefix, "{value:#x}".format(**vars(args))
        else:
            print prefix, "{value:#x} << {shift} ({adj_value:#x})".format(**vars(args))
    else:
        print prefix, "({value:#x} & {mask}) << {shift} ({adj_value:#x})".format(**vars(args))

    return True

pci_read_argparser = argparse.ArgumentParser(prog='pci_read', description='Read PCI register')
pci_read_argparser.add_argument('-b', '--bytes', type=int, choices=[1,2,4], help='Bytes to read for PCI value')
pci_read_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
pci_read_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
pci_read_argparser.add_argument('bus', type=parse_pci_bus, help='Bus number')
pci_read_argparser.add_argument('dev', type=parse_pci_dev, help='Device number')
pci_read_argparser.add_argument('fn', type=parse_pci_fun, help='Function number')
pci_read_argparser.add_argument('reg', type=parse_pci_reg, help='Register number')

def cmd_pci_read(args):
    value, desc = testpci.pci_read_helper(args.bus, args.dev, args.fn, args.reg, pci_read_func=bits.pci_read, bytes=args.bytes, mask=args.mask, shift=args.shift)
    print desc
    return True

pci_write_argparser = argparse.ArgumentParser(prog='pci_write', description='Write PCI register')
pci_write_argparser.add_argument('-b', '--bytes', type=int, choices=[1,2,4], help='Bytes to write for PCI value')
pci_write_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
pci_write_argparser.add_argument('-r', '--rmw', action='store_true', help='Read-modify-write operation (default=disabled)')
pci_write_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
pci_write_argparser.add_argument('bus', type=parse_pci_bus, help='Bus number')
pci_write_argparser.add_argument('dev', type=parse_pci_dev, help='Device number')
pci_write_argparser.add_argument('fn', type=parse_pci_fun, help='Function number')
pci_write_argparser.add_argument('reg', type=parse_pci_reg, help='Register number')
pci_write_argparser.add_argument('value', type=parse_pci_value, help='Value to write')

def cmd_pci_write(args):
    return do_pci_write(args, bits.pci_read, bits.pci_write)

def get_pciexbase(memaddr_arg):
    """Get the pciexbase from the environment or the specified argument.

    The argument takes precedence if not None."""
    if memaddr_arg is not None:
        return memaddr_arg
    baseaddr = os.getenv("pciexbase")
    if baseaddr is None:
        print "No PCIE memory base address specified."
        return None
    try:
        baseaddr = parse_int(baseaddr, "pciexbase environment variable", 2**32 - 1)
    except argparse.ArgumentTypeError:
        print sys.exc_info()[1]
        return None
    return baseaddr

pcie_read_argparser = argparse.ArgumentParser(prog='pcie_read', description='Read PCIE register')
pcie_read_argparser.add_argument('-b', '--bytes', type=int, choices=[1,2,4,8], help='Bytes to read for PCIe value')
pcie_read_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
pcie_read_argparser.add_argument('-p', '--memaddr', type=parse_pciexbase, help='PCIE memory base address (default=$pciexbase)')
pcie_read_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
pcie_read_argparser.add_argument('bus', type=parse_pci_bus, help='Bus number')
pcie_read_argparser.add_argument('dev', type=parse_pci_dev, help='Device number')
pcie_read_argparser.add_argument('fn', type=parse_pci_fun, help='Function number')
pcie_read_argparser.add_argument('reg', type=parse_pcie_reg, help='Register number')

def cmd_pcie_read(args):
    baseaddr = get_pciexbase(args.memaddr)
    if baseaddr is None:
        return False
    value, desc = testpci.pci_read_helper(args.bus, args.dev, args.fn, args.reg, pci_read_func=bits.pcie_read, bytes=args.bytes, mask=args.mask, shift=args.shift, memaddr=baseaddr)
    print desc
    return True

pcie_write_argparser = argparse.ArgumentParser(prog='pcie_write', description='Write PCIE register')
pcie_write_argparser.add_argument('-b', '--bytes', type=int, choices=[1,2,4,8], help='Bytes to write for PCIE value')
pcie_write_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
pcie_write_argparser.add_argument('-p', '--memaddr', type=parse_pciexbase, help='PCIE memory base address (default=$pciexbase)')
pcie_write_argparser.add_argument('-r', '--rmw', action='store_true', help='Read-modify-write operation (default=disabled)')
pcie_write_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
pcie_write_argparser.add_argument('bus', type=parse_pci_bus, help='Bus number')
pcie_write_argparser.add_argument('dev', type=parse_pci_dev, help='Device number')
pcie_write_argparser.add_argument('fn', type=parse_pci_fun, help='Function number')
pcie_write_argparser.add_argument('reg', type=parse_pcie_reg, help='Register number')
pcie_write_argparser.add_argument('value', type=parse_pci_value, help='Value to write')

def cmd_pcie_write(args):
    baseaddr = get_pciexbase(args.memaddr)
    if baseaddr is None:
        return False
    return do_pci_write(args, bits.pcie_read, bits.pcie_write, memaddr=baseaddr)

rdmsr_argparser = argparse.ArgumentParser(prog='rdmsr', description='Read MSR')
rdmsr_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
rdmsr_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
rdmsr_argparser.add_argument('msr', type=parse_msr, help='MSR number')

def cmd_rdmsr(args):
    uniques, desc = testmsr.rdmsr_helper(msr=args.msr, shift=args.shift, mask=args.mask)
    print "\n".join(desc)
    value = uniques.keys()[0]
    return len(uniques) == 1 and value is not None

def parse_hint(s):
    return parse_int(s, "HINT")

wrmsr_argparser = argparse.ArgumentParser(prog='wrmsr', description='Write MSR')
wrmsr_argparser.add_argument('-s', '--shift', default=0, type=parse_shift, help='Shift count for mask and value (default=0)')
wrmsr_argparser.add_argument('-m', '--mask', default=~0, type=parse_mask, help='Mask to apply to value (default=~0)')
wrmsr_argparser.add_argument('-r', '--rmw', action='store_true', help='Read-modify-write operation (default=disabled)')
wrmsr_argparser.add_argument('msr', type=parse_msr, help='MSR number')
wrmsr_argparser.add_argument('value', type=parse_msr_value, help='MSR value')

def cmd_wrmsr(args):
    rd_fail = []
    wr_fail = []
    success = []

    def process_wrmsr(apicid):
        wr_value = 0
        if args.rmw:
            rd_value = bits.rdmsr(apicid, args.msr)
            if rd_value is None:
                rd_fail.append(apicid)
                return
            wr_value = rd_value & ~(args.mask << args.shift)
        wr_value |= (args.value & args.mask) << args.shift
        if bits.wrmsr(apicid, args.msr, wr_value):
            success.append(apicid)
        else:
            wr_fail.append(apicid)

    for apicid in bits.cpus():
        process_wrmsr(apicid)

    if rd_fail or wr_fail:
        if args.rmw:
            op = "|="
        else:
            op = "="
        print "MSR {0:#x} {1} ({2:#x} & {3:#x}) << {4} ({5:#x})".format(args.msr, op, args.value,
                                                                        args.mask, args.shift,
                                                                        (args.value & args.mask) << args.shift)
        if rd_fail:
            print "Read MSR fail (GPF) on {} CPUs: {}".format(len(rd_fail), testutil.apicid_list(rd_fail))
        if wr_fail:
            print "Write MSR fail (GPF) on {} CPUs: {}".format(len(wr_fail), testutil.apicid_list(wr_fail))
        if success:
            print "Write MSR pass on {} CPUs: {}".format(len(success), testutil.apicid_list(success))

    return not rd_fail and not wr_fail

def register_argparsed_command(func, argparser):
    usage = argparser.format_usage().split(' ', 2)[2].rstrip()
    def do_cmd(args):
        try:
            parsed_args = argparser.parse_args(args[1:])
        except SystemExit:
            return False
        return func(parsed_args)
    bits.register_grub_command(argparser.prog, do_cmd, usage, argparser.description)

def register():
    bits.register_grub_command("pydoc", cmd_pydoc, "NAME ... | -k KEYWORD", "Show Python documentation on a NAME or KEYWORD")
    register_argparsed_command(cmd_brandstring, brandstring_argparser)
    register_argparsed_command(cmd_cpuid32, cpuid32_argparser)
    register_argparsed_command(cmd_pci_read, pci_read_argparser)
    register_argparsed_command(cmd_pci_write, pci_write_argparser)
    register_argparsed_command(cmd_pcie_read, pcie_read_argparser)
    register_argparsed_command(cmd_pcie_write, pcie_write_argparser)
    register_argparsed_command(cmd_rdmsr, rdmsr_argparser)
    register_argparsed_command(cmd_wrmsr, wrmsr_argparser)
