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

"""MP Table module."""

from __future__ import print_function
import bits
import bitfields
import ctypes
import struct
import unpack
import testsuite
import ttypager
import sys

valid_address_ranges = [
    (0x9FC00, 0x400),
    (0xF0000, 0x10000),
]

bad_address_ranges = [
    (0xE0000, 0x10000),
]

def find_mp_table():
    if sys.platform == "BITS-EFI":
        import efi
        return efi.system_table.ConfigurationTableDict.get(efi.MPS_TABLE_GUID)

    address_ranges = valid_address_ranges + bad_address_ranges
    bda_address = 0x400
    ebda_address = ctypes.c_uint16.from_address(bda_address + 0x14).value << 4
    if ebda_address:
        address_ranges.insert(0, (ebda_address, 0x400))
    for address, size in address_ranges:
        mem = bits.memory(address, size)
        for offset in range(0, size, 16):
            signature = (ctypes.c_char * 4).from_address(address + offset).value
            if signature == "_MP_":
                length = ctypes.c_ubyte.from_address(address + offset + 8).value
                if length == 1:
                    csum = sum(map(ord, mem[offset:offset+16])) & 0xff
                    if csum == 0:
                        return address + offset
    return None

class MPTable(unpack.Struct):
    """Find and decode the MP Table."""

    def __new__(cls):
        offset = find_mp_table()
        if offset is None:
            return None

        mp = super(MPTable, cls).__new__(cls)
        mp._floating_pointer_memory = bits.memory(offset, 0x10)
        return mp

    def __init__(self):
        super(MPTable, self).__init__()
        u = unpack.Unpackable(self._floating_pointer_memory)
        self.add_field('floating_pointer', FloatingPointer(u))

        self._base_header_memory = bits.memory(self.floating_pointer.physical_address_pointer, 44)
        u = unpack.Unpackable(self._base_header_memory)
        self.add_field('header', Header(u), "\n\n{!r}")

        self._base_table_memory = bits.memory(self.floating_pointer.physical_address_pointer, self.header.base_table_length)
        u = unpack.Unpackable(self._base_table_memory)
        u.skip(44)
        self.add_field('base_structures', unpack.unpack_all(u, _base_structures), unpack.format_each("\n\n{!r}"))

        self._extended_table_memory = bits.memory(self.floating_pointer.physical_address_pointer + self.header.base_table_length, self.header.extended_table_length)
        u = unpack.Unpackable(self._extended_table_memory)
        self.add_field('extended_structures', unpack.unpack_all(u, _extended_structures), unpack.format_each("\n\n{!r}"))

class FloatingPointer(unpack.Struct):
    def __init__(self, u):
        super(FloatingPointer, self).__init__()
        self.raw_data = u.unpack_peek_rest()
        self.add_field('anchor_string', u.unpack_one("4s"))
        self.add_field('physical_address_pointer', u.unpack_one("<I"))
        self.add_field('length', u.unpack_one("B"))
        self.add_field('spec_revision', u.unpack_one("B"))
        self.add_field('checksum', u.unpack_one("B"))
        self.add_field('mp_feature_info_1', u.unpack_one("B"))
        self.add_field('mp_feature_info_2', u.unpack_one("B"))
        self.add_field('multiple_clock_sources', bool(bitfields.getbits(self.mp_feature_info_2, 6)), "mp_feature_info_2[6]={}")
        self.add_field('imcrp_present', bool(bitfields.getbits(self.mp_feature_info_2, 7)), "mp_feature_info_2[7]={}")
        self.add_field('mp_feature_info_3', u.unpack_one("B"))
        self.add_field('mp_feature_info_4', u.unpack_one("B"))
        self.add_field('mp_feature_info_5', u.unpack_one("B"))
        if not u.at_end():
            self.add_field('data', u.unpack_rest())

class Header(unpack.Struct):
    def __init__(self, u):
        super(Header, self).__init__()
        self.raw_data = u.unpack_peek_rest()
        self.add_field('signature', u.unpack_one("4s"))
        self.add_field('base_table_length', u.unpack_one("<H"))
        self.add_field('spec_revision', u.unpack_one("B"))
        self.add_field('checksum', u.unpack_one("B"))
        self.add_field('oem_id', u.unpack_one("8s"))
        self.add_field('product_id', u.unpack_one("12s"))
        self.add_field('oem_table_pointer', u.unpack_one("<I"))
        self.add_field('oem_table_size', u.unpack_one("<H"))
        self.add_field('entry_count', u.unpack_one("<H"))
        self.add_field('local_apic_address', u.unpack_one("<I"))
        self.add_field('extended_table_length', u.unpack_one("<H"))
        self.add_field('extended_table_checksum', u.unpack_one("B"))
        u.skip(1)   # reserved byte
        if not u.at_end():
            self.add_field('data', u.unpack_rest())

class MpBaseStructure(unpack.Struct):
    def __new__(cls, u):
        t = u.unpack_peek_one("B")
        if cls.mp_structure_type is not None and t != cls.mp_structure_type:
            return None
        return super(MpBaseStructure, cls).__new__(cls)

    def __init__(self, u):
        super(MpBaseStructure, self).__init__()
        self.start_offset = u.offset
        entry_type = u.unpack_peek_one("B")
        if entry_type == 0:
            length = 20
        else:
            length = 8
        self.u = u.unpack_unpackable(length)
        self.raw_data = self.u.unpack_peek_rest()
        self.add_field('entry_type', self.u.unpack_one("B"))
        self.add_field('length', length)

    def fini(self):
        if not self.u.at_end():
            self.add_field('data', self.u.unpack_rest())
        del self.u

class Processor(MpBaseStructure):
    mp_structure_type = 0

    def __init__(self, u):
        super(Processor, self).__init__(u)
        u = self.u
        self.add_field('local_apic_id', u.unpack_one("B"))
        self.add_field('local_apic_version', u.unpack_one("B"))
        self.add_field('cpu_flags', u.unpack_one("B"))
        self.add_field('enable', bool(bitfields.getbits(self.cpu_flags, 0)), "cpu_flags[0]={}")
        self.add_field('bsp', bool(bitfields.getbits(self.cpu_flags, 1)), "cpu_flags[1]={}")
        self.add_field('cpu_signature', u.unpack_one("<I"))
        self.add_field('feature_flags', u.unpack_one("<I"))
        self.add_field('reserved', u.unpack_one("<Q"))
        self.fini()

class Bus(MpBaseStructure):
    mp_structure_type = 1

    def __init__(self, u):
        super(Bus, self).__init__(u)
        u = self.u
        self.add_field('bus_id', u.unpack_one("B"))
        self.add_field('bus_type', u.unpack_one("6s"))
        self.fini()

class IOApic(MpBaseStructure):
    mp_structure_type = 2

    def __init__(self, u):
        super(IOApic, self).__init__(u)
        u = self.u
        self.add_field('io_apic_id', u.unpack_one("B"))
        self.add_field('io_apic_version', u.unpack_one("B"))
        self.add_field('io_apic_flags', u.unpack_one("B"))
        self.add_field('enable', bool(bitfields.getbits(self.io_apic_flags, 0)), "io_apic_flags[0]={}")
        self.add_field('io_apic_address', u.unpack_one("<I"))
        self.fini()

_int_types = {
    0: 'INT',
    1: 'NMI',
    2: 'SMI',
    3: 'ExtINT',
}

_polarity = {
    0b00: 'Conforms to specifications of bus (for example, EISA is active-low for level-triggered interrupts)',
    0b01: 'Active high',
    0b10: 'Reserved',
    0b11: 'Active low',
}

_trigger_modes = {
    0b00: "Conforms to specifications of bus (for example, ISA is edge-triggered)",
    0b01: "Edge-triggered",
    0b10: "Reserved",
    0b11: "Level-triggered",
}

class IOInterrupt(MpBaseStructure):
    mp_structure_type = 3

    def __init__(self, u):
        super(IOInterrupt, self).__init__(u)
        u = self.u
        self.add_field('interrupt_type', u.unpack_one("B"), unpack.format_table("{}", _int_types))
        self.add_field('io_interrupt_flags', u.unpack_one("B"))
        self.add_field('polarity', bitfields.getbits(self.io_interrupt_flags, 1, 0), unpack.format_table("io_interrupt_flags[1:0]={}", _polarity))
        self.add_field('trigger', bitfields.getbits(self.io_interrupt_flags, 3, 2), unpack.format_table("io_interrupt_flags[3:2]={}", _trigger_modes))
        u.skip(1)
        self.add_field('source_bus_id', u.unpack_one("B"))
        self.add_field('source_bus_irq', u.unpack_one("B"))
        self.add_field('destination_io_apic_id', u.unpack_one("B"))
        self.add_field('destination_io_apic_int_pin', u.unpack_one("B"))
        self.fini()

class LocalInterrupt(MpBaseStructure):
    mp_structure_type = 4

    def __init__(self, u):
        super(LocalInterrupt, self).__init__(u)
        u = self.u
        self.add_field('interrupt_type', u.unpack_one("B"), unpack.format_table("{}", _int_types))
        self.add_field('local_interrupt_flags', u.unpack_one("B"))
        self.add_field('polarity', bitfields.getbits(self.local_interrupt_flags, 1, 0), unpack.format_table("local_interrupt_flags[1:0]={}", _polarity))
        self.add_field('trigger', bitfields.getbits(self.local_interrupt_flags, 3, 2), unpack.format_table("local_interrupt_flags[3:2]={}", _trigger_modes))
        u.skip(1)
        self.add_field('source_bus_id', u.unpack_one("B"))
        self.add_field('source_bus_irq', u.unpack_one("B"))
        self.add_field('destination_local_apic_id', u.unpack_one("B"))
        self.add_field('destination_local_apic_lint_pin', u.unpack_one("B"))
        self.fini()

class MpBaseStructureUnknown(MpBaseStructure):
    mp_structure_type = None

    def __init__(self, u):
        super(MpBaseStructureUnknown, self).__init__(u)
        self.fini()

_base_structures = [
    Processor,
    Bus,
    IOApic,
    IOInterrupt,
    LocalInterrupt,
    MpBaseStructureUnknown, # Must always come last
]

class MpExtendedStructure(unpack.Struct):
    def __new__(cls, u):
        t = u.unpack_peek_one("B")
        if cls.mp_structure_type is not None and t != cls.mp_structure_type:
            return None
        return super(MpExtendedStructure, cls).__new__(cls)

    def __init__(self, u):
        super(MpExtendedStructure, self).__init__()
        self.start_offset = u.offset
        entry_type, entry_length = u.unpack_peek("BB")
        self.u = u.unpack_unpackable(entry_length)
        self.raw_data = self.u.unpack_peek_rest()
        self.add_field('entry_type', self.u.unpack_one("B"))
        self.add_field('entry_length', self.u.unpack_one("B"))

    def fini(self):
        if not self.u.at_end():
            self.add_field('data', self.u.unpack_rest())
        del self.u

class SystemAddressSpaceMapping(MpExtendedStructure):
    mp_structure_type = 128

    def __init__(self, u):
        super(SystemAddressSpaceMapping, self).__init__(u)
        u = self.u
        _address_types = {
            0: "I/O address",
            1: " Memory address",
            2: "Prefetch address",
        }
        self.add_field('bus_id', u.unpack_one("B"))
        self.add_field('address_type', u.unpack_one("B"), unpack.format_table("{}", _address_types))
        self.add_field('address_base', u.unpack_one("<Q"))
        self.add_field('address_length', u.unpack_one("<Q"))
        self.fini()

class BusHierachyDescriptor(MpExtendedStructure):
    mp_structure_type = 129

    def __init__(self, u):
        super(BusHierachyDescriptor, self).__init__(u)
        u = self.u
        self.add_field('bus_id', u.unpack_one("B"))
        self.add_field('bus_info', u.unpack_one("B"))
        self.add_field('subtractive_decode', bool(bitfields.getbits(self.bus_info, 0)), "bus_info[0]={}")
        self.add_field('parent_bus', u.unpack_one("B"))
        u.skip(3)
        self.fini()

class CompatibilityBusAddressSpaceModifier(MpExtendedStructure):
    mp_structure_type = 130

    def __init__(self, u):
        super(CompatibilityBusAddressSpaceModifier, self).__init__(u)
        u = self.u
        self.add_field('bus_id', u.unpack_one("B"))
        self.add_field('address_modifier', u.unpack_one("B"))
        self.add_field('predefined_list_subtracted', bool(bitfields.getbits(self.address_modifier, 0)), "address_modifier[0]={}")
        self.add_field('predefined_range_list', u.unpack_one("<I"))
        self.fini()

class MpExtendedStructureUnknown(MpExtendedStructure):
    mp_structure_type = None

    def __init__(self, u):
        super(MpExtendedStructureUnknown, self).__init__(u)
        self.fini()

_extended_structures = [
    SystemAddressSpaceMapping,
    BusHierachyDescriptor,
    CompatibilityBusAddressSpaceModifier,
    MpExtendedStructureUnknown, # Must always come last
]

def dump_raw():
    try:
        mp = MPTable()
        s = "MP Table -- Raw bytes and structure decode.\n\n"
        if mp:
            s += str(mp.floating_pointer) + '\n'
            s += bits.dumpmem(mp._floating_pointer_memory) + '\n'

            s += str(mp.header) + '\n'
            s += bits.dumpmem(mp._base_header_memory) + '\n'

            for base_struct in mp.base_structures:
                s += str(base_struct) + '\n'
                s += bits.dumpmem(base_struct.raw_data) + '\n'

            if mp.header.extended_table_length:
                for extended_struct in mp.extended_structures:
                    s += str(extended_struct) + '\n'
                    s += bits.dumpmem(extended_struct.raw_data)  + '\n'
        else:
            s += "MP Table not found.\n"
        ttypager.ttypager_wrap(s, indent=False)
    except:
        print("Error parsing MP Table information:")
        import traceback
        traceback.print_exc()

def dump():
    try:
        mp = MPTable()
        s = "MP Table -- Structure decode.\n\n"
        if mp:
            s += str(mp)
        else:
            s += "MP Table not found.\n"
        ttypager.ttypager_wrap(s, indent=False)
    except:
        print("Error parsing MP Table information:")
        import traceback
        traceback.print_exc()

def register_tests():
    testsuite.add_test("MP Table", test_mptable)

def test_mptable():
    """Test the MP Table"""
    mp = MPTable()
    if mp is None:
        return
    addr = bits.memory_addr(mp._floating_pointer_memory)
    for address, size in bad_address_ranges:
        if addr >= address and addr < address + size:
            bad_address = True
            break
    else:
        bad_address = False
    testsuite.test('MP Floating Pointer Structure at spec-compliant address', not bad_address)
    testsuite.print_detail('Found MP Floating Pointer Structure at bad address {:#x}'.format(addr))
    testsuite.print_detail('MP Floating Pointer Structure must appear at a 16-byte-aligned address')
    testsuite.print_detail('located, in order of preference, in:')
    testsuite.print_detail('- the first kilobyte of the EBDA')
    testsuite.print_detail('- the last kilobyte of system base memory (639k to 640k)')
    testsuite.print_detail('- the 0xF0000 to 0xFFFFF block')
