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

"""PCI Interrupt Routing Table module."""

from __future__ import print_function
import bits
import ctypes
import testsuite
import ttypager

valid_address_ranges = [
    (0xF0000, 0x10000),
]

bad_address_ranges = [
    (0xE0000, 0x10000),
]

def find_pir_table():
    """Find and validate the address of the PCI Interrupt Routing table"""
    address_ranges = valid_address_ranges + bad_address_ranges
    for address, size in address_ranges:
        mem = bits.memory(address, size)
        for offset in range(0, len(mem), 16):
            signature = (ctypes.c_char * 4).from_address(address + offset).value
            if signature == '$PIR':
                table_size = ctypes.c_uint16.from_address(address + offset + 6).value
                if table_size <= (size - offset) and ((table_size - 32) % 16 == 0):
                    csum = sum(ord(mem[c]) for c in range(offset, offset + table_size))
                    if csum & 0xff == 0:
                        return address + offset
    return None

def pir_factory(num_slots):
    """Create variable-sized PIR table based on the number of Slot Entry structures."""
    class PIR(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('reserved', ctypes.c_ubyte * 0x20),
            ('structures', num_slots * SlotEntry),
        ]
    return PIR

def PIR(val):
    """Create class based on decode of an PIR table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_slots = (hdr.table_size - ctypes.sizeof(pir_factory(0))) / ctypes.sizeof(SlotEntry)
    if isinstance(val, str):
        return pir_factory(num_tables).from_buffer_copy(data)
    return pir_factory(num_slots).from_address(addr)

def PIRTable():
    """Find and decode the PCI Interrupt Routing Table."""
    addr = find_pir_table()
    return None if addr is None else PIR(addr)

class TableHeader(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 4),
        ('version', ctypes.c_uint16),
        ('table_size', ctypes.c_uint16),
        ('pci_interrupt_router_bus', ctypes.c_ubyte),
        ('pci_interrupt_router_dev_func', ctypes.c_ubyte),
        ('pci_exclusive_irq_bitmap', ctypes.c_uint16),
        ('compatible_pci_interrupt_router_vendor_id', ctypes.c_uint16),
        ('compatible_pci_interrupt_router_device_id', ctypes.c_uint16),
        ('miniport_data', ctypes.c_uint32),
        ('reserved', ctypes.c_ubyte * 11),
        ('checksum', ctypes.c_ubyte),
    ]

class SlotEntry(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pci_bus_num', ctypes.c_ubyte),
        ('pci_device_num', ctypes.c_ubyte),
        ('link_value_INTA', ctypes.c_ubyte),
        ('irq_bitmap_INTA', ctypes.c_uint16),
        ('link_value_INTB', ctypes.c_ubyte),
        ('irq_bitmap_INTB', ctypes.c_uint16),
        ('link_value_INTC', ctypes.c_ubyte),
        ('irq_bitmap_INTC', ctypes.c_uint16),
        ('link_value_INTD', ctypes.c_ubyte),
        ('irq_bitmap_INTD', ctypes.c_uint16),
        ('slot_num', ctypes.c_ubyte),
        ('reserved', ctypes.c_ubyte),
    ]

def dump_raw():
    try:
        pir = PIRTable()
        s = "PCI Interrupt Routing (PIR) Table -- Raw bytes and structure decode.\n\n"
        if pir:
            s += str(pir.header) + '\n'
            s += bits.dumpmem(bits.cdata.to_bytes(pir.header)) + '\n'

            for slot_entry in pir.structures:
                s += str(slot_entry) + '\n'
                s += bits.dumpmem(bits.cdata.to_bytes(slot_entry)) + '\n'
        else:
            s += "PCI Interrupt Routing (PIR) Table not found.\n"
        ttypager.ttypager_wrap(s, indent=False)
    except:
        print("Error parsing PCI Interrupt Routing Table information:")
        import traceback
        traceback.print_exc()

def dump():
    try:
        pir = PIRTable()
        s = "PCI Interrupt Routing (PIR) Table -- Structure decode.\n\n"
        if pir:
            s += str(pir)
        else:
            s += "PCI Interrupt Routing (PIR) Table not found.\n"
        ttypager.ttypager_wrap(s, indent=False)
    except:
        print("Error parsing PCI Interrupt Routing (PIR) Table information:")
        import traceback
        traceback.print_exc()

def register_tests():
    testsuite.add_test("PCI Interrupt Routing Table", test_pirtable)

def test_pirtable():
    """Test the PCI Interrupt Routing Table"""
    pir = PIRTable()
    if pir is None:
        return
    addr = bits.memory_addr(pir._table_memory)
    for address, size in bad_address_ranges:
        if addr >= address and addr < address + size:
            bad_address = True
            break
    else:
        bad_address = False
    testsuite.test('PCI Interrupt Routing Table spec-compliant address', not bad_address)
    testsuite.print_detail('Found PCI Interrupt Routing Table at bad address {:#x}'.format(addr))
    testsuite.print_detail('$PIR Structure must appear at a 16-byte-aligned address')
    testsuite.print_detail('located in the 0xF0000 to 0xFFFFF block')
