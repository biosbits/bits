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

"""ACPI module."""

import _acpi
import bits
import bits.cdata
import bits.pyfs
import bitfields
from cpudetect import cpulib
from collections import OrderedDict
import copy
from cStringIO import StringIO
import ctypes
from ctypes import *
import itertools
import os
import string
import struct
import ttypager
import unpack

def _id(v):
    return v

class TableParseException(Exception): pass

class AcpiBuffer(str):
    def __repr__(self):
        return "AcpiBuffer(" + ' '.join("{:02x}".format(ord(c)) for c in self) + ")"

    def __str__(self):
        return repr(self)

def display_resources(name):
    with ttypager.page():
        for r in get_objpaths(name):
            raw_descriptor = evaluate(r)
            print r
            print repr(raw_descriptor)
            if raw_descriptor is None:
                continue
            for descriptor in parse_descriptor(raw_descriptor):
                print descriptor
            print

class small_resource(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('length', ctypes.c_uint8, 3),
        ('item_name', ctypes.c_uint8, 4),
        ('rtype', ctypes.c_uint8, 1),
    ]

class large_resource(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('item_name', ctypes.c_uint8, 7),
        ('rtype', ctypes.c_uint8, 1),
    ]

SMALL_RESOURCE, LARGE_RESOURCE = 0, 1

class resource_data(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("small_resource",)
    _fields_ = [
        ('small_resource', small_resource),
        ('large_resource', large_resource),
    ]

def parse_descriptor(buf):
    large_factory = [
        parse_VendorDefinedLargeDescriptor,
        parse_ExtendedInterruptDescriptor,
    ]
    small_factory = [
        parse_IRQDescriptor,
        parse_StartDependentFunctionsDescriptor,
        parse_VendorDefinedSmallDescriptor,
    ]
    large_descriptor_dict = {
        1 : Memory24BitRangeDescriptor,
        2 : GenericRegisterDescriptor,
        4 : parse_VendorDefinedLargeDescriptor,
        5 : Memory32BitRangeDescriptor,
        6 : FixedMemory32BitRangeDescriptor,
        7 : DwordAddressSpaceDescriptor,
        8 : WordAddressSpaceDescriptor,
        9 : parse_ExtendedInterruptDescriptor,
        0xA : QwordAddressSpaceDescriptor,
        0xB : ExtendedAddressSpaceDescriptor,
        0xC : None,
        0xE : None,
    }
    small_descriptor_dict = {
        4 : parse_IRQDescriptor,
        5 : DMADescriptor,
        6 : parse_StartDependentFunctionsDescriptor,
        7 : EndDependentFunctionsDescriptor,
        8 : IOPortDescriptor,
        9 : FixedIOPortDescriptor,
        0xA : FixedDMADescriptor,
        0xE : parse_VendorDefinedSmallDescriptor,
        0xF : EndTagDescriptor,
    }
    descriptors = list()
    current = 0
    end = len(buf)
    while current < end:
        cls = None
        res = resource_data.from_buffer_copy(buf, current)
        if res.rtype == LARGE_RESOURCE:
            cls = large_descriptor_dict.get(res.large_resource.item_name)
        elif res.rtype == SMALL_RESOURCE:
            cls = small_descriptor_dict.get(res.small_resource.item_name)
        if cls is not None:
            if cls in large_factory or cls in small_factory:
                descriptor = cls(buf[current:]).from_buffer_copy(buf, current)
            else:
                descriptor = cls.from_buffer_copy(buf, current)
            current += descriptor.length
            if res.rtype == LARGE_RESOURCE:
                current += 3
            elif res.rtype == SMALL_RESOURCE:
                current += 1
            descriptors.append(descriptor)
        else:
            return AcpiBuffer(buf[current:])
    if len(descriptors):
        return tuple(d for d in descriptors)
    return buf

class IRQDescriptor2(bits.cdata.Struct):
    """IRQ Descriptor (Length=2)"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) + [
        ('_INT', ctypes.c_uint16),
    ]

_interrupt_sharing_wakes = {
    0x0: "Exclusive",
    0x1: "Shared",
    0x2: "ExclusiveAndWake",
    0x3: "SharedAndWake",
}

_interrupt_polarities = {
    0: "Active-High",
    1: "Active-Low",
}

_interrupt_modes = {
    0 : "Level-Triggered",
    1 : "Edge-Triggered",
}

class irq_information_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('_HE', ctypes.c_uint8, 1),
        ('reserved', ctypes.c_uint8, 2),
        ('_LL', ctypes.c_uint8, 1),
        ('_SHR', ctypes.c_uint8, 2),
    ]

    _formats = {
        '_HE': unpack.format_table("{}", _interrupt_modes),
        '_LL': unpack.format_table("{}", _interrupt_polarities),
        '_SHR': unpack.format_table("{}", _interrupt_sharing_wakes),
    }

class irq_information(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', irq_information_bits),
    ]

class IRQDescriptor3(bits.cdata.Struct):
    """IRQ Descriptor (Length=3)"""
    _pack_ = 1
    _fields_ = copy.copy(IRQDescriptor2._fields_) +[
        ('information', irq_information),
    ]

def parse_IRQDescriptor(buf):
    des = small_resource.from_buffer_copy(buf)
    if des.length == 2:
        return IRQDescriptor2
    return IRQDescriptor3

class dma_mask_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('_SIZ', ctypes.c_uint8, 2),
        ('_BM', ctypes.c_uint8, 1),
        ('_TYP', ctypes.c_uint8, 2),
    ]
    dma_types = {
        0b00: "compatibility mode",
        0b01: "Type A",
        0b10: "Type B",
        0b11: "Type F",
    }
    logical_device_bus_master_status = {
        0: "Logical device is not a bus master",
        1: "Logical device is a bus master",
    }
    transfer_type_preferences = {
        0b00: "8-bit only",
        0b01: "8- and 16-bit",
        0b10: "16-bit only",
    }
    _formats = {
        '_SIZ': unpack.format_table("{}", transfer_type_preferences),
        '_BM': unpack.format_table("{}", logical_device_bus_master_status),
        '_TYP': unpack.format_table("{}", dma_types),
    }

class dma_mask(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', dma_mask_bits),
    ]

class DMADescriptor(bits.cdata.Struct):
    """DMA Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) +[
        ('_DMA', ctypes.c_uint8),
        ('mask', ctypes.c_uint8),
    ]

class StartDependentFunctionsDescriptor0(bits.cdata.Struct):
    """Start Dependent Functions Descriptor (length=0)"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_)

class priority_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('compatibility_priority', ctypes.c_uint8, 2),
        ('performance_robustness', ctypes.c_uint8, 2),
    ]
    configurations = {
        0: "Good configuration",
        1: "Acceptable configuration",
        2: "Sub-optimal configuration",
    }
    _formats = {
        'compatibility_priority': unpack.format_table("priority[1:0]={}", configurations),
        'performance_robustness': unpack.format_table("priority[3:2]={}", configurations),
    }

class priority(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', priority_bits),
    ]

class StartDependentFunctionsDescriptor1(bits.cdata.Struct):
    """Start Dependent Functions Descriptor (length=1)"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) +[
        ('priority', priority),
    ]

def parse_StartDependentFunctionsDescriptor(buf):
    des = small_resource.from_buffer_copy(buf)
    if des.length == 0:
        return StartDependentFunctionsDescriptor0
    return StartDependentFunctionsDescriptor1

class EndDependentFunctionsDescriptor(bits.cdata.Struct):
    """End Dependent Functions Descriptor"""
    _fields_ = copy.copy(small_resource._fields_)

class ioport_information_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('_DEC', ctypes.c_uint8, 1),
    ]
    _dec_statuses = {
        1 : "logical device decodes 16-bit addresses",
        0 : "logical device only decodes address bits[9:0]",
    }
    _formats = {
        '_DEC': unpack.format_table("{}", _dec_statuses),
    }

class ioport_information(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ioport_information_bits),
    ]

class IOPortDescriptor(bits.cdata.Struct):
    """I/O Port Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) +[
        ('ioport_information', ioport_information),
        ('_MIN', ctypes.c_uint16),
        ('_MAX', ctypes.c_uint16),
        ('_ALN', ctypes.c_uint8),
        ('_LEN', ctypes.c_uint8),
    ]

class FixedIOPortDescriptor(bits.cdata.Struct):
    """Fixed Location I/O Port Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) + [
        ('_BAS', ctypes.c_uint16),
        ('_LEN', ctypes.c_uint8),
    ]

class FixedDMADescriptor(bits.cdata.Struct):
    """Fixed DMA Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) + [
        ('_DMA', ctypes.c_uint16),
        ('_TYPE', ctypes.c_uint16),
        ('_SIZ', ctypes.c_uint8),
    ]
    _dma_transfer_widths = {
        0x00: "8-bit",
        0x01: "16-bit",
        0x02: "32-bit",
        0x03: "64-bit",
        0x04: "128-bit",
        0x05: "256-bit",
    }
    _formats = {
        '_SIZ': unpack.format_table("DMA transfer width={}", _dma_transfer_widths),
    }

def VendorDefinedSmallDescriptor_factory(num_vendor_bytes):
    """Vendor-Defined Descriptor"""
    class VendorDefinedSmallDescriptor(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(small_resource._fields_) + [
            ('vendor_byte_list', ctypes.c_uint8 * num_vendor_bytes),
        ]
    return VendorDefinedSmallDescriptor

def parse_VendorDefinedSmallDescriptor(buf):
    des = VendorDefinedSmallDescriptor_factory(0)
    num_vendor_bytes = len(buf) - ctypes.sizeof(des)
    return VendorDefinedSmallDescriptor_factory(num_vendor_bytes)

class EndTagDescriptor(bits.cdata.Struct):
    """End Tag"""
    _pack_ = 1
    _fields_ = copy.copy(small_resource._fields_) + [
        ('checksum', ctypes.c_uint8),
    ]

class memory_range_information_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('_RW', ctypes.c_uint8, 1),
    ]
    _rw_statuses = {
        1: "writeable (read/write)",
        0: "non-writeable (read-only)",
    }
    _formats = {
        '_RW': unpack.format_table("{}", _rw_statuses),
    }

class memory_range_information(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', memory_range_information_bits),
    ]

class Memory24BitRangeDescriptor(bits.cdata.Struct):
    """Memory 24-Bit Range Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('information', memory_range_information),
        ('_MIN', ctypes.c_uint16),
        ('_MAX', ctypes.c_uint16),
        ('_ALN', ctypes.c_uint16),
        ('_LEN', ctypes.c_uint16),
    ]

def VendorDefinedLargeDescriptor_factory(num_vendor_bytes):
    """Vendor-Defined Descriptor"""
    class VendorDefinedLargeDescriptor(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(large_resource._fields_) + [
            ('length', ctypes.c_uint16),
            ('uuid_sub_type', ctypes.c_uint8),
            ('uuid', bits.cdata.GUID),
            ('vendor_byte_list', ctypes.c_uint8 * num_vendor_bytes),
        ]
    return VendorDefinedLargeDescriptor

def parse_VendorDefinedLargeDescriptor(buf):
    des = VendorDefinedLargeDescriptor_factory(0)
    num_vendor_bytes = len(buf) - ctypes.sizeof(des)
    return VendorDefinedLargeDescriptor_factory(num_vendor_bytes)

class Memory32BitRangeDescriptor(bits.cdata.Struct):
    """32-Bit Memory Range Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('information', memory_range_information),
        ('_MIN', ctypes.c_uint16),
        ('_MAX', ctypes.c_uint16),
        ('_ALN', ctypes.c_uint16),
        ('_LEN', ctypes.c_uint16),
    ]

class FixedMemory32BitRangeDescriptor(bits.cdata.Struct):
    """32-Bit Fixed Memory Range Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('information', memory_range_information),
        ('_BAS', ctypes.c_uint32),
        ('_LEN', ctypes.c_uint32),
    ]

def _range_type_str(range_type):
    if range_type >= 192 and range_type <= 255:
        return 'OEM Defined'
    _range_types = {
        0: 'Memory range',
        1: 'IO range',
        2: 'Bus number range',
    }
    return _range_types.get(range_type, 'Reserved')

_decode_type = {
    1: "bridge subtractively decodes (top level bridges only)",
    0: "bridge positively decodes",
}

_min_address_fixed = {
    1: "specified minimum address is fixed",
    0: "specified minimum address is not fixed and can be changed",
}

_max_address_fixed = {
    1: "specified maximum address is fixed",
    0: "specified maximum address is not fixed",
}

class _resource_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('reserved_0', ctypes.c_uint8, 1),
        ('_DEC', ctypes.c_uint8, 1),
        ('_MIF', ctypes.c_uint8, 1),
        ('_MAF', ctypes.c_uint8, 1),
        ('reserved_7_4', ctypes.c_uint8, 1),
    ]
    _formats = {
        '_DEC': unpack.format_table("{}", _decode_type),
        '_MIF': unpack.format_table("{}", _min_address_fixed),
        '_MAF': unpack.format_table("{}", _max_address_fixed),
    }

class _resource_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', _resource_flags_bits),
    ]

class DwordAddressSpaceDescriptor(bits.cdata.Struct):
    """DWord Address Space Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('range_type', ctypes.c_uint8),
        ('general_flags', _resource_flags),
        ('type_specific_flags', ctypes.c_uint8),
        ('address_space_granularity', ctypes.c_uint32),
        ('address_range_minimum', ctypes.c_uint32),
        ('address_range_maximum', ctypes.c_uint32),
        ('address_translation_offset', ctypes.c_uint32),
        ('address_length', ctypes.c_uint32),
    ]
    _formats = {
        'range_type': unpack.format_function("{:#x}", _range_type_str),
    }

class WordAddressSpaceDescriptor(bits.cdata.Struct):
    """Word Address Space Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('range_type', ctypes.c_uint8),
        ('general_flags', _resource_flags),
        ('type_specific_flags', ctypes.c_uint8),
        ('address_space_granularity', ctypes.c_uint16),
        ('address_range_minimum', ctypes.c_uint16),
        ('address_range_maximum', ctypes.c_uint16),
        ('address_translation_offset', ctypes.c_uint16),
        ('address_length', ctypes.c_uint16),
    ]
    _formats = {
        'range_type': unpack.format_function("{:#x}", _range_type_str),
    }

_consumer_producer = {
    1: "device consumes this resource",
    0: "device produces and consumes this resource",
}

class interrupt_vector_info_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('consumer_producer', ctypes.c_uint8, 1),
        ('_HE', ctypes.c_uint8, 1),
        ('_LL', ctypes.c_uint8, 1),
        ('_SHR', ctypes.c_uint8, 2),
        ('reserved_7_5', ctypes.c_uint8, 3),
    ]

    _formats = {
        'consumer_producer': unpack.format_table("{}", _consumer_producer),
        '_HE': unpack.format_table("{}", _interrupt_modes),
        '_LL': unpack.format_table("{}", _interrupt_polarities),
        '_SHR': unpack.format_table("{}", _interrupt_sharing_wakes),
    }

class interrupt_vector_info(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', interrupt_vector_info_bits),
    ]

def ExtendedInterruptDescriptor_factory(num_interrupts):
    class ExtendedInterruptDescriptor(bits.cdata.Struct):
        """Extended Address Space Descriptor"""
        _pack_ = 1
        _fields_ = copy.copy(large_resource._fields_) + [
            ('length', ctypes.c_uint16),
            ('interrupt_vector_flags', interrupt_vector_info),
            ('interrupt_table_length', ctypes.c_uint8),
            ('interrupt_number', ctypes.c_uint32 * num_interrupts),
        ]
    return ExtendedInterruptDescriptor

def parse_ExtendedInterruptDescriptor(buf):
    res = ExtendedInterruptDescriptor_factory(0).from_buffer_copy(buf)
    return ExtendedInterruptDescriptor_factory(res.interrupt_table_length)

class QwordAddressSpaceDescriptor(bits.cdata.Struct):
    """QWord Address Space Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('range_type', ctypes.c_uint8),
        ('general_flags', _resource_flags),
        ('type_specific_flags', ctypes.c_uint8),
        ('address_space_granularity', ctypes.c_uint64),
        ('address_range_minimum', ctypes.c_uint64),
        ('address_range_maximum', ctypes.c_uint64),
        ('address_translation_offset', ctypes.c_uint64),
        ('address_length', ctypes.c_uint64),
    ]
    _formats = {
        'range_type': unpack.format_function("{:#x}", _range_type_str)
    }

class ExtendedAddressSpaceDescriptor(bits.cdata.Struct):
    """Extended Address Space Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('resource_type', ctypes.c_uint8),
        ('general_flags', _resource_flags),
        ('type_specific_flags', ctypes.c_uint8),
        ('revision_id', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8),
        ('address_range_granularity', ctypes.c_uint64),
        ('address_range_minimum', ctypes.c_uint64),
        ('address_range_maximum', ctypes.c_uint64),
        ('address_translation_offset', ctypes.c_uint64),
        ('address_length', ctypes.c_uint64),
        ('type_specific_attribute', ctypes.c_uint64),
    ]
    _formats = {
        'resource_type': unpack.format_function("{:#x}", _range_type_str)
    }

class AcpiLocalReference(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('ActualType', ctypes.c_uint32),
        ('NamePath', ctypes.c_char_p)
    ]

class _adr_pci(bits.cdata.Struct):
    """_ADR encoding for PCI bus"""
    _pack_ = 1
    _fields_ = [
        ('function', ctypes.c_uint32, 16),
        ('device', ctypes.c_uint32, 16),
    ]

class pci_address(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', _adr_pci),
    ]

class PciRoutingTablePIC(bits.cdata.Struct):
    """PCI Routing Table Entry using PIC mode"""
    _pack_ = 1
    _fields_ = [
        ('address', pci_address),
        ('pin', ctypes.c_uint8),
        ('source', ctypes.c_uint8),
        ('source_index', ctypes.c_uint32),
    ]

class PciRoutingTablePICgsi(bits.cdata.Struct):
    """PCI Routing Table Entry using PIC mode and specifying a Global System Interrupt (GSI)"""
    _pack_ = 1
    _fields_ = [
        ('address', pci_address),
        ('pin', ctypes.c_uint8),
        ('source', ctypes.c_uint8),
        ('global_system_interrupt', ctypes.c_uint32),
    ]

class PciRoutingTableAPIC(bits.cdata.Struct):
    """PCI Routing Table Entry using APIC mode"""
    _pack_ = 1
    _fields_ = [
        ('address', pci_address),
        ('pin', ctypes.c_uint8),
        ('source', AcpiLocalReference),
        ('source_index', ctypes.c_uint32),
    ]

def parse_prt(pkg):
    """Parse PCI Routing Table (PRT) Entries"""
    if isinstance(pkg, tuple):
        if len(pkg) == 4:
            if isinstance(pkg[2], AcpiLocalReference):
                return PciRoutingTableAPIC(pci_address(pkg[0]), *pkg[1:])
            if issubclass(type(pkg[2]), (int, long)):
                if pkg[2] == 0:
                    return PciRoutingTablePICgsi(pci_address(pkg[0]), *pkg[1:])
                else:
                    return PciRoutingTablePIC(pci_address(pkg[0]), *pkg[1:])
    return pkg

def make_prt(data):
    if data is None:
        return None
    data = parse_prt(data)
    if isinstance(data, tuple):
        return tuple(make_prt(v) for v in data)
    return data

def display_prt(name="_PRT"):
    with ttypager.page():
        for path in get_objpaths(name):
            print path
            for prt in make_prt(evaluate(path)):
                print prt
            print

class AcpiPower(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('SystemLevel', ctypes.c_uint32),
        ('ResourceOrder', ctypes.c_uint32)
    ]

class AcpiProcessor(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('ProcId', ctypes.c_uint32),
        ('PblkAddress', ctypes.c_uint64),
        ('PblkLength', ctypes.c_uint32),
    ]

# ACPI_OBJECT_TYPE values
assert _acpi.ACPI_TYPE_EXTERNAL_MAX == 16, "Internal error: ACPI_OBJECT_TYPE enumeration not updated for new ACPICA"
(
    ACPI_TYPE_ANY,
    ACPI_TYPE_INTEGER,
    ACPI_TYPE_STRING,
    ACPI_TYPE_BUFFER,
    ACPI_TYPE_PACKAGE,
    ACPI_TYPE_FIELD_UNIT,
    ACPI_TYPE_DEVICE,
    ACPI_TYPE_EVENT,
    ACPI_TYPE_METHOD,
    ACPI_TYPE_MUTEX,
    ACPI_TYPE_REGION,
    ACPI_TYPE_POWER,
    ACPI_TYPE_PROCESSOR,
    ACPI_TYPE_THERMAL,
    ACPI_TYPE_BUFFER_FIELD,
    ACPI_TYPE_DDB_HANDLE,
    ACPI_TYPE_DEBUG_OBJECT,
) = range(_acpi.ACPI_TYPE_EXTERNAL_MAX + 1)

ACPI_TYPE_LOCAL_REFERENCE = 0x14

_acpi_object_types = {
    ACPI_TYPE_INTEGER: _id,
    ACPI_TYPE_STRING: _id,
    ACPI_TYPE_BUFFER: AcpiBuffer,
    ACPI_TYPE_PACKAGE: (lambda t: tuple(_acpi_object_to_python(v) for v in t)),
    ACPI_TYPE_POWER: (lambda args: AcpiPower(*args)),
    ACPI_TYPE_PROCESSOR: (lambda args: AcpiProcessor(*args)),
    ACPI_TYPE_LOCAL_REFERENCE: (lambda args: AcpiLocalReference(*args)),
}

def _acpi_object_to_python(acpi_object):
    if acpi_object is None:
        return None
    object_type, value = acpi_object
    return _acpi_object_types[object_type](value)

def ctypes_to_python(data):
    if data is None:
        return None
    if isinstance(data, (list, tuple)):
        return tuple(ctypes_to_python(v) for v in data)
    if issubclass(type(data), (bits.cdata.Struct, bits.cdata.Union)):
        return tuple(ctypes_to_python(getattr(data, f[0])) for f in data._fields_)
    return data

def make_resources(data):
    if data is None:
        return None
    if isinstance(data, tuple):
        return tuple(make_resources(v) for v in data)
    if isinstance(data, AcpiBuffer):
        return parse_descriptor(data)
    return data

def _acpi_object_from_python(obj):
    if isinstance(obj, (int, long)):
        return (ACPI_TYPE_INTEGER, obj)
    # Must check AcpiBuffer before str, since AcpiBuffer derives from str
    if isinstance(obj, AcpiBuffer):
        return (ACPI_TYPE_BUFFER, obj)
    if isinstance(obj, str):
        return (ACPI_TYPE_STRING, obj)
    if isinstance(obj, AcpiPower):
        return (ACPI_TYPE_POWER, obj)
    if isinstance(obj, AcpiProcessor):
        return (ACPI_TYPE_PROCESSOR, obj)
    # Must check tuple after any namedtuples, since namedtuples derive from tuple
    if isinstance(obj, tuple):
        return (ACPI_TYPE_PACKAGE, tuple(_acpi_object_from_python(arg) for arg in obj))

def evaluate(pathname, *args, **kwargs):
    """Evaluate an ACPI method and return the result.

    By default, ACPI method evaluation allows reads and writes of I/O ports.
    Pass the keyword argument unsafe_io=False to silently ignore I/O
    operations."""
    global acpi_unsafe_io
    unsafe_io = kwargs.get("unsafe_io")
    if unsafe_io is not None:
        old_unsafe_io = acpi_unsafe_io
        acpi_unsafe_io = unsafe_io
    try:
        return _acpi_object_to_python(_acpi._eval(pathname, tuple(_acpi_object_from_python(arg) for arg in args)))
    finally:
        if unsafe_io is not None:
            acpi_unsafe_io = old_unsafe_io

acpi_object_types = {
    ACPI_TYPE_INTEGER: 'ACPI_TYPE_INTEGER',
    ACPI_TYPE_STRING: 'ACPI_TYPE_STRING',
    ACPI_TYPE_BUFFER: 'ACPI_TYPE_BUFFER',
    ACPI_TYPE_PACKAGE: 'ACPI_TYPE_PACKAGE',
    ACPI_TYPE_FIELD_UNIT: 'ACPI_TYPE_FIELD_UNIT',
    ACPI_TYPE_DEVICE: 'ACPI_TYPE_DEVICE',
    ACPI_TYPE_EVENT: 'ACPI_TYPE_EVENT',
    ACPI_TYPE_METHOD: 'ACPI_TYPE_METHOD',
    ACPI_TYPE_MUTEX: 'ACPI_TYPE_MUTEX',
    ACPI_TYPE_REGION: 'ACPI_TYPE_REGION',
    ACPI_TYPE_POWER: 'ACPI_TYPE_POWER',
    ACPI_TYPE_PROCESSOR: 'ACPI_TYPE_PROCESSOR',
    ACPI_TYPE_THERMAL: 'ACPI_TYPE_THERMAL',
    ACPI_TYPE_BUFFER_FIELD: 'ACPI_TYPE_BUFFER_FIELD',
    ACPI_TYPE_DDB_HANDLE: 'ACPI_TYPE_DDB_HANDLE',
    ACPI_TYPE_DEBUG_OBJECT: 'ACPI_TYPE_DEBUG_OBJECT',
    ACPI_TYPE_LOCAL_REFERENCE: 'ACPI_TYPE_LOCAL_REFERENCE',
}

def ObjectInfo_factory(ids_length):
    class object_info_flags_bits(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('current_status_valid', ctypes.c_uint8, 1),
            ('address_valid', ctypes.c_uint8, 1),
            ('hardware_id_valid', ctypes.c_uint8, 1),
            ('unique_id_valid', ctypes.c_uint8, 1),
            ('subsystem_id_valid', ctypes.c_uint8, 1),
            ('compatibility_id_valid', ctypes.c_uint8, 1),
            ('highest_dstates_valid', ctypes.c_uint8, 1),
            ('lowest_dstates_valid', ctypes.c_uint8, 1),
        ]
    class object_info_flags(bits.cdata.Union):
        _pack_ = 1
        _anonymous_ = ("bits",)
        _fields_ = [
            ('data', ctypes.c_uint8),
            ('bits', object_info_flags_bits),
        ]
    class current_status_flags_bits(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('present', ctypes.c_uint32, 1),
            ('enabled', ctypes.c_uint32, 1),
            ('visible', ctypes.c_uint32, 1),
            ('functional', ctypes.c_uint32, 1),
            ('battery_present', ctypes.c_uint32, 1),
        ]
    class current_status_flags(bits.cdata.Union):
        _pack_ = 1
        _anonymous_ = ("bits",)
        _fields_ = [
            ('data', ctypes.c_uint32),
            ('bits', current_status_flags_bits),
        ]
    class ObjectInfo_factory(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('info_size', ctypes.c_uint32),
            ('name', ctypes.c_char * 4),
            ('object_type', ctypes.c_uint32),
            ('parameter_count', ctypes.c_uint8),
            ('valid', ctypes.c_uint8),
            ('flags', object_info_flags),
            ('highest_dstates', ctypes.c_uint8 * 4),
            ('lowest_dstates', ctypes.c_uint8 * 5),
            ('current_status', current_status_flags),
            ('address', ctypes.c_uint64),
            ('hardware_id', get_string())
            ('unique_id', get_string())
            ('subsystem_id', get_string())
            ('compatibility_id_count', ctypes.c_uint32),
            ('compatibility_id_length', ctypes.c_uint32),
            ('ids', ctypes.c_uint8 * ids_length),
        ]
        _formats = {
            'object_type': unpack.format_table("{}", acpi_object_types),
        }
    def get_string():
        length, offset = u.unpack("IP")
        if not length:
            return None
        return s.unpack_peek_one("{}x{}s".format(offset - addr, length)).split("\x00", 1)[0]

class ObjectInfo(unpack.Struct):
    def __init__(self, data, addr):
        super(ObjectInfo, self).__init__()
        u = unpack.Unpackable(data)
        s = unpack.Unpackable(data)
        self.add_field('info_size', u.unpack_one("<I"))
        self.add_field('name', u.unpack_one("4s"))
        self.add_field('object_type', u.unpack_one("<I"), unpack.format_table("{}", acpi_object_types))
        self.add_field('parameter_count', u.unpack_one("B"))
        self.add_field('valid', u.unpack_one("B"))
        self.add_field('current_status_valid', bool(bitfields.getbits(self.valid, 0)), "valid[0]={}")
        self.add_field('address_valid', bool(bitfields.getbits(self.valid, 1)), "valid[1]={}")
        self.add_field('hardware_id_valid', bool(bitfields.getbits(self.valid, 2)), "valid[2]={}")
        self.add_field('unique_id_valid', bool(bitfields.getbits(self.valid, 3)), "valid[3]={}")
        self.add_field('subsystem_id_valid', bool(bitfields.getbits(self.valid, 4)), "valid[4]={}")
        self.add_field('compatibility_id_valid', bool(bitfields.getbits(self.valid, 5)), "valid[5]={}")
        self.add_field('highest_dstates_valid', bool(bitfields.getbits(self.valid, 6)), "valid[6]={}")
        self.add_field('lowest_dstates_valid', bool(bitfields.getbits(self.valid, 7)), "valid[7]={}")

        self.add_field('flags', u.unpack_one("B"))
        self.add_field('highest_dstates', tuple(u.unpack_one("B") for i in range(4)))
        self.add_field('lowest_dstates', tuple(u.unpack_one("B") for i in range(5)))
        self.add_field('current_status', u.unpack_one("<I"))

        if self.current_status_valid:
            self.add_field('present', bool(bitfields.getbits(self.current_status, 0)), "current_status[0]={}")
            self.add_field('enabled', bool(bitfields.getbits(self.current_status, 1)), "current_status[1]={}")
            self.add_field('visible', bool(bitfields.getbits(self.current_status, 2)), "current_status[2]={}")
            self.add_field('functional', bool(bitfields.getbits(self.current_status, 3)), "current_status[3]={}")
            self.add_field('battery_present', bool(bitfields.getbits(self.current_status, 4)), "current_status[4]={}")

        # Deal with padding before the 8-byte address field
        ptralign = struct.calcsize("I0P")
        if u.offset % ptralign != 0:
            u.skip(ptralign - (u.offset % ptralign))
        self.add_field('address', u.unpack_one("<Q"))

        def get_string():
            length, offset = u.unpack("IP")
            if not length:
                return None
            return s.unpack_peek_one("{}x{}s".format(offset - addr, length)).split("\x00", 1)[0]

        self.add_field('hardware_id', get_string())
        self.add_field('unique_id', get_string())
        self.add_field('subsystem_id', get_string())
        self.add_field('compatibility_id_count', u.unpack_one("<I"))
        self.add_field('compatibility_id_length', u.unpack_one("<I"))
        self.add_field('compatibility_ids', tuple(get_string() for i in range(self.compatibility_id_count)))

def scope(path):
    try:
        prefix, _ = path.rsplit('.', 1)
        return prefix
    except ValueError:
        return "/"

def parse_table(signature, instance=1):
    addr = get_table_addr(signature, instance)
    if addr is None:
        return None
    signature = string.rstrip(signature,"!")
    return globals()[signature](addr)

def make_compat_parser(signature):
    def parse(printflag=False, instance=1):
        table = parse_table(signature, instance)
        if table is None:
            return None
        if printflag:
            with ttypager.page():
                print table
        return table
    return parse

class RSDP_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 8),
        ('checksum', ctypes.c_uint8),
        ('oemid', ctypes.c_char * 6),
        ('revision', ctypes.c_uint8),
        ('rsdt_address', ctypes.c_uint32),
    ]

class RSDP_v2(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(RSDP_v1._fields_) + [
        ('length', ctypes.c_uint32),
        ('xsdt_address', ctypes.c_uint64),
        ('extended_checksum', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8 * 3),
    ]

def RSDP(val):
    """Create class based on decode of an RSDP table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    r = RSDP_v1.from_address(addr)
    cls = RSDP_v1
    if r.revision == 2:
        cls = RSDP_v2
    if isinstance(val, str):
        return cls.from_buffer_copy(data)
    return cls.from_address(addr)

parse_rsdp = make_compat_parser("RSDP")

class TableHeader(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 4),
        ('length', ctypes.c_uint32),
        ('revision', ctypes.c_ubyte),
        ('checksum', ctypes.c_ubyte),
        ('oemid', ctypes.c_char * 6),
        ('oemtableid', ctypes.c_char * 8),
        ('oemrevision', ctypes.c_uint32),
        ('creatorid', ctypes.c_char * 4),
        ('creatorrevision', ctypes.c_uint32),
    ]

def format_table_addrs(addrs):
    return "(\n{})".format(",\n".join("{:#x} ({})".format(addr, (ctypes.c_char * 4).from_address(addr).raw) for addr in addrs))

def rsdt_factory(num_tables, no_formats=False):
    formats = { 'tables': format_table_addrs, }
    if no_formats:
        formats = dict()
    class RSDT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('tables', ctypes.c_uint32 * num_tables),
        ]
        _formats = formats
    return RSDT_v1

def RSDT(val):
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_tables = (hdr.length - ctypes.sizeof(TableHeader)) / ctypes.sizeof(ctypes.c_uint32)
    if isinstance(val, str):
        return rsdt_factory(num_tables, no_formats=True).from_buffer_copy(data)
    return rsdt_factory(num_tables).from_address(addr)

parse_rsdt = make_compat_parser("RSDT")

def xsdt_factory(num_tables, no_formats=False):
    formats = { 'tables': format_table_addrs, }
    if no_formats:
        formats = dict()
    class XSDT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('tables', ctypes.c_uint64 * num_tables),
        ]
        _formats = formats
    return XSDT_v1

def XSDT(val):
    """Create class based on decode of an XSDT table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_tables = (hdr.length - ctypes.sizeof(TableHeader)) / ctypes.sizeof(ctypes.c_uint64)
    if isinstance(val, str):
        return xsdt_factory(num_tables, no_formats=True).from_buffer_copy(data)
    return xsdt_factory(num_tables).from_address(addr)

parse_xsdt = make_compat_parser("XSDT")

class DMARSubtable(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('subtype', ctypes.c_uint16),
        ('length', ctypes.c_uint16),
    ]

class DMARDeviceScopePath(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pci_device', ctypes.c_uint8),
        ('pci_function', ctypes.c_uint8),
    ]

def DMARDeviceScope_factory(num_dev_scope_path):
    class DMARDeviceScope(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('type', ctypes.c_uint8),
            ('length', ctypes.c_uint8),
            ('reserved', ctypes.c_uint16),
            ('enumeration_id', ctypes.c_uint8),
            ('start_bus_number', ctypes.c_uint8),
            ('paths', DMARDeviceScopePath * num_dev_scope_path),
        ]
    return DMARDeviceScope

def dmar_device_scope_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    base_len_DMARDeviceScope = ctypes.sizeof(DMARDeviceScope_factory(0))
    len_DMARDeviceScopePath = ctypes.sizeof(DMARDeviceScopePath)
    while addr < end:
        subtable_num += 1
        subtable = DMARDeviceScope_factory(0).from_address(addr)
        num_dev_scope_path = (subtable.length - base_len_DMARDeviceScope) / len_DMARDeviceScopePath
        cls = DMARDeviceScope_factory(num_dev_scope_path)
        addr += subtable.length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

class drhd_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('include_pci_all', ctypes.c_uint8, 1),
    ]

class drhd_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', drhd_flags_bits),
    ]

def DMARSubtableDRHD_factory(field_list):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class DMARSubtableDRHD(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(DMARSubtable._fields_) + [
            ('flags', drhd_flags),
            ('reserved', ctypes.c_uint8),
            ('segment_number', ctypes.c_uint16),
            ('base_address', ctypes.c_uint64),
            ('device_scopes', subtables)
        ]
    return DMARSubtableDRHD

def DMARSubtableRMRR_factory(field_list):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class DMARSubtableRMRR(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(DMARSubtable._fields_) + [
            ('reserved', ctypes.c_uint16),
            ('segment_number', ctypes.c_uint16),
            ('base_address', ctypes.c_uint64),
            ('limit_address', ctypes.c_uint64),
            ('device_scopes', subtables),
        ]

    return DMARSubtableRMRR

class atsr_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('all_ports', ctypes.c_uint8, 1),
    ]

class atsr_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', atsr_flags_bits),
    ]

def DMARSubtableATSR_factory(field_list):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class DMARSubtableATSR(bits.cdata.Struct):
        _pack = 1
        _fields_ = copy.copy(DMARSubtable._fields_) + [
            ('flags', atsr_flags),
            ('reserved', ctypes.c_uint8),
            ('segment_number', ctypes.c_uint16),
            ('device_scopes', subtables),
        ]
    return DMARSubtableATSR

class DMARSubtableRHSA(bits.cdata.Struct):
    _pack = 1
    _fields_ = copy.copy(DMARSubtable._fields_) + [
        ('reserved', ctypes.c_uint32),
        ('base_address', ctypes.c_uint64),
        ('proximity_domain', ctypes.c_uint32),
    ]

def DMARSubTableANDD_factory(obj_name_len):
    class DMARSubTableANDD(bits.cdata.Struct):
        _pack = 1
        _fields_ = copy.copy(DMARSubtable._fields_) + [
            ('reserved', ctypes.c_uint8 * 3),
            ('device_num', ctypes.c_uint8),
            ('object_name', ctypes.c_char * obj_name_len),
        ]
    return DMARSubTableANDD

def DMARSubtableUnknown_factory(data_len):
    class DMARSubtableUnknown(bits.cdata.Struct):
        _pack = 1
        _fields_ = copy.copy(DMARSubtable._fields_) + [
            ('data', ctypes.c_uint8 * data_len),
        ]
    return DMARSubtableUnknown

ACPI_DMAR_TYPE_DRHD = 0
ACPI_DMAR_TYPE_RMRR = 1
ACPI_DMAR_TYPE_ATSR = 2
ACPI_DMAR_TYPE_RHSA = 3
ACPI_DMAR_TYPE_ANDD = 4

def dmar_subtable_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    base_len_DRHD = ctypes.sizeof(DMARSubtableDRHD_factory(list()))
    base_len_RMRR = ctypes.sizeof(DMARSubtableRMRR_factory(list()))
    base_len_ATSR = ctypes.sizeof(DMARSubtableATSR_factory(list()))
    base_len_ANDD = ctypes.sizeof(DMARSubTableANDD_factory(0))
    while addr < end:
        subtable_num += 1
        subtable = DMARSubtable.from_address(addr)
        if subtable.subtype == ACPI_DMAR_TYPE_DRHD:
            next_field_list = dmar_device_scope_list(addr + base_len_DRHD, subtable.length - base_len_DRHD)
            cls = DMARSubtableDRHD_factory(next_field_list)
        elif subtable.subtype == ACPI_DMAR_TYPE_RMRR:
            next_field_list = dmar_device_scope_list(addr + base_len_RMRR, subtable.length - base_len_RMRR)
            cls = DMARSubtableRMRR_factory(next_field_list)
        elif subtable.subtype == ACPI_DMAR_TYPE_ATSR:
            next_field_list = dmar_device_scope_list(addr + base_len_ATSR, subtable.length - base_len_ATSR)
            cls = DMARSubtableATSR_factory(next_field_list)
        elif subtable.subtype == ACPI_DMAR_TYPE_RHSA:
            cls = DMARSubtableRHSA
        elif subtable.subtype == ACPI_DMAR_TYPE_ANDD:
            cls = DMARSubTableANDD_factory(subtable.length - base_len_ANDD)
        else:
            cls = DMARSubtableUnknown_factory(subtable.length - ctypes.sizeof(DMARSubtable))
        addr += subtable.length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

class dmar_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('intr_remap', ctypes.c_uint8, 1),
        ('x2apic_opt_out', ctypes.c_uint8, 1),
    ]

class dmar_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', dmar_flags_bits),
    ]

def dmar_factory(field_list):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class DMAR_v1(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('header', TableHeader),
            ('host_addr_width', ctypes.c_uint8),
            ('flags', ctypes.c_uint8),
            ('reserved', ctypes.c_uint8 * 10),
            ('remapping_structures', subtables),
        ]

    return DMAR_v1

def DMAR(val):
    """Create class based on decode of an DMAR table from address or filename."""
    base_length = ctypes.sizeof(dmar_factory(list()))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    field_list = dmar_subtable_list(addr + base_length, hdr.length - base_length)
    if isinstance(val, str):
        return dmar_factory(field_list).from_buffer_copy(data)
    return dmar_factory(field_list).from_address(addr)

parse_dmar = make_compat_parser("DMAR")

class FixedFuncHwReg(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('Type', ctypes.c_uint8),
        ('VendorCode', ctypes.c_uint8),
        ('ClassCode', ctypes.c_uint8),
        ('Arg1', ctypes.c_uint8),
        ('Arg0', ctypes.c_uint64),
    ]

class GenericRegisterDescriptor(bits.cdata.Struct):
    """Generic Register Descriptor"""
    _pack_ = 1
    _fields_ = copy.copy(large_resource._fields_) + [
        ('length', ctypes.c_uint16),
        ('AddressSpaceId', ctypes.c_uint8),
        ('BitWidth', ctypes.c_uint8),
        ('BitOffset', ctypes.c_uint8),
        ('AccessSize', ctypes.c_uint8),
        ('Address', ctypes.c_uint64),
    ]

    @property
    def FFH(self):
        if self.AddressSpaceId == ASID_FFH:
            a = getattr(self.__class__, 'AddressSpaceId')
            return FixedFuncHwReg.from_buffer(self, a.offset)
        return None

def make_SingleRegisters(data):
    if data is None:
        return None
    if isinstance(data, tuple):
        if len(data) == 2:
            if isinstance(data[0], GenericRegisterDescriptor):
                if isinstance(data[1], EndTagDescriptor):
                    return SingleRegister(*data)
        return tuple(make_SingleRegisters(v) for v in data)
    return data

class SingleRegister(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('GenericRegister', GenericRegisterDescriptor),
        ('EndTag', EndTagDescriptor),
    ]

_preferred_pm_profile = {
    0: 'Unspecified',
    1: 'Desktop',
    2: 'Mobile',
    3: 'Workstation',
    4: 'Enterprise Server',
    5: 'SOHO Server',
    6: 'Appliance PC',
    7: 'Performance Server',
    8: 'Tablet'
}

ASID_SYSTEM_MEMORY = 0
ASID_SYSTEM_IO = 1
ASID_PCI_CFG_SPACE = 2
ASID_EMBEDDED_CONTROLLER = 3
ASID_SMBUS = 4
ASID_PCC = 0xA
ASID_FFH = 0x7F

def _asid_str(asid):
    if asid >= 0xC0 and asid <= 0xff:
        return 'OEM Defined'
    _asid = {
        ASID_SYSTEM_MEMORY: 'System Memory',
        ASID_SYSTEM_IO: 'System IO',
        ASID_PCI_CFG_SPACE: 'PCI Configuration Space',
        ASID_EMBEDDED_CONTROLLER: 'Embedded Controller',
        ASID_SMBUS: 'SMBus',
        ASID_PCC: 'Platform Communications Channel (PCC)',
        ASID_FFH: 'Functional Fixed Hardware',
        }
    return _asid.get(asid, 'Reserved')

_access_sizes = {
    0: 'Undefined',
    1: 'Byte access',
    2: 'Word access',
    3: 'Dword access',
    4: 'Qword access',
}

class GAS(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('address_space_id', ctypes.c_uint8),
        ('register_bit_width', ctypes.c_uint8),
        ('register_bit_offset', ctypes.c_uint8),
        ('access_size', ctypes.c_uint8),
        ('address', ctypes.c_uint64),
    ]

    _formats = {
        'address_space_id' : unpack.format_function("{:#x}", _asid_str),
        'access_size'      : unpack.format_table("{}", _access_sizes),
    }

class facp_flags_bits_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('wbinvd', ctypes.c_uint32, 1),
        ('wbinvd_flush', ctypes.c_uint32, 1),
        ('proc_c1', ctypes.c_uint32, 1),
        ('p_lvl2_up', ctypes.c_uint32, 1),
        ('pwr_button', ctypes.c_uint32, 1),
        ('slp_button', ctypes.c_uint32, 1),
        ('fix_rtc', ctypes.c_uint32, 1),
        ('rtc_s4', ctypes.c_uint32, 1),
        ('tmr_val_ext', ctypes.c_uint32, 1),
        ('dck_cap', ctypes.c_uint32, 1),
    ]

class facp_flags_v1(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facp_flags_bits_v1),
    ]

class FACP_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('firmware_ctrl', ctypes.c_uint32),
        ('dsdt', ctypes.c_uint32),
        ('int_model', ctypes.c_uint8),
        ('reserved0', ctypes.c_uint8),
        ('sci_int', ctypes.c_uint16),
        ('smi_cmd', ctypes.c_uint32),
        ('acpi_enable', ctypes.c_uint8),
        ('acpi_disable', ctypes.c_uint8),
        ('s4bios_req', ctypes.c_uint8),
        ('reserved1', ctypes.c_uint8),
        ('pm1a_evt_blk', ctypes.c_uint32),
        ('pm1b_evt_blk', ctypes.c_uint32),
        ('pm1a_cnt_blk', ctypes.c_uint32),
        ('pm1b_cnt_blk', ctypes.c_uint32),
        ('pm2_cnt_blk', ctypes.c_uint32),
        ('pm_tmr_blk', ctypes.c_uint32),
        ('gpe0_blk', ctypes.c_uint32),
        ('gpe1_blk', ctypes.c_uint32),
        ('pm1_evt_len', ctypes.c_uint8),
        ('pm1_cnt_len', ctypes.c_uint8),
        ('pm2_cnt_len', ctypes.c_uint8),
        ('pm_tmr_len', ctypes.c_uint8),
        ('gpe0_blk_len', ctypes.c_uint8),
        ('gpe1_blk_len', ctypes.c_uint8),
        ('gpe1_base', ctypes.c_uint8),
        ('reserved2', ctypes.c_uint8),
        ('p_lvl2_lat', ctypes.c_uint16),
        ('p_lvl3_lat', ctypes.c_uint16),
        ('flush_size', ctypes.c_uint16),
        ('flush_stride', ctypes.c_uint16),
        ('duty_offset', ctypes.c_uint8),
        ('duty_width', ctypes.c_uint8),
        ('day_alrm', ctypes.c_uint8),
        ('mon_alrm', ctypes.c_uint8),
        ('century', ctypes.c_uint8),
        ('reserved3', ctypes.c_uint8 * 3),
        ('flags', facp_flags_v1),
    ]

class facp_flags_bits_v3(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(facp_flags_bits_v1._fields_) + [
        ('reset_reg_sup', ctypes.c_uint32, 1),
        ('sealed_case', ctypes.c_uint32, 1),
        ('headless', ctypes.c_uint32, 1),
        ('cpu_sw_slp', ctypes.c_uint32, 1),
        ('pci_exp_wak', ctypes.c_uint32, 1),
        ('use_platform_clock', ctypes.c_uint32, 1),
        ('s4_rtc_sts_valid', ctypes.c_uint32, 1),
        ('remote_power_on_capable', ctypes.c_uint32, 1),
        ('force_apic_cluster_mode', ctypes.c_uint32, 1),
        ('force_apic_physical_destination_mode', ctypes.c_uint32, 1),
    ]

class facp_flags_v3(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facp_flags_bits_v3),
    ]

class facp_iapc_arch_bits_v3(bits.cdata.Struct):
    _pack_ = 1
    _fields_ =  [
        ('legacy_devices', ctypes.c_uint16, 1),
        ('8042', ctypes.c_uint16, 1),
        ('vga_not_present', ctypes.c_uint16, 1),
        ('msi_not_supported', ctypes.c_uint16, 1),
    ]

class facp_iapc_arch_v3(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', facp_iapc_arch_bits_v3),
    ]

class FACP_v3(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('firmware_ctrl', ctypes.c_uint32),
        ('dsdt', ctypes.c_uint32),
        ('reserved0', ctypes.c_uint8),
        ('preferred_pm_profile', ctypes.c_uint8),
        ('sci_int', ctypes.c_uint16),
        ('smi_cmd', ctypes.c_uint32),
        ('acpi_enable', ctypes.c_uint8),
        ('acpi_disable', ctypes.c_uint8),
        ('s4bios_req', ctypes.c_uint8),
        ('pstate_cnt', ctypes.c_uint8),
        ('pm1a_evt_blk', ctypes.c_uint32),
        ('pm1b_evt_blk', ctypes.c_uint32),
        ('pm1a_cnt_blk', ctypes.c_uint32),
        ('pm1b_cnt_blk', ctypes.c_uint32),
        ('pm2_cnt_blk', ctypes.c_uint32),
        ('pm_tmr_blk', ctypes.c_uint32),
        ('gpe0_blk', ctypes.c_uint32),
        ('gpe1_blk', ctypes.c_uint32),
        ('pm1_evt_len', ctypes.c_uint8),
        ('pm1_cnt_len', ctypes.c_uint8),
        ('pm2_cnt_len', ctypes.c_uint8),
        ('pm_tmr_len', ctypes.c_uint8),
        ('gpe0_blk_len', ctypes.c_uint8),
        ('gpe1_blk_len', ctypes.c_uint8),
        ('gpe1_base', ctypes.c_uint8),
        ('cst_cnt', ctypes.c_uint8),
        ('p_lvl2_lat', ctypes.c_uint16),
        ('p_lvl3_lat', ctypes.c_uint16),
        ('flush_size', ctypes.c_uint16),
        ('flush_stride', ctypes.c_uint16),
        ('duty_offset', ctypes.c_uint8),
        ('duty_width', ctypes.c_uint8),
        ('day_alrm', ctypes.c_uint8),
        ('mon_alrm', ctypes.c_uint8),
        ('century', ctypes.c_uint8),
        ('iapc_boot_arch', facp_iapc_arch_v3),
        ('reserved1', ctypes.c_uint8),
        ('flags', facp_flags_v3),
        ('reset_reg', GAS),
        ('reset_value', ctypes.c_uint8),
        ('reserved2', ctypes.c_uint8 * 3),
        ('x_firmware_ctrl', ctypes.c_uint64),
        ('x_dsdt', ctypes.c_uint64),
        ('x_pm1a_evt_blk', GAS),
        ('x_pm1b_evt_blk', GAS),
        ('x_pm1a_cnt_blk', GAS),
        ('x_pm1b_cnt_blk', GAS),
        ('x_pm2_cnt_blk', GAS),
        ('x_pm_tmr_blk', GAS),
        ('x_gpe0_blk', GAS),
        ('x_gpe1_blk', GAS),
    ]

    _formats = {
        'preferred_pm_profile': unpack.format_table("{}", _preferred_pm_profile),
    }

class facp_iapc_arch_bits_v4(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(facp_iapc_arch_bits_v3._fields_) + [
        ('pcie_aspm_controls', ctypes.c_uint16, 1),
    ]

class facp_iapc_arch_v4(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', facp_iapc_arch_bits_v4),
    ]

class FACP_v4(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('firmware_ctrl', ctypes.c_uint32),
        ('dsdt', ctypes.c_uint32),
        ('reserved0', ctypes.c_uint8),
        ('preferred_pm_profile', ctypes.c_uint8),
        ('sci_int', ctypes.c_uint16),
        ('smi_cmd', ctypes.c_uint32),
        ('acpi_enable', ctypes.c_uint8),
        ('acpi_disable', ctypes.c_uint8),
        ('s4bios_req', ctypes.c_uint8),
        ('pstate_cnt', ctypes.c_uint8),
        ('pm1a_evt_blk', ctypes.c_uint32),
        ('pm1b_evt_blk', ctypes.c_uint32),
        ('pm1a_cnt_blk', ctypes.c_uint32),
        ('pm1b_cnt_blk', ctypes.c_uint32),
        ('pm2_cnt_blk', ctypes.c_uint32),
        ('pm_tmr_blk', ctypes.c_uint32),
        ('gpe0_blk', ctypes.c_uint32),
        ('gpe1_blk', ctypes.c_uint32),
        ('pm1_evt_len', ctypes.c_uint8),
        ('pm1_cnt_len', ctypes.c_uint8),
        ('pm2_cnt_len', ctypes.c_uint8),
        ('pm_tmr_len', ctypes.c_uint8),
        ('gpe0_blk_len', ctypes.c_uint8),
        ('gpe1_blk_len', ctypes.c_uint8),
        ('gpe1_base', ctypes.c_uint8),
        ('cst_cnt', ctypes.c_uint8),
        ('p_lvl2_lat', ctypes.c_uint16),
        ('p_lvl3_lat', ctypes.c_uint16),
        ('flush_size', ctypes.c_uint16),
        ('flush_stride', ctypes.c_uint16),
        ('duty_offset', ctypes.c_uint8),
        ('duty_width', ctypes.c_uint8),
        ('day_alrm', ctypes.c_uint8),
        ('mon_alrm', ctypes.c_uint8),
        ('century', ctypes.c_uint8),
        ('iapc_boot_arch', facp_iapc_arch_v4),
        ('reserved1', ctypes.c_uint8),
        ('flags', facp_flags_v3),
        ('reset_reg', GAS),
        ('reset_value', ctypes.c_uint8),
        ('reserved2', ctypes.c_uint8 * 3),
        ('x_firmware_ctrl', ctypes.c_uint64),
        ('x_dsdt', ctypes.c_uint64),
        ('x_pm1a_evt_blk', GAS),
        ('x_pm1b_evt_blk', GAS),
        ('x_pm1a_cnt_blk', GAS),
        ('x_pm1b_cnt_blk', GAS),
        ('x_pm2_cnt_blk', GAS),
        ('x_pm_tmr_blk', GAS),
        ('x_gpe0_blk', GAS),
        ('x_gpe1_blk', GAS),
    ]

    _formats = {
        'preferred_pm_profile': unpack.format_table("{}", _preferred_pm_profile),
    }

class facp_flags_bits_v5(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(facp_flags_bits_v3._fields_) + [
        ('hw_reduced_acpi', ctypes.c_uint32, 1),
        ('low_power_s0_idle_capable', ctypes.c_uint32, 1),
    ]

class facp_flags_v5(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facp_flags_bits_v5),
    ]

class facp_iapc_arch_bits_v5(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(facp_iapc_arch_bits_v4._fields_) + [
        ('cmos_rtc_not_present', ctypes.c_uint16, 1),
    ]

class facp_iapc_arch_v5(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', facp_iapc_arch_bits_v5),
    ]

class FACP_v5(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('firmware_ctrl', ctypes.c_uint32),
        ('dsdt', ctypes.c_uint32),
        ('reserved0', ctypes.c_uint8),
        ('preferred_pm_profile', ctypes.c_uint8),
        ('sci_int', ctypes.c_uint16),
        ('smi_cmd', ctypes.c_uint32),
        ('acpi_enable', ctypes.c_uint8),
        ('acpi_disable', ctypes.c_uint8),
        ('s4bios_req', ctypes.c_uint8),
        ('pstate_cnt', ctypes.c_uint8),
        ('pm1a_evt_blk', ctypes.c_uint32),
        ('pm1b_evt_blk', ctypes.c_uint32),
        ('pm1a_cnt_blk', ctypes.c_uint32),
        ('pm1b_cnt_blk', ctypes.c_uint32),
        ('pm2_cnt_blk', ctypes.c_uint32),
        ('pm_tmr_blk', ctypes.c_uint32),
        ('gpe0_blk', ctypes.c_uint32),
        ('gpe1_blk', ctypes.c_uint32),
        ('pm1_evt_len', ctypes.c_uint8),
        ('pm1_cnt_len', ctypes.c_uint8),
        ('pm2_cnt_len', ctypes.c_uint8),
        ('pm_tmr_len', ctypes.c_uint8),
        ('gpe0_blk_len', ctypes.c_uint8),
        ('gpe1_blk_len', ctypes.c_uint8),
        ('gpe1_base', ctypes.c_uint8),
        ('cst_cnt', ctypes.c_uint8),
        ('p_lvl2_lat', ctypes.c_uint16),
        ('p_lvl3_lat', ctypes.c_uint16),
        ('flush_size', ctypes.c_uint16),
        ('flush_stride', ctypes.c_uint16),
        ('duty_offset', ctypes.c_uint8),
        ('duty_width', ctypes.c_uint8),
        ('day_alrm', ctypes.c_uint8),
        ('mon_alrm', ctypes.c_uint8),
        ('century', ctypes.c_uint8),
        ('iapc_boot_arch', facp_iapc_arch_v5),
        ('reserved1', ctypes.c_uint8),
        ('flags', facp_flags_v5),
        ('reset_reg', GAS),
        ('reset_value', ctypes.c_uint8),
        ('reserved2', ctypes.c_uint8 * 3),
        ('x_firmware_ctrl', ctypes.c_uint64),
        ('x_dsdt', ctypes.c_uint64),
        ('x_pm1a_evt_blk', GAS),
        ('x_pm1b_evt_blk', GAS),
        ('x_pm1a_cnt_blk', GAS),
        ('x_pm1b_cnt_blk', GAS),
        ('x_pm2_cnt_blk', GAS),
        ('x_pm_tmr_blk', GAS),
        ('x_gpe0_blk', GAS),
        ('x_gpe1_blk', GAS),
        ('sleep_control_reg', GAS),
        ('sleep_status_reg', GAS),
    ]

    _formats = {
        'preferred_pm_profile': unpack.format_table("{}", _preferred_pm_profile),
    }

def FACP(val):
    """Create class based on decode of an FACP table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    if hdr.revision < 3:
        cls = FACP_v1
    elif hdr.revision == 3:
        cls = FACP_v3
    elif hdr.revision == 4:
        cls = FACP_v4
    else:
        cls = FACP_v5
    if isinstance(val, str):
        return cls.from_buffer_copy(data)
    return cls.from_address(addr)

parse_facp = make_compat_parser("FACP")

class facs_global_lock_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pending', ctypes.c_uint32, 1),
        ('owned', ctypes.c_uint32, 1),
    ]

class facs_global_lock(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facs_global_lock_bits),
    ]

class facs_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('s4bios_f', ctypes.c_uint32, 1),
    ]

class facs_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facs_flags_bits),
    ]

class facs_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('s4bios_f', ctypes.c_uint32, 1),
    ]

class facs_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facs_flags_bits),
    ]

class facs_flags_bits_v2(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('s4bios_f', ctypes.c_uint32, 1),
        ('64bit_wake_supported_f', ctypes.c_uint32, 1),
    ]

class facs_flags_v2(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facs_flags_bits_v2),
    ]

class facs_ospm_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('64bit_wake_f', ctypes.c_uint32, 1),
    ]

class facs_ospm_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', facs_ospm_flags_bits),
    ]

class FACS_v0(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 4),
        ('length', ctypes.c_uint32),
        ('hardware_signature', ctypes.c_uint32),
        ('firmware_waking_vector', ctypes.c_uint32),
        ('global_lock', facs_global_lock),
        ('flags', facs_flags),
        ('reserved', ctypes.c_uint8 * 40),
    ]

class FACS_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 4),
        ('length', ctypes.c_uint32),
        ('hardware_signature', ctypes.c_uint32),
        ('firmware_waking_vector', ctypes.c_uint32),
        ('global_lock', facs_global_lock),
        ('flags', facs_flags),
        ('x_firmware_waking_vector', ctypes.c_uint64),
        ('version', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8 * 31),
    ]

class FACS_v2(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('signature', ctypes.c_char * 4),
        ('length', ctypes.c_uint32),
        ('hardware_signature', ctypes.c_uint32),
        ('firmware_waking_vector', ctypes.c_uint32),
        ('global_lock', facs_global_lock),
        ('flags', facs_flags_v2),
        ('x_firmware_waking_vector', ctypes.c_uint64),
        ('version', ctypes.c_uint8),
        ('pad', ctypes.c_uint8 * 3),
        ('ospm_flags', facs_ospm_flags),
        ('reserved', ctypes.c_uint8 * 24),
    ]

def FACS(val):
    """Create class based on decode of an FACS table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    cls = FACS_v0
    r = FACS_v0.from_address(addr)
    if r.length != ctypes.sizeof(FACS_v0):
        r = FACS_v1.from_address(addr)
        if r.version == 1:
            cls = FACS_v1
        elif r.version == 2:
            cls = FACS_v2
    if isinstance(val, str):
        return cls.from_buffer_copy(data)
    return cls.from_address(addr)

parse_facs = make_compat_parser("FACS")

class MCFGResource(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('address', ctypes.c_uint64),
        ('segment', ctypes.c_uint16),
        ('start_bus', ctypes.c_uint8),
        ('end_bus', ctypes.c_uint8),
        ('reserved', ctypes.c_uint32),
    ]

def mcfg_factory(num_resources):
    """Create variable-sized MCFG table based on the number of resources."""
    class MCFG(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('reserved', ctypes.c_uint64),
            ('resources', num_resources * MCFGResource),
        ]
    return MCFG

def MCFG(val):
    """Create class based on decode of an MCFG table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_tables = (hdr.length - ctypes.sizeof(mcfg_factory(0))) / ctypes.sizeof(MCFGResource)
    if isinstance(val, str):
        return mcfg_factory(num_tables).from_buffer_copy(data)
    return mcfg_factory(num_tables).from_address(addr)

parse_mcfg = make_compat_parser("MCFG")

class trigger_error_header(bits.cdata.Struct):
    """Trigger error header used with the trigger_error_action table."""
    _pack_ = 1
    _fields_ = [
        ('header_size', ctypes.c_uint32),
        ('revision', ctypes.c_uint32),
        ('table_size', ctypes.c_uint32),
        ('entry_count', ctypes.c_uint32),
    ]

def trigger_error_action_factory(num_entries):
    """Create variable-sized trigger error action table based on the number of trigger error instruction entries."""
    class trigger_error_action(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', trigger_error_header),
            ('entries', num_entries * InjectionInstructionEntry),
        ]
    return trigger_error_action

def trigger_error_action(val):
    """Create class based on decode of an trigger_error_action table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = trigger_error_header.from_address(addr)
    num_entries = (hdr.table_size - ctypes.sizeof(trigger_error_action_factory(0))) / ctypes.sizeof(InjectionInstructionEntry)
    if isinstance(val, str):
        return trigger_error_action(num_entries).from_buffer_copy(data)
    return trigger_error_action_factory(num_entries).from_address(addr)

_error_injection_action = {
    0x0  : 'BEGIN_INJECTION_OPERATION',
    0x1  : 'GET_TRIGGER_ERROR_ACTION_TABLE',
    0x2  : 'SET_ERROR_TYPE',
    0x3  : 'GET_ERROR_TYPE',
    0x4  : 'END_OPERATION',
    0x5  : 'EXECUTE_OPERATION',
    0x6  : 'CHECK_BUSY_STATUS',
    0x7  : 'GET_COMMAND_STATUS',
    0x8  : 'SET_ERROR_TYPE_WITH_ADDRESS',
    0xFF : 'TRIGGER_ERROR',
}

_error_injection_instruction = {
    0x00 : 'READ_REGISTER',
    0x01 : 'READ_REGISTER_VALUE',
    0x02 : 'WRITE_REGISTER',
    0x03 : 'WRITE_REGISTER_VALUE',
    0x04 : 'NOOP',
}

class error_type_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('processor_correctable', ctypes.c_uint32, 1),
        ('processor_uncorrectable_non_fatal', ctypes.c_uint32, 1),
        ('processor_uncorrectable_fatal', ctypes.c_uint32, 1),
        ('memory_correctable', ctypes.c_uint32, 1),
        ('memory_uncorrectable_non_fatal', ctypes.c_uint32, 1),
        ('memory_uncorrectable_fatal', ctypes.c_uint32, 1),
        ('pci_express_correctable', ctypes.c_uint32, 1),
        ('pci_express_uncorrectable_non_fatal', ctypes.c_uint32, 1),
        ('pci_express_uncorrectable_fatal', ctypes.c_uint32, 1),
        ('platform_correctable', ctypes.c_uint32, 1),
        ('platform_uncorrectable_non_fatal', ctypes.c_uint32, 1),
        ('platform_encorrectable_fatal', ctypes.c_uint32, 1),
        ('reserved_12_30', ctypes.c_uint32, 19),
        ('vendor_defined', ctypes.c_uint32, 1),
    ]

class error_type_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', error_type_flags_bits),
    ]

class pcie_sbdf_struct_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('reserved_8_0', ctypes.c_uint32, 8),
        ('function_num', ctypes.c_uint32, 3),
        ('device_num', ctypes.c_uint32, 5),
        ('bus_num', ctypes.c_uint32, 8),
        ('pcie_segment', ctypes.c_uint32, 8),
    ]

class pcie_sbdf_struct(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', pcie_sbdf_struct_bits),
    ]

class set_error_type_with_addr_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('processor_apic_valid', ctypes.c_uint32, 1),
        ('memory_addr_and_mask_valid', ctypes.c_uint32, 1),
        ('pcie_sbdf_valid', ctypes.c_uint32, 1),
        ('reserved_31_3', ctypes.c_uint32, 29),
    ]

class set_error_type_with_addr_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', set_error_type_with_addr_flags_bits),
    ]

class set_error_type_with_addr(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('error_type', error_type_flags),
        ('vendor_error_type_extension_structure_offset', ctypes.c_uint32),
        ('flags', set_error_type_with_addr_flags),
        ('apic_id', ctypes.c_uint32),
        ('memory_address', ctypes.c_uint64),
        ('memory_address_range', ctypes.c_uint64),
        ('pcie_sbdf', pcie_sbdf_struct),
    ]

class vendor_error_type_extension(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('length', ctypes.c_uint32),
        ('sbdf', pcie_sbdf_struct),
        ('vendor_id', ctypes.c_uint16),
        ('device_id', ctypes.c_uint16),
        ('rev_id', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8 * 3),
    ]

class injection_instruction_entry_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('preserve_register', ctypes.c_uint8, 1),
    ]

class injection_instruction_entry_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', injection_instruction_entry_flags_bits),
    ]

class InjectionInstructionEntry(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('injection_action', ctypes.c_uint8),
        ('instruction', ctypes.c_uint8),
        ('flags', injection_instruction_entry_flags),
        ('reserved', ctypes.c_uint8),
        ('register_region', GAS),
        ('value', ctypes.c_uint64),
        ('mask', ctypes.c_uint64),
    ]
    _formats = {
        'injection_action' : unpack.format_table("{}", _error_injection_action),
        'instruction' : unpack.format_table("{}", _error_injection_instruction),
    }

def einj_factory(num_entries):
    """Create variable-sized EINJ table based on the number of injection instruction entries."""
    class EINJ(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('injection_header_size', ctypes.c_uint32),
            ('injection_flags', ctypes.c_uint8),
            ('reserved', 3 * ctypes.c_uint8),
            ('injection_entry_count', ctypes.c_uint32),
            ('entries', num_entries * InjectionInstructionEntry),
        ]
    return EINJ

def EINJ(val):
    """Create class based on decode of an EINJ table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_entries = (hdr.length - ctypes.sizeof(einj_factory(0))) / ctypes.sizeof(InjectionInstructionEntry)
    if isinstance(val, str):
        return einj_factory(num_entries).from_buffer_copy(data)
    return einj_factory(num_entries).from_address(addr)

parse_einj = make_compat_parser("EINJ")

class error_severity_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('correctable', ctypes.c_uint32, 1),
        ('fatal', ctypes.c_uint32, 1),
        ('corrected', ctypes.c_uint32, 1),
        ('none', ctypes.c_uint32, 1),
        ('reserved', ctypes.c_uint32, 28),
    ]

class error_severity_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', error_severity_flags_bits),
    ]

class generic_error_data_entry(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('section_type', bits.cdata.GUID),
        ('error_severity', error_severity_flags),
        ('revision', ctypes.c_uint16),
        ('validation_bits', ctypes.c_uint8),
        ('flags', ctypes.c_uint8),
        ('error_data_length', ctypes.c_uint32),
        #('FRU_id', ?),
        ('FRU_text', ctypes.c_uint8),
        #('data', array of generic_error_data),
    ]

class block_status_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('uncorrectable_error_valid', ctypes.c_uint32, 1),
        ('correctable_error_valid', ctypes.c_uint32, 1),
        ('multiple_uncorrectable_errors', ctypes.c_uint32, 1),
        ('multiple_correctable_errors', ctypes.c_uint32, 1),
        ('error_data_entry_count', ctypes.c_uint32, 10),
        ('reserved', ctypes.c_uint32, 18),
    ]

class block_status_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', block_status_flags_bits),
    ]

class boot_error_region(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('block_status', block_status_flags),
        ('raw_data_offset', ctypes.c_uint32),
        ('raw_data_length', ctypes.c_uint32),
        ('data_length', ctypes.c_uint32),
        ('error_severity', error_severity_flags),
        ('generic_error_data', generic_error_data_entry),
    ]

class BERT_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('boot_error_region_length', ctypes.c_uint32),
        ('boot_error_region', ctypes.c_uint64),
    ]

def BERT(val):
    """Create class based on decode of an BERT table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
        return BERT_v1.from_buffer_copy(data)
    return BERT_v1.from_address(addr)

parse_bert = make_compat_parser("BERT")

class APICSubtable(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('subtype', ctypes.c_uint8),
        ('length', ctypes.c_uint8),
    ]

class local_apic_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint32, 1),
    ]

class local_apic_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', local_apic_flags_bits),
    ]

class APICSubtableLocalApic(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('proc_id', ctypes.c_uint8),
        ('apic_id', ctypes.c_uint8),
        ('flags', local_apic_flags),
    ]

class APICSubtableIOApic(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('io_apic_id', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8),
        ('io_apic_addr', ctypes.c_uint32),
        ('global_sys_int_base', ctypes.c_uint32),
    ]

mps_inti_polarity = {
    0b00: 'Conforms to bus specifications',
    0b01: 'Active high',
    0b11: 'Active low',
}

mps_inti_trigger_mode = {
    0b00: 'Conforms to bus specifications',
    0b01: 'Edge-triggered',
    0b11: 'Level-triggered',
}

class APICSubtable_int_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('polarity', ctypes.c_uint16, 2),
        ('trigger_mode', ctypes.c_uint16, 2),
    ]
    _formats = {
        'polarity': unpack.format_table("{}", mps_inti_polarity),
        'trigger_mode': unpack.format_table("{}", mps_inti_trigger_mode),
    }

class APICSubtable_int_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', APICSubtable_int_flags_bits),
    ]

class APICSubtableNmiIntSrc(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('flags', APICSubtable_int_flags),
        ('global_sys_interrupt', ctypes.c_uint32),
    ]

class APICSubtableLocalApicNmi(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('proc_id', ctypes.c_uint8),
        ('flags', APICSubtable_int_flags),
        ('lint_num', ctypes.c_uint8),
    ]

class APICSubtableIntSrcOverride(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('bus', ctypes.c_uint8),
        ('source', ctypes.c_uint8),
        ('global_sys_interrupt', ctypes.c_uint32),
        ('flags', APICSubtable_int_flags)
    ]

class APICSubtableLocalx2Apic(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('reserved', ctypes.c_uint16),
        ('x2apicid', ctypes.c_uint32),
        ('flags', local_apic_flags),
        ('uid', ctypes.c_uint32),
    ]

class APICSubtableLocalx2ApicNmi(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('flags', APICSubtable_int_flags),
        ('uid', ctypes.c_uint32),
        ('lint_num', ctypes.c_uint8),
        ('reserved', ctypes.c_uint8 * 3),
    ]

_performance_interrupt_mode = {
    0: 'Level-triggered',
    1: 'Edge-triggered',
}

class APICSubtableLocalGIC_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint32, 1),
        ('performance_interrupt_mode', ctypes.c_uint32, 1),
    ]
    _formats = {
        'performance_interrupt_mode': unpack.format_table("{}", mps_inti_polarity),
    }

class APICSubtableLocalGIC_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', APICSubtableLocalGIC_flags_bits),
    ]

class APICSubtableLocalGIC(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('reserved', ctypes.c_uint16),
        ('gic_id', ctypes.c_uint32),
        ('uid', ctypes.c_uint32),
        ('flags', APICSubtableLocalGIC_flags),
        ('parking_protocol_version', ctypes.c_uint32),
        ('performance_interrupt_gsiv', ctypes.c_uint32),
        ('parked_address', ctypes.c_uint64),
        ('physical_base_adddress', ctypes.c_uint64),
    ]

class APICSubtableLocalGICDistributor(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(APICSubtable._fields_) + [
        ('reserved1', ctypes.c_uint16),
        ('gic_id', ctypes.c_uint32),
        ('physical_base_adddress', ctypes.c_uint64),
        ('system_vector_base', ctypes.c_uint32),
        ('reserved2', ctypes.c_uint32),
    ]

def APICSubtableUnknown_factory(_len):
    class APICSubtableUnknown(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = APICSubtable._fields_ + [
            ('data', ctypes.c_uint8 * _len),
        ]
    return APICSubtableUnknown

MADT_TYPE_LOCAL_APIC = 0
MADT_TYPE_IO_APIC = 1
MADT_TYPE_INT_SRC_OVERRIDE = 2
MADT_TYPE_NMI_INT_SRC = 3
MADT_TYPE_LOCAL_APIC_NMI = 4
MADT_TYPE_LOCAL_X2APIC = 9
MADT_TYPE_LOCAL_X2APIC_NMI = 0xA
MADT_TYPE_LOCAL_GIC = 0xB
MADT_TYPE_LOCAL_GIC_DISTRIBUTOR = 0xC

class APIC_table_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pcat_compat', ctypes.c_uint32, 1),
    ]

class APIC_table_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', APIC_table_flags_bits),
    ]

def apic_factory(field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class APIC_v3(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('local_apic_address', ctypes.c_uint32),
            ('flags', APIC_table_flags),
            ('interrupt_controller_structures', subtables),
        ]

        @property
        def procid_apicid(self):
            procid_apicid_dict = {}
            for subtable in self.interrupt_controller_structures:
                # accumulate the dictionary
                if subtable.subtype == MADT_TYPE_LOCAL_APIC:
                    if subtable.flags.bits.enabled == 1:
                        procid_apicid_dict[subtable.proc_id] = subtable.apic_id
            return procid_apicid_dict

        @property
        def uid_x2apicid(self):
            uid_x2apicid_dict = {}
            for subtable in self.interrupt_controller_structures:
                # accumulate the dictionary
                if subtable.subtype == MADT_TYPE_LOCAL_X2APIC:
                    if subtable.flags.bits.enabled == 1:
                        uid_x2apicid_dict[subtable.uid] = subtable.x2apicid
            return uid_x2apicid_dict

    return APIC_v3

def apic_subtable_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    while addr < end:
        subtable_num += 1
        subtable = APICSubtable.from_address(addr)
        addr += subtable.length
        if subtable.subtype == MADT_TYPE_LOCAL_APIC:
            cls = APICSubtableLocalApic
        elif subtable.subtype == MADT_TYPE_IO_APIC:
            cls = APICSubtableIOApic
        elif subtable.subtype == MADT_TYPE_INT_SRC_OVERRIDE:
            cls = APICSubtableIntSrcOverride
        elif subtable.subtype == MADT_TYPE_NMI_INT_SRC:
            cls = APICSubtableNmiIntSrc
        elif subtable.subtype == MADT_TYPE_LOCAL_APIC_NMI:
            cls = APICSubtableLocalApicNmi
        elif subtable.subtype == MADT_TYPE_LOCAL_X2APIC:
            cls = APICSubtableLocalx2Apic
        elif subtable.subtype == MADT_TYPE_LOCAL_X2APIC_NMI:
            cls = APICSubtableLocalx2ApicNmi
        elif subtable.subtype == MADT_TYPE_LOCAL_GIC:
            cls = APICSubtableLocalGIC
        elif subtable.subtype == MADT_TYPE_LOCAL_GIC_DISTRIBUTOR:
            cls = APICSubtableLocalGICDistributor
        else:
            cls = APICSubtableUnknown_factory(subtable.length - ctypes.sizeof(APICSubtable))
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

def APIC(val):
    """Create class based on decode of an APIC table from address or filename."""
    preamble_length = ctypes.sizeof(apic_factory(list()))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    subtable_list = apic_subtable_list(addr + preamble_length, hdr.length - preamble_length)
    if isinstance(val, str):
        return apic_factory(subtable_list).from_buffer_copy(data)
    return apic_factory(subtable_list).from_address(addr)

def parse_apic(printflag=False, EnabledOnly=False, instance=1):
    """Parse and optionally print an ACPI MADT table."""

    apic = parse_table("APIC", instance)
    if apic is None:
        return None, None
    if printflag:
        with ttypager.page():
            print apic
    if EnabledOnly:
        with ttypager.page():
            print '\n'.join(str(subtable) for subtable in apic.interrupt_controller_structures if ((subtable.subtype in (MADT_TYPE_LOCAL_APIC, MADT_TYPE_LOCAL_X2APIC)) and subtable.flags.bits.enabled))
    return apic

def _mat_factory(field_list):
    class _mat_subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    return _mat_subtables

def _MAT(mat_buffer):
    """Multiple APIC Table Entry"""
    buf = ctypes.create_string_buffer(mat_buffer, len(mat_buffer))
    addr = ctypes.addressof(buf)
    subtable_list = apic_subtable_list(addr, len(buf))
    return _mat_factory(subtable_list).from_buffer_copy(buf)

def parse_mat(mat_data):
    """Parse Multiple APIC Table Entry"""
    return _MAT(mat_data)

class ASFSubtable(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('record_type', ctypes.c_uint8, 7),
        ('last_record', ctypes.c_uint8, 1),
        ('reserved', ctypes.c_uint8),
        ('record_length', ctypes.c_uint16),
    ]

def ASF_subtable_unknown_factory(data_len):
    class ASFSubtableUnknown(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(ASFSubtable._fields_) + [
            ('data', ctypes.c_uint8 * data_len),
        ]
    return ASFSubtableUnknown

class ASF_info_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('smbus_support', ctypes.c_uint8, 1),
    ]

class ASF_info_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ASF_info_flags_bits),
    ]

class fixed_smbus_address(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('ASF_compliant_device', ctypes.c_uint8, 1),
        ('address', ctypes.c_uint8, 7),
    ]

class ASF_info_record(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(ASFSubtable._fields_) + [
        ('min_watchdog_reset_value', ctypes.c_uint8),
        ('min_pollng_interval', ctypes.c_uint8),
        ('system_id', ctypes.c_uint16),
        ('iana_manufacturer_id', ctypes.c_uint8 * 4),
        ('flags', ASF_info_flags),
        ('reserved2', ctypes.c_uint8 * 3),
    ]

class ASF_ALERTDATA(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('device_address', ctypes.c_uint8),
        ('command', ctypes.c_uint8),
        ('data_mask', ctypes.c_uint8),
        ('compare_value', ctypes.c_uint8),
        ('event_sensor_type', ctypes.c_uint8),
        ('event_type', ctypes.c_uint8),
        ('event_offset', ctypes.c_uint8),
        ('event_source_type', ctypes.c_uint8),
        ('event_severity', ctypes.c_uint8),
        ('sendor_number', ctypes.c_uint8),
        ('entity', ctypes.c_uint8),
        ('entity_instance', ctypes.c_uint8),
    ]

def ASF_alrt_factory(num_alerts):
    class ASF_ALRT(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(ASFSubtable._fields_) + [
            ('assertion_event_mask', ctypes.c_uint8),
            ('deassertion_event_mask', ctypes.c_uint8),
            ('number_alerts', ctypes.c_uint8),
            ('array_element_length', ctypes.c_uint8),
            ('device_array', ASF_ALERTDATA * num_alerts),
        ]
    return ASF_ALRT

class ASF_CONTROLDATA(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('function', ctypes.c_uint8),
        ('device_address', ctypes.c_uint8),
        ('command', ctypes.c_uint8),
        ('data_value', ctypes.c_uint8),
    ]

def ASF_rctl_factory(num_controls):
    class ASF_RCTL(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(ASFSubtable._fields_) + [
            ('number_controls', ctypes.c_uint8),
            ('array_element_length', ctypes.c_uint8),
            ('reserved2', ctypes.c_uint16),
            ('control_array', ASF_CONTROLDATA * num_controls),
        ]
    return ASF_RCTL

class ASF_boot_options_capabilities_1_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('firmware_verbosity_screen_blank', ctypes.c_uint8, 1),
        ('power_button_lock', ctypes.c_uint8, 1),
        ('reset_button_lock', ctypes.c_uint8, 1),
        ('reserved_4_3', ctypes.c_uint8, 2),
        ('lock_keyboard', ctypes.c_uint8, 1),
        ('sleep_button_lock', ctypes.c_uint8, 1),
        ('reserved_7', ctypes.c_uint8, 1),
    ]

class ASF_boot_options_capabilities_1(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ASF_boot_options_capabilities_1_bits),
    ]

class ASF_boot_options_capabilities_2_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('reserved_2_0', ctypes.c_uint8, 3),
        ('user_password_bypass', ctypes.c_uint8, 1),
        ('forced_progress_events', ctypes.c_uint8, 1),
        ('firmware_verbosity_verbose', ctypes.c_uint8, 1),
        ('firmware_verbosity_quiet', ctypes.c_uint8, 1),
        ('configuration_data_reset', ctypes.c_uint8, 1),
    ]

class ASF_boot_options_capabilities_2(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ASF_boot_options_capabilities_2_bits),
    ]

class ASF_special_commands_2_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('force_pxe_boot', ctypes.c_uint8, 1),
        ('force_hard_drive_boot', ctypes.c_uint8, 1),
        ('force_hard_drive_safe_mode_boot', ctypes.c_uint8, 1),
        ('force_diagnostic_boot', ctypes.c_uint8, 1),
        ('force_cd_dvd_boot', ctypes.c_uint8, 1),
        ('reserved', ctypes.c_uint8, 3),
    ]

class ASF_special_commands_2(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ASF_special_commands_2_bits),
    ]

class ASF_system_capabilities_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('power_cycle_reset_only_on_secure_port', ctypes.c_uint8, 1),
        ('power_down_only_on_secure_port', ctypes.c_uint8, 1),
        ('power_on_only_on_secure_port', ctypes.c_uint8, 1),
        ('reset_only_on_secure_port', ctypes.c_uint8, 1),
        ('power_cycle_reset_on_compat_or_secure_port', ctypes.c_uint8, 1),
        ('power_down_on_compat_or_secure_port', ctypes.c_uint8, 1),
        ('power_on_via_compat_or_secure_port', ctypes.c_uint8, 1),
        ('reset_only_on_compat_or_secure_port', ctypes.c_uint8, 1),
    ]

class ASF_system_capabilities(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', ASF_system_capabilities_bits),
    ]

class ASF_rmcp(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(ASFSubtable._fields_) + [
        ('boot_options_capabilities_1', ASF_boot_options_capabilities_1),
        ('boot_options_capabilities_2', ASF_boot_options_capabilities_2),
        ('boot_options_capabilities_3', ctypes.c_uint8),
        ('boot_options_capabilities_4', ctypes.c_uint8),
        ('special_commands_1', ctypes.c_uint8),
        ('special_commands_2', ASF_special_commands_2),
        ('system_capabilities', ASF_system_capabilities),
        ('completion_code', ctypes.c_uint8),
        ('iana', ctypes.c_uint8 * 4),
        ('special_command', ctypes.c_uint8),
        ('special_command_parameter', ctypes.c_uint8 * 2),
        ('boot_options', ctypes.c_uint8 * 2),
        ('oem_parameters', ctypes.c_uint8 * 2),
    ]

def ASF_addr_record_factory(num_devices):

    class ASF_addr_record(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(ASFSubtable._fields_) + [
            ('seeprom_address', ctypes.c_uint8),
            ('num_devices', ctypes.c_uint8),
            ('fixed_smbus_addresses', fixed_smbus_address * num_devices),
        ]
    return ASF_addr_record

def ASF_factory(field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class ASF_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('information_records', subtables),
        ]

    return ASF_v1

ASF_INFO = 0
ASF_ALRT = 1
ASF_RCTL = 2
ASF_RMCP = 3
ASF_ADDR = 4

def ASF_subtable_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    ASF_addr_record_base_len = ctypes.sizeof(ASF_addr_record_factory(0))
    ASF_alrt_base = ASF_alrt_factory(0)
    ASF_rctl_base = ASF_rctl_factory(0)
    while addr < end:
        subtable_num += 1
        subtable = ASFSubtable.from_address(addr)
        if subtable.record_type == ASF_INFO:
            cls = ASF_info_record
        elif subtable.record_type == ASF_ALRT:
            num_alerts = ASF_alrt_base.from_address(addr).number_alerts
            cls = ASF_alrt_factory(num_alerts)
        elif subtable.record_type == ASF_RCTL:
            num_controls = ASF_rctl_base.from_address(addr).number_controls
            cls = ASF_rctl_factory(num_controls)
        elif subtable.record_type == ASF_RMCP:
            cls = ASF_rmcp
        elif subtable.record_type == ASF_ADDR:
            cls = ASF_addr_record_factory(subtable.record_length - ASF_addr_record_base_len)
        else:
            cls = (subtable.record_length - ctypes.sizeof(ASFSubtable))
        addr += subtable.record_length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

def ASF(val):
    """Create class based on decode of an ASF! table from address or filename."""
    base_length = ctypes.sizeof(ASF_factory(list()))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    field_list = ASF_subtable_list(addr + base_length, hdr.length - base_length)
    if isinstance(val, str):
        return ASF_factory(field_list).from_buffer_copy(data)
    return ASF_factory(field_list).from_address(addr)

parse_asf = make_compat_parser("ASF!")

class PCCTSubtable(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('subtype', ctypes.c_uint8),
        ('length', ctypes.c_uint8),
    ]

def pcct_subtable_unknown_factory(data_len):
    class PCCTSubtableUnknown(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(PCCTSubtable._fields_) + [
            ('data', ctypes.c_uint8 * data_len),
        ]
    return PCCTSubtableUnknown

class PCCTGenericCommSubspace(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(PCCTSubtable._fields_) + [
        ('reserved', ctypes.c_uint8 * 6),
        ('base_address', ctypes.c_uint64),
        ('mem_range_length', ctypes.c_uint64),
        ('doorbell_register', GAS),
        ('doorbell_preserve', ctypes.c_uint64),
        ('doorbell_write', ctypes.c_uint64),
        ('nominal_latency', ctypes.c_uint32),
        ('max_periodic_access_rate', ctypes.c_uint32),
        ('min_request_turnaround_time', ctypes.c_uint16),
    ]

class PCCT_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('sci_doorbell', ctypes.c_uint32, 1),
    ]

class PCCT_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', PCCT_flags_bits),
    ]

def pcct_factory(field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class PCCT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('flags', PCCT_flags),
            ('reserved', ctypes.c_uint64),
            ('pcc_subspace_structures', subtables),
        ]

    return PCCT_v1

PCCT_GENERIC_COMMUNICATION_SUBSPACE = 0

def pcct_subtable_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    while addr < end:
        subtable_num += 1
        subtable = PCCTSubtable.from_address(addr)
        if subtable.subtype == PCCT_GENERIC_COMMUNICATION_SUBSPACE:
            cls = PCCTGenericCommSubspace
        else:
            cls = pcct_subtable_unknown_factory(subtable.length - ctypes.sizeof(PCCTSubtable))
        addr += subtable.length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

def PCCT(val):
    """Create class based on decode of an PCCT table from address or filename."""
    base_length = ctypes.sizeof(pcct_factory(list()))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    field_list = pcct_subtable_list(addr + base_length, hdr.length - base_length)
    if isinstance(val, str):
        return pcct_factory(field_list).from_buffer_copy(data)
    return pcct_factory(field_list).from_address(addr)

parse_pcct = make_compat_parser("PCCT")

PMTT_component_memory_type = {
    0b00:   'Volatile memory',
    0b01:   'Both volatile and non-volatile memory',
    0b10:   'Non-volatile memory',
}

class PMTT_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('top_level_aggregator_device', ctypes.c_uint16, 1),
        ('physical_topology_element', ctypes.c_uint16, 1),
    ]
    _formats = {
        'component_memory_type': unpack.format_table("{}", PMTT_component_memory_type),
    }

class PMTT_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', PMTT_flags_bits),
    ]

class PMTTSubtable(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('subtype', ctypes.c_uint8),
        ('reserved1', ctypes.c_uint8),
        ('length', ctypes.c_uint16),
        ('flags', PMTT_flags),
        ('reserved2', ctypes.c_uint16),
    ]

def PMTTSubtableSocket_factory(field_list):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class PMTTSubtableSocket(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(PMTTSubtable._fields_) + [
            ('socket_identifier', ctypes.c_uint16),
            ('reserved', ctypes.c_uint16),
            ('memory_controller_structures', subtables),
        ]

    return PMTTSubtableSocket

def PMTTSubtableMemController_factory(num_proximity_domains, field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class PMTTSubtableMemController(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(PMTTSubtable._fields_) + [
            ('read_latency', ctypes.c_uint32),
            ('write_latency', ctypes.c_uint32),
            ('read_bandwidth', ctypes.c_uint32),
            ('write_bandwidth', ctypes.c_uint32),
            ('optimal_access_unit', ctypes.c_uint16),
            ('optimal_access_aligment', ctypes.c_uint16),
            ('reserved', ctypes.c_uint16),
            ('number_proximity_domains', ctypes.c_uint16),
            ('domains', (ctypes.c_uint32 * num_proximity_domains)),
            ('physical_component_identifier_structures', subtables),
        ]

    return PMTTSubtableMemController

class PMTTSubtableDIMM(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(PMTTSubtable._fields_) + [
        ('physical_component_id', ctypes.c_uint16),
        ('reserved', ctypes.c_uint16),
        ('dimm_size', ctypes.c_uint32),
        ('smbios_handle', ctypes.c_uint32),
    ]

def pmtt_subtable_unknown_factory(data_len):
    class PMTTSubtableUnknown(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(PMTTSubtable._fields_) + [
            ('data', ctypes.c_uint8 * data_len),
        ]
    return PMTTSubtableUnknown

def pmtt_factory(field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class PMTT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('reserved', ctypes.c_uint32),
            ('memory_aggregator_device_structures', subtables),
        ]

    return PMTT_v1

PMTT_SOCKET = 0
PMTT_MEMORY_CONTROLLER = 1
PMTT_DIMM = 2

def pmtt_subtable_list(addr, length):
    end = addr + length
    field_list = list()
    subtable_num = 0
    skt_base_length = ctypes.sizeof(PMTTSubtableSocket_factory(list()))
    mc_base_cls = PMTTSubtableMemController_factory(0, list())
    while addr < end:
        subtable_num += 1
        subtable = PMTTSubtable.from_address(addr)
        if subtable.subtype == PMTT_SOCKET:
            next_field_list = pmtt_subtable_list(addr + skt_base_length, subtable.length - skt_base_length)
            cls = PMTTSubtableSocket_factory(next_field_list)
        elif subtable.subtype == PMTT_MEMORY_CONTROLLER:
            base_subtable = mc_base_cls.from_address(addr)
            base_length = ctypes.sizeof(PMTTSubtableMemController_factory(base_subtable.number_proximity_domains, list()))
            next_field_list = pmtt_subtable_list(addr + base_length, subtable.length - base_length)
            cls = PMTTSubtableMemController_factory(base_subtable.number_proximity_domains, next_field_list)
        elif subtable.subtype == PMTT_DIMM:
            cls = PMTTSubtableDIMM
        else:
            cls = pmtt_subtable_unknown_factory(subtable.length - ctypes.sizeof(PMTTSubtable))
        addr += subtable.length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

def PMTT(val):
    """Create class based on decode of an PMTT table from address or filename."""
    base_length = ctypes.sizeof(pmtt_factory(list()))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    field_list = pmtt_subtable_list(addr + base_length, hdr.length - base_length)
    if isinstance(val, str):
        return pmtt_factory(field_list).from_buffer_copy(data)
    return pmtt_factory(field_list).from_address(addr)

parse_pmtt = make_compat_parser("PMTT")

class MPSTMemPowerNode_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint8, 1),
        ('power_managed', ctypes.c_uint8, 1),
        ('hot_pluggable', ctypes.c_uint8, 1),
    ]

class MPSTMemPowerNode_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', MPSTMemPowerNode_flags_bits),
    ]

class MPSTState(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('value', ctypes.c_uint8),
        ('information_index', ctypes.c_uint8),
    ]

def MPSTMemPowerNode_factory(num_power_states, num_physical_components):
    class MPSTMemPowerNode(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('flags', MPSTMemPowerNode_flags),
            ('reserved', ctypes.c_uint8),
            ('node_id', ctypes.c_uint16),
            ('length', ctypes.c_uint32),
            ('base_address_low', ctypes.c_uint32),
            ('base_address_high', ctypes.c_uint32),
            ('length_low', ctypes.c_uint32),
            ('length_high', ctypes.c_uint32),
            ('num_power_states', ctypes.c_uint32),
            ('num_physical_components', ctypes.c_uint32),
            ('memory_power_nodes', MPSTState * num_power_states),
            ('physical_component_ids', ctypes.c_uint16 * num_physical_components),
        ]
    return MPSTMemPowerNode

class power_state_structure_id_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pss_id_value', ctypes.c_uint8, 6),
        ('pss_id_revision', ctypes.c_uint8, 2),
    ]

class power_state_structure_id(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', power_state_structure_id_bits),
    ]

class power_state_structure_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('memory_content_preserved', ctypes.c_uint8, 1),
        ('autonomous_power_state_entry', ctypes.c_uint8, 1),
        ('autonomous_power_state_exit', ctypes.c_uint8, 1),
    ]

class power_state_structure_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', power_state_structure_flags_bits),
    ]

class MPSTCharacteristics(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('pss_id', power_state_structure_id),
        ('flags', power_state_structure_flags),
        ('reserved', ctypes.c_uint16),
        ('average_power', ctypes.c_uint32),
        ('relative_power', ctypes.c_uint32),
        ('exit_latency', ctypes.c_uint64),
        ('reserved2', ctypes.c_uint32),
    ]

def mpst_factory(field_list, characteristics_count):

    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class MPST_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('pcc_id', ctypes.c_uint8),
            ('reserved', ctypes.c_uint8 * 3),
            ('memory_power_node_count', ctypes.c_uint16),
            ('reserved2', ctypes.c_uint16),
            ('memory_power_nodes', subtables),
            ('characteristics_count', ctypes.c_uint16),
            ('reserved3', ctypes.c_uint16),
            ('characteristics', MPSTCharacteristics * characteristics_count),
        ]

    return MPST_v1

def mpst_subtable_list(addr, memory_power_node_count):
    field_list = list()
    base_MPSTMemPowerNode = MPSTMemPowerNode_factory(0, 0)
    for subtable_num in range(1, memory_power_node_count + 1):
        subtable = base_MPSTMemPowerNode.from_address(addr)
        cls = MPSTMemPowerNode_factory(subtable.num_power_states, subtable.num_physical_components)
        addr += subtable.length
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    return field_list

def MPST(val):
    """Create class based on decode of an PMTT table from address or filename."""
    base_length = ctypes.sizeof(mpst_factory(list(), 0))
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    mpst = mpst_factory(list(), 0).from_address(addr)
    field_list = mpst_subtable_list(ctypes.addressof(mpst.memory_power_nodes), mpst.memory_power_node_count)
    mpst = mpst_factory(field_list, 0).from_address(addr)
    if isinstance(val, str):
        return mpst_factory(field_list, mpst.characteristics_count).from_buffer_copy(data)
    return mpst_factory(field_list, mpst.characteristics_count).from_address(addr)

parse_mpst = make_compat_parser("MPST")

class MSCTProximityDomainInfo_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('revision', ctypes.c_uint8),
        ('length', ctypes.c_uint8),
        ('proximity_domain_range_low', ctypes.c_uint32),
        ('proximity_domain_range_high', ctypes.c_uint32),
        ('max_processor_capacity', ctypes.c_uint32),
        ('max_memory_capacity', ctypes.c_uint64),
    ]

def msct_factory(num_proxdominfo):
    class MSCT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('proximity_domain_info_offset', ctypes.c_uint32),
            ('max_proximity_domains', ctypes.c_uint32),
            ('max_clock_domains', ctypes.c_uint32),
            ('max_physical_address', ctypes.c_uint64),
            ('proximity_domain_info_structs', num_proxdominfo * MSCTProximityDomainInfo_v1),
        ]
    return MSCT_v1

def MSCT(val):
    """Create class based on decode of an MSCT table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    num_tables = (hdr.length - ctypes.sizeof(TableHeader)) / ctypes.sizeof(MSCTProximityDomainInfo_v1)
    if isinstance(val, str):
        return msct_factory(num_tables).from_buffer_copy(data)
    return msct_factory(num_tables).from_address(addr)

parse_msct = make_compat_parser("MSCT")

def msdm_factory(data_len):
    """Create variable-sized MSDM table."""
    class MSDM_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('software_licensing_structure', ctypes.c_uint8 * data_len),
        ]
    return MSDM_v1

def MSDM(val):
    """Create class based on decode of an MSDM table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    data_len = hdr.length - ctypes.sizeof(msdm_factory(0))
    if isinstance(val, str):
        return msdm_factory(data_len).from_buffer_copy(data)
    return msdm_factory(data_len).from_address(addr)

parse_msdm = make_compat_parser("MSDM")

def slic_factory(data_len):
    """Create variable-sized SLIC table."""
    class SLIC_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('software_licensing_structure', ctypes.c_uint8 * data_len)
        ]
    return SLIC_v1

def SLIC(val):
    """Create class based on decode of an SLIC table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    data_len = hdr.length - ctypes.sizeof(slic_factory(0))
    if isinstance(val, str):
        return slic_factory(data_len).from_buffer_copy(data)
    return slic_factory(data_len).from_address(addr)

parse_slic = make_compat_parser("SLIC")

def slit_factory(num_system_localities):
    class SLIT_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('number_system_localities', ctypes.c_uint64),
            ('relative_distances', ctypes.c_uint8 * num_system_localities * num_system_localities),
        ]
    return SLIT_v1

def SLIT(val):
    """Create class based on decode of an DMAR table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    s = slit_factory(0).from_address(addr)
    if isinstance(val, str):
        return slit_factory(s.number_system_localities).from_buffer_copy(data)
    return slit_factory(s.number_system_localities).from_address(addr)

parse_slit = make_compat_parser("SLIT")

class SRATSubtable(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('subtype', ctypes.c_uint8),
            ('length', ctypes.c_uint8),
        ]

class SRATLocalApicAffinity_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint32, 1),
    ]

class SRATLocalApicAffinity_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', SRATLocalApicAffinity_flags_bits),
    ]

class SRATLocalApicAffinity(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(SRATSubtable._fields_) + [
        ('proximity_domain_7_0', ctypes.c_uint8),
        ('apic_id', ctypes.c_uint8),
        ('flags', SRATLocalApicAffinity_flags),
        ('local_sapic_eid', ctypes.c_uint8),
        ('proximity_domain_31_8', ctypes.c_uint8 * 3),
        ('clock_domain', ctypes.c_uint32),
    ]

class SRATMemoryAffinity_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint32, 1),
        ('hot_pluggable', ctypes.c_uint32, 1),
        ('nonvolatile', ctypes.c_uint32, 1),
    ]

class SRATMemoryAffinity_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', SRATMemoryAffinity_flags_bits),
    ]

class SRATMemoryAffinity(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(SRATSubtable._fields_) + [
        ('proximity_domain', ctypes.c_uint32),
        ('reserved1', ctypes.c_uint8 * 2),
        ('base_address_low', ctypes.c_uint32),
        ('base_address_high', ctypes.c_uint32),
        ('length_low', ctypes.c_uint32),
        ('length_high', ctypes.c_uint32),
        ('reserved2', ctypes.c_uint32),
        ('flags', SRATMemoryAffinity_flags),
        ('reserved3', ctypes.c_uint64),
    ]

class SRATLocalX2ApicAffinity_flags_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('enabled', ctypes.c_uint32, 1),
    ]

class SRATLocalX2ApicAffinity_flags(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', SRATLocalX2ApicAffinity_flags_bits),
    ]

class SRATLocalX2ApicAffinity(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = copy.copy(SRATSubtable._fields_) + [
        ('reserved1', ctypes.c_uint16),
        ('proximity_domain', ctypes.c_uint32),
        ('x2apic_id', ctypes.c_uint32),
        ('flags', SRATLocalX2ApicAffinity_flags),
        ('clock_domain', ctypes.c_uint32),
        ('reserved2', ctypes.c_uint32),
    ]

def SRATSubtableUnknown_factory(_len):
    class SRATSubtableUnknown(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = copy.copy(SRATSubtable._fields_) + [
            ('data', ctypes.c_uint8 * _len),
        ]
    return SRATSubtableUnknown

SRAT_LOCAL_APIC_AFFINITY = 0
SRAT_MEMORY_AFFINITY = 1
SRAT_LOCAL_X2APIC_AFFINITY = 2

def srat_factory(field_list):
    class subtables(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = field_list

        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class SRAT_v3(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('reserved1', ctypes.c_uint32),
            ('reserved2', ctypes.c_uint64),
            ('subtables', subtables),
        ]
        def __str__(self):
            out = StringIO()
            print >>out, "SRAT Summary\n"
            mem = [t for t in self.subtables if (t.subtype == SRAT_MEMORY_AFFINITY) and t.flags.bits.enabled]
            if mem:
                print >>out, "Enabled Memory Affinity Domains"
                for m in mem:
                    domain = m.proximity_domain
                    addr = (m.base_address_high << 32) + m.base_address_low
                    len = (m.length_high << 32) +  m.length_low
                    print >>out, "domain = {:#x}  base address = {:#016x}  length = {:#016x}".format(domain, addr, len)
                print >>out
            xapic = [t for t in  self.subtables if (t.subtype == SRAT_LOCAL_APIC_AFFINITY) and t.flags.bits.enabled]
            x2apic = [t for t in  self.subtables if (t.subtype == SRAT_LOCAL_X2APIC_AFFINITY) and t.flags.bits.enabled]
            if xapic or x2apic:
                domain_apicids = {}
                print >>out, "Enabled Processor Affinity Domains"
                for x in xapic:
                    domain = (x.proximity_domain_31_8[2] << 24) + (x.proximity_domain_31_8[1] << 16) + (x.proximity_domain_31_8[0] << 8) + x.proximity_domain_7_0
                    domain_apicids.setdefault(domain, []).append(x.apic_id)
                for x2 in x2apic:
                    domain_apicids.setdefault(x2.proximity_domain, []).append(x2.x2apic_id)
                for domain, apicids in domain_apicids.iteritems():
                    print >>out, "domain={:#x}  apicids={}".format(domain, ','.join("{:#x}".format(a) for a in sorted(apicids)))
                print >>out
            print >>out, super(SRAT_v3, self).__str__()
            return out.getvalue()

    return SRAT_v3

def SRAT(val):
    """Create class based on decode of an SRAT table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    hdr = TableHeader.from_address(addr)
    end = addr + hdr.length
    current = addr + ctypes.sizeof(srat_factory(list()))
    field_list = list()
    subtable_num = 0
    while current < end:
        subtable_num += 1
        subtable = SRATSubtable.from_address(current)
        current += subtable.length
        if subtable.subtype == SRAT_LOCAL_APIC_AFFINITY:
            cls = SRATLocalApicAffinity
        elif subtable.subtype == SRAT_MEMORY_AFFINITY:
            cls = SRATMemoryAffinity
        elif subtable.subtype == SRAT_LOCAL_X2APIC_AFFINITY:
            cls = SRATLocalX2ApicAffinity
        else:
            cls = srat_subtable_unknown_factory(subtable.length - ctypes.sizeof(SRATSubtable))
        field_list.append( ('subtable{}'.format(subtable_num), cls) )
    if isinstance(val, str):
        return srat_factory(field_list).from_buffer_copy(data)
    return srat_factory(field_list).from_address(addr)

def parse_srat(printflag=False, EnabledOnly=False, instance=1):
    """Parse and optionally print an SRAT table."""

    srat = parse_table("SRAT", instance)
    if srat is None:
        return None
    if printflag:
        with ttypager.page():
            print srat
    if EnabledOnly:
        with ttypager.page():
            print '\n'.join(str(subtable) for subtable in srat.subtables if subtable.flags.bits.enabled)
    return srat

def _asid_str(asid):
    if asid >= 0xC0 and asid <= 0xff:
        return 'OEM Defined'
    _asid = {
        ASID_SYSTEM_MEMORY: 'System Memory',
        ASID_SYSTEM_IO: 'System IO',
        ASID_PCI_CFG_SPACE: 'PCI Configuration Space',
        ASID_EMBEDDED_CONTROLLER: 'Embedded Controller',
        ASID_SMBUS: 'SMBus',
        ASID_PCC: 'Platform Communications Channel (PCC)',
        ASID_FFH: 'Functional Fixed Hardware',
        }
    return _asid.get(asid, 'Reserved')

class flow_control_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('DCD', ctypes.c_uint8, 1),
        ('RTSCTS', ctypes.c_uint8, 1),
        ('XONXOFF', ctypes.c_uint8, 1),
    ]

class flow_control(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', flow_control_bits),
    ]

# Decode for baud rate the BIOS used for redirection
baud = {
    3: 9600,
    4: 19200,
    6: 57600,
    7: 115200,
}
def _format_baud(val):
    return baud.get(val, 'Reserved')

class SPCR_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('interface_type', ctypes.c_uint8),
        ('reserved0', ctypes.c_uint8 * 3),
        ('base_address', GAS),
        ('int_type', ctypes.c_uint8),
        ('irq', ctypes.c_uint8),
        ('global_sys_int', ctypes.c_uint32),
        ('baud_rate', ctypes.c_uint8),
        ('parity', ctypes.c_uint8),
        ('stop_bits', ctypes.c_uint8),
        ('flow_control', flow_control),
        ('terminal_type', ctypes.c_uint8),
        ('reserved1', ctypes.c_uint8),
        ('pci_did', ctypes.c_uint16),
        ('pci_vid', ctypes.c_uint16),
        ('pci_bus', ctypes.c_uint8),
        ('pci_dev', ctypes.c_uint8),
        ('pci_func', ctypes.c_uint8),
        ('pci_flags', ctypes.c_uint32),
        ('pci_segment', ctypes.c_uint8),
        ('reserved2', ctypes.c_uint8 * 4)
    ]
    _formats = {
        'baud_rate': unpack.format_function("{}", _format_baud),
        'parity': unpack.format_table("{}", { 0: 'No Parity' }),
        'stop_bits': unpack.format_table("{}", { 1: '1 stop bit' }),
    }

def SPCR(val):
    """Create class based on decode of an SPCR table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
        return SPCR_v1.from_buffer_copy(data)
    return SPCR_v1.from_address(addr)

parse_spcr = make_compat_parser("SPCR")

class event_timer_block_id_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('hardware_rev_id', ctypes.c_uint32, 8),
        ('num_comparators', ctypes.c_uint32, 5),
        ('count_size_cap_counter_size', ctypes.c_uint32, 1),
        ('reserved', ctypes.c_uint32, 1),
        ('legacy_replacement_IRQ_routing_capable', ctypes.c_uint32, 1),
        ('pci_vid', ctypes.c_uint32, 16),
    ]

class event_timer_block_id(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint32),
        ('bits', event_timer_block_id_bits),
    ]

_page_protection_table = {
    0: 'No Guarantee for page protection',
    1: '4KB page protected',
    2: '64KB page protected',
}

class hpet_capabilities_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('page_protection', ctypes.c_uint8, 4),
        ('oem_attributes', ctypes.c_uint8, 4),
    ]
    _formats = {
        'page_protection': unpack.format_table("{:#x}", _page_protection_table),
    }

class hpet_capabilities(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint8),
        ('bits', hpet_capabilities_bits),
    ]

class HPET_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('event_timer_block_id', event_timer_block_id),
        ('base_address', GAS),
        ('hpet_number', ctypes.c_uint8),
        ('main_counter_min_clock_tick_in_periodic_mode', ctypes.c_uint16),
        ('capabilities', hpet_capabilities),
    ]

def HPET(val):
    """Create class based on decode of an HPET table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
        return HPET_v1.from_buffer_copy(data)
    return HPET_v1.from_address(addr)

parse_hpet = make_compat_parser("HPET")

def uefi_factory(data_len):

    class UEFI_v1(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('header', TableHeader),
            ('identifier', bits.cdata.GUID),
            ('data_offset', ctypes.c_uint16),
            ('data', ctypes.c_uint8 * data_len),
        ]
        _formats = {
            'identifier': bits.cdata._format_guid,
        }

    return UEFI_v1

def UEFI(val):
    """Create class based on decode of an UEFI table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
    u = TableHeader.from_address(addr)
    data_len = u.length - ctypes.sizeof(uefi_factory(0))
    if isinstance(val, str):
        return uefi_factory(data_len).from_buffer_copy(data)
    return uefi_factory(data_len).from_address(addr)

parse_uefi = make_compat_parser("UEFI")

_wdt_available_decode = {
    0: 'permanently disabled',
    1: 'available',
}

_wdt_active_decode = {
    0: 'WDT stopped when BIOS hands off control',
    1: 'WDT running when BIOS hnads off control',
}

_ownership_decode = {
    0: 'TCO is owned by the BIOS',
    1: 'TCO is owned by the OS',
}

class wddt_status_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('wdt_available', ctypes.c_uint16, 1),
        ('wdt_active', ctypes.c_uint16, 1),
        ('ownership', ctypes.c_uint16, 1),
        ('reserved', ctypes.c_uint16, 8),
        ('user_reset_event', ctypes.c_uint16, 1),
        ('wdt_event', ctypes.c_uint16, 1),
        ('power_fail_event', ctypes.c_uint16, 1),
        ('unknown_reset_event', ctypes.c_uint16, 1),
    ]
    _formats = {
        'wdt_available': unpack.format_table("{}", _wdt_available_decode),
        'wdt_active': unpack.format_table("{}", _wdt_active_decode),
        'ownership': unpack.format_table("{}", _ownership_decode),
    }

class wddt_status(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', wddt_status_bits),
    ]

class wddt_capability_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('auto_reset', ctypes.c_uint16, 1),
        ('alert_support', ctypes.c_uint16, 1),
        ('platform_directed_shutdown', ctypes.c_uint16, 1),
        ('immediate_shutdown', ctypes.c_uint16, 1),
        ('bios_handoff_support', ctypes.c_uint16, 1),
    ]

class wddt_capability(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ("bits",)
    _fields_ = [
        ('data', ctypes.c_uint16),
        ('bits', wddt_capability_bits),
    ]

class WDDT_v1(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('header', TableHeader),
        ('tco_spec_version', ctypes.c_uint16),
        ('tco_description_table_version', ctypes.c_uint16),
        ('pci_vid', ctypes.c_uint16),
        ('tco_base_address', GAS),
        ('timer_min_count', ctypes.c_uint16),
        ('timer_max_count', ctypes.c_uint16),
        ('timer_count_period', ctypes.c_uint16),
        ('status', wddt_status),
        ('capability', wddt_capability),
    ]

def WDDT(val):
    """Create class based on decode of an WDDT table from address or filename."""
    addr = val
    if isinstance(val, str):
        data = open(val).read()
        buf = ctypes.create_string_buffer(data, len(data))
        addr = ctypes.addressof(buf)
        return WDDT_v1.from_buffer_copy(data)
    return WDDT_v1.from_address(addr)

parse_wddt = make_compat_parser("WDDT")

def get_cpupaths(*args):
    cpupaths, devpaths = _acpi._cpupaths(*args)
    apic = parse_apic()
    procid_apicid = apic.procid_apicid
    uid_x2apicid = apic.uid_x2apicid
    if procid_apicid is None or uid_x2apicid is None:
        # No APIC table exists, so assume the existing cpus are enabled
        return cpupaths
    enabled_cpupaths = []
    for cpupath in cpupaths:
        procdef = evaluate(cpupath)
        if procdef is not None and procdef.ProcId in procid_apicid:
           enabled_cpupaths.append(cpupath)
    for devpath in devpaths:
        uid = evaluate(devpath + "._UID")
        if uid is not None and uid in uid_x2apicid:
           enabled_cpupaths.append(devpath)
    return enabled_cpupaths

def find_procid():
    cpupaths = get_cpupaths()
    cpupath_procid = {}
    for cpupath in cpupaths:
        if get_object_info(cpupath).object_type != ACPI_TYPE_PROCESSOR:
            continue
        processor = evaluate(cpupath)
        if processor is not None:
            cpupath_procid[cpupath] = processor.ProcId
        else:
            cpupath_procid[cpupath] = None
    return OrderedDict(sorted(cpupath_procid.items()))

def find_uid():
    cpupaths = get_cpupaths()
    cpupath_uid = {}
    for cpupath in cpupaths:
        if get_object_info(cpupath).object_type != ACPI_TYPE_DEVICE:
            continue
        value = evaluate(cpupath + "._UID")
        cpupath_uid[cpupath] = value
    return OrderedDict(sorted(cpupath_uid.items()))

def commonprefix(l):
    """Return the common prefix of a list of strings."""
    if not l:
        return ''
    prefix = l[0]
    for s in l[1:]:
        for i, c in enumerate(prefix):
            if c != s[i]:
                prefix = s[:i]
                break
    return prefix

def factor_commonprefix(l):
    if not l:
        return ''
    if len(l) == 1:
        return l[0]
    prefix = commonprefix(l)
    prefixlen = len(prefix)
    return prefix + "{" + ", ".join([s[prefixlen:] for s in l]) + "}"

def display_cpu_info():
    cpupaths = get_cpupaths()
    cpupath_procid = find_procid()
    cpupath_uid = find_uid()
    apic = parse_apic()
    procid_apicid = apic.procid_apicid
    uid_x2apicid = apic.uid_x2apicid
    if procid_apicid is None or uid_x2apicid is None:
        return
    socketindex_cpuscope = {}
    s = factor_commonprefix(cpupaths) + '\n'
    for cpupath in cpupaths:
        s += '\n' + cpupath
        def socket_str(apicid):
            socket_index = bits.socket_index(apicid)
            if socket_index is None:
                return ''
            return ', socketIndex=0x%02x' % socket_index
        def apicid_str(apicid):
            if apicid is None:
                return 'no ApicID'
            return 'ApicID=0x%02x%s' % (apicid, socket_str(apicid))
        procid = cpupath_procid.get(cpupath, None)
        if procid is not None:
            s += ' ProcID=%-2u (%s) ' % (procid, apicid_str(procid_apicid.get(procid, None)))
            socketindex_cpuscope.setdefault(bits.socket_index(procid_apicid.get(procid, None)), []).append(scope(cpupath))
        uid = cpupath_uid.get(cpupath, None)
        if uid is not None:
            s += ' _UID=%s (%s)' % (uid, apicid_str(uid_x2apicid.get(uid, None)))
            socketindex_cpuscope.setdefault(bits.socket_index(uid_x2apicid.get(uid, None)), []).append(scope(cpupath))
    for value, scopes in socketindex_cpuscope.iteritems():
        unique_scopes = set(scopes)
        s += '\nsocket {0} contains {1} processors and {2} ACPI scope: {3}\n'.format(value, len(scopes), len(unique_scopes), ','.join(sorted(unique_scopes)))
    ttypager.ttypager_wrap(s, indent=False)

def display_acpi_method(method, print_one):
    """Helper function that performs all basic processing for evaluating an ACPI method"""
    cpupaths = get_cpupaths()
    uniques = {}
    for cpupath in cpupaths:
        value = evaluate(cpupath + "." + method)
        uniques.setdefault(value, []).append(cpupath)

    print ttypager._wrap("%u unique %s values" % (len(uniques), method))
    for value, cpupaths in sorted(uniques.iteritems(), key=(lambda (k,v): v)):
        print
        print ttypager._wrap(factor_commonprefix(cpupaths))
        if value is None:
            print "No %s found for these CPUs" % method
        else:
            print_one(value)

def parse_cpu_method(method):
    cls = globals()["parse" + string.lower(method)]
    cpupaths = get_cpupaths()
    uniques = {}
    for cpupath in cpupaths:
        value = evaluate(cpupath + "." + method)
        if value is not None:
            obj = cls(value)
        else:
            obj = None
        uniques.setdefault(obj, []).append(cpupath)
    return uniques

def display_cpu_method(method):
    uniques = parse_cpu_method(method)
    lines = [ttypager._wrap("{} unique {} values".format(len(uniques), method))]
    for value, cpupaths in sorted(uniques.iteritems(), key=(lambda (k,v): v)):
        lines.append("")
        lines.append(ttypager._wrap(factor_commonprefix(cpupaths)))
        if value == None:
            lines.append("No {} found for these CPUs".format(method))
        elif ctypes.sizeof(value) == 0:
            lines.append("No {} found for these CPUs".format(method))
        else:
            lines.extend(ttypager._wrap(str(value), indent=False).splitlines())
    ttypager.ttypager("\n".join(lines))

def _CSD_factory(num_dependencies):
    class CStateDependency(bits.cdata.Struct):
        """C-State Dependency"""
        _pack_ = 1
        _fields_ = [
            ('num_entries', ctypes.c_uint32),
            ('revision', ctypes.c_uint8),
            ('domain', ctypes.c_uint32),
            ('coordination_type', ctypes.c_uint32),
            ('num_processors', ctypes.c_uint32),
            ('index', ctypes.c_uint32),
        ]
        _formats = {
            'coordination_type': unpack.format_table("{:#x}", _coordination_types)
        }
        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class _CSD(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('CStateDependencies', CStateDependency * num_dependencies),
        ]
    return _CSD

def parse_csd(dependencies):
    """Parse C-State Dependency"""
    return _CSD_factory(len(csd_data))(csd_data)

class CState(bits.cdata.Struct):
    """Processor Power States (CStates)"""
    _pack_ = 1
    _fields_ = [
        ('register', SingleRegister),
        ('type', ctypes.c_uint8),
        ('latency', ctypes.c_uint16),
        ('power', ctypes.c_uint32),
    ]
    _formats = {
        'type': lambda x: "C{}".format(x),
        'latency': lambda x: "{} us".format(x),
        'power': lambda x: "{} mW".format(x),
    }
    def __iter__(self):
        for f in self._fields_:
            yield getattr(self, f[0])

def make_CStates(data):
    if data is None:
        return None
    if isinstance(data, tuple):
        if len(data) == 4:
            if isinstance(data[0], SingleRegister):
                return CState(*data)
        return tuple(make_CStates(v) for v in data)
    return data

def _CST_factory(num_cstates):
    class _CST(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('count', ctypes.c_uint32),
            ('CStates', CState * num_cstates),
        ]
    return _CST

def parse_cst(cst_data):
    """Parse Processor Power States (_CST)"""
    cst_data = make_resources(cst_data)
    return _CST_factory(cst_data[0])(cst_data[0], cst_data[1:])

#if hasattr(cstate, 'FFH'):
#    # Decode register as FFH
#    if cstate.FFH.VendorCode == 0:
#        desc += "C1 Halt"
#    elif (cstate.FFH.VendorCode == 1) and (cstate.FFH.ClassCode == 1):
#        desc += "C1 I/O then Halt I/O port address = {#x}".format(Register.Arg0)
#    elif (cstate.FFH.VendorCode == 1) and (cstate.FFH.ClassCode == 2):
#        desc += "MWAIT {:#02x} ({})".format(cstate.FFH.Arg0, cpulib.mwait_hint_to_cstate(cstate.FFH.Arg0))
#        desc += " {} {}BMAvoid".format(("SWCoord", "HWCoord")[bool(cstate.FFH.Arg1 & 1)], ("!", "")[bool(cstate.FFH.Arg1 & (1 << 1))])
#    lines.append("C{cstate_num:<d}  {desc}".format(cstate_num=cstate_num, desc=desc))
#else:
#    # Decode register as actual hardware resource
#    lines.append("    {:11s} {:10s} {:9s} {:10s} {:8s}".format("AddrSpaceId", "BitWidth", "BitOffset", "AccessSize", "Address"))
#    lines.append("C{cstate_num:<d}  {r.AddressSpaceId:<#11x} {r.BitWidth:<#10x} {r.BitOffset:<#9x} {r.AccessSize:<#10x} {r.Address:<#8x}".format(cstate_num=cstate_num, r=cstate.register))
# Decode and print ACPI c-state, latency, & power
#lines.append("    ACPI C{c.type:<1d}  latency={c.latency}us  power={c.power}mW".format(c=cstate))

class _PCT(bits.cdata.Struct):
    """Performance Control"""
    _pack = 1
    _fields_ = [
        ('control_register', SingleRegister),
        ('status_register', SingleRegister),
    ]

def parse_pct(pct_data):
    """Parse Performance Control"""
    return _PCT(*make_resources(pct_data))

class _PDL(bits.cdata.Struct):
    """P-State Depth Limit"""
    _pack_ = 1
    _fields_ = [
        ('pstate_depth_limit', ctypes.c_uint32),
    ]
    _formats = {
        'pstate_depth_limit': (lambda x : "Lowest performance state that OSPM can use = {}".format(x)),
    }

def parse_pdl(pdl_data):
    """Parse P-State Depth Limit"""
    return _PDL(pdl_data)

class _PPC(bits.cdata.Struct):
    """Performance Present Capabilities"""
    _pack_ = 1
    _fields_ = [
        ('highest_pstate', ctypes.c_uint32),
    ]
    _formats = {
        'highest_pstate': (lambda x : "Highest performance state that OSPM can use = {}".format(x)),
    }

def parse_ppc(ppc_data):
    """Parse Performance Present Capabilities"""
    return _PPC(ppc_data)

_coordination_types = {
    0xFC : 'SW_ALL',
    0xFD : 'SW_ANY',
    0xFE : 'HW_ALL',
}

def _PSD_factory(num_dependencies):
    class PStateDependency(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('num_entries', ctypes.c_uint32),
            ('revision', ctypes.c_uint8),
            ('domain', ctypes.c_uint32),
            ('coordination_type', ctypes.c_uint32),
            ('num_processors', ctypes.c_uint32),
        ]
        _formats = {
            'coordination_type': unpack.format_table("{:#x}", _coordination_types)
        }
        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class _PSD(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('PStateDependencies', PStateDependency * num_dependencies),
        ]
    return _PSD

def parse_psd(psd_data):
    """Parse P-State Dependency"""
    return _PSD_factory(len(psd_data))(psd_data)

def _PSS_factory(num_pstates):
    class PState(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('core_frequency', ctypes.c_uint32),
            ('power', ctypes.c_uint32),
            ('latency', ctypes.c_uint32),
            ('bus_master_latency', ctypes.c_uint32),
            ('control', ctypes.c_uint32),
            ('status', ctypes.c_uint32),
        ]
        _formats = {
            'core_frequency': lambda x: "{} MHz".format(x),
            'power': lambda x: "{} mW".format(x),
            'latency': lambda x: "{} us".format(x),
            'bus_master_latency': lambda x: "{} us".format(x),
        }
        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class _PSS(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('pstates', PState * num_pstates),
        ]
    return _PSS

def parse_pss(pstates):
    """Parse Performance Supported States"""
    return _PSS_factory(len(pstates))(pstates)

class _PTC(bits.cdata.Struct):
    """Processor Throttling Control"""
    _pack = 1
    _fields_ = [
        ('control_register', SingleRegister),
        ('status_register', SingleRegister),
    ]

def parse_ptc(ptc_data):
    """Parse Processor Throttling Control"""
    return _PTC(*make_resources(ptc_data))

class _TDL(bits.cdata.Struct):
    """T-State Depth Limit"""
    _pack_ = 1
    _fields_ = [
        ('lowest_tstate', ctypes.c_uint32),
    ]
    _formats = {
        'lowest_tstate': (lambda x : "Lowest throttling state that OSPM can use = {}".format(x)),
    }

def parse_tdl(tdl_data):
    """Parse T-State Depth Limit"""
    return _TDL(tdl_data)

class _TPC(bits.cdata.Struct):
    """Throttling Present Capabilities"""
    _pack_ = 1
    _fields_ = [
        ('highest_tstate', ctypes.c_uint32),
    ]
    _formats = {
        'highest_tstate': (lambda x : "Highest throttling state that OSPM can use = {}".format(x)),
    }

def parse_tpc(tpc_data):
    """Parse Throttling Present Capabilities"""
    return _TPC(tpc_data)

def _TSD_factory(num_dependencies):
    class TStateDependency(bits.cdata.Struct):
        _pack_ = 1
        _fields_ = [
            ('num_entries', ctypes.c_uint32),
            ('revision', ctypes.c_uint8),
            ('domain', ctypes.c_uint32),
            ('coordination_type', ctypes.c_uint32),
            ('num_processors', ctypes.c_uint32),
        ]
        _formats = {
            'coordination_type': unpack.format_table("{:#x}", _coordination_types)
        }
        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class _TSD(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('TStateDependencies', TStateDependency * num_dependencies),
        ]
    return _TSD

def parse_tsd(dependencies):
    """Parse T-State Dependency"""
    return _TSD_factory(len(dependencies))(dependencies)

def _TSS_factory(num_tstates):
    class TState(bits.cdata.Struct):
        """Throttling Supported States"""
        _pack_ = 1
        _fields_ = [
            ('percent', ctypes.c_uint32),
            ('power', ctypes.c_uint32),
            ('latency', ctypes.c_uint32),
            ('control', ctypes.c_uint32),
            ('status', ctypes.c_uint32),
        ]
        _formats = {
            'percent': lambda x: "{}%".format(x),
            'power': lambda x: "{} mW".format(x),
            'latency': lambda x: "{} us".format(x),
        }
        def __iter__(self):
            for f in self._fields_:
                yield getattr(self, f[0])

    class _TSS(bits.cdata.Struct):
        _pack = 1
        _fields_ = [
            ('TStates', TState * num_tstates),
        ]
    return _TSS

def parse_tss(tss_data):
    """Parse Throttling Supported States"""
    return _TSS_factory(len(tss_data))(tss_data)

def display_uid():
    """Find and display _UID"""
    def print_uid(uid):
        print "_UID = %s" % uid
    display_acpi_method("_UID", print_uid)

_acpica_early_init = CFUNCTYPE(c_bool)(_acpi.acpica_early_init)
_acpica_init = CFUNCTYPE(c_bool)(_acpi.acpica_init)

def needs_early_init(f, docstring=""):
    """Wrap a function that requires minimal ACPICA table-parsing initialization"""
    def acpica_early_init_wrapper(*args):
        if not _acpica_early_init():
            raise RuntimeError("ACPICA module failed minimal initialization.")
        return f(*args)
    acpica_early_init_wrapper.__doc__ = docstring
    return acpica_early_init_wrapper

def needs_init(f, docstring=""):
    """Wrap a function that requires ACPICA initialization"""
    def acpica_init_wrapper(*args):
        if not _acpica_init():
            raise RuntimeError("ACPICA module failed to initialize.")
        return f(*args)
    acpica_init_wrapper.__doc__ = docstring
    return acpica_init_wrapper

AE_OK = 0
AE_BAD_PARAMETER = 0x1001

ACPI_HANDLE = c_void_p
ACPI_IO_ADDRESS = c_ulong
ACPI_OBJECT_TYPE = c_uint32
ACPI_SIZE = c_ulong
ACPI_STATUS = c_uint32
ACPI_STRING = c_char_p
UINT32 = c_uint32

ACPI_ALLOCATE_BUFFER = ACPI_SIZE(-1)
ACPI_ROOT_OBJECT = ACPI_HANDLE(-1)
ACPI_FULL_PATHNAME, ACPI_SINGLE_NAME = range(2)

class ACPI_BUFFER(bits.cdata.Struct):
    _fields_ = (
            ("Length", ACPI_SIZE),
            ("Pointer", c_void_p),
    )

ACPI_WALK_CALLBACK = CFUNCTYPE(ACPI_STATUS, ACPI_HANDLE, UINT32, c_void_p, POINTER(c_void_p))

terminate = CFUNCTYPE(None)(_acpi.acpica_terminate)

ACPI_FREE = CFUNCTYPE(None, c_void_p)(_acpi.ACPI_FREE)

AcpiFormatException = CFUNCTYPE(POINTER(c_char), ACPI_STATUS)(_acpi.AcpiFormatException)

class ACPIException(Exception):
    def __str__(self):
        s = string_at(AcpiFormatException(self.args[0]))
        return "[Error {:#x}] {}".format(self.args[0], s)

def check_status(status):
    """Check an ACPI_STATUS value, and raise an exception if not successful

    To check non-status values that may have the error bit set, use check_error_value instead."""
    if status:
        raise ACPIException(status)

acpi_unsafe_io = True

@CFUNCTYPE(ACPI_STATUS, ACPI_IO_ADDRESS, POINTER(UINT32), UINT32)
def AcpiOsReadPort(Address, Value, Width):
    if Width == 8:
        Value.contents.value = bits.inb(Address) if acpi_unsafe_io else 0xFF
    elif Width == 16:
        Value.contents.value = bits.inw(Address) if acpi_unsafe_io else 0xFFFF
    elif Width == 32:
        Value.contents.value = bits.inl(Address) if acpi_unsafe_io else 0xFFFFFFFF
    else:
        return AE_BAD_PARAMETER
    return AE_OK

@CFUNCTYPE(ACPI_STATUS, ACPI_IO_ADDRESS, UINT32, UINT32)
def AcpiOsWritePort(Address, Value, Width):
    if not acpi_unsafe_io:
        return AE_OK
    if Width == 8:
        bits.outb(Address, Value)
    elif Width == 16:
        bits.outw(Address, Value)
    elif Width == 32:
        bits.outl(Address, Value)
    else:
        return AE_BAD_PARAMETER
    return AE_OK

bits.set_func_ptr(_acpi.AcpiOsReadPort_ptrptr, AcpiOsReadPort)
bits.set_func_ptr(_acpi.AcpiOsWritePort_ptrptr, AcpiOsWritePort)

_AcpiGetHandle_docstring = """Get the object handle associated with an ACPI name"""
AcpiGetHandle = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_HANDLE, ACPI_STRING, POINTER(ACPI_HANDLE))(_acpi.AcpiGetHandle), _AcpiGetHandle_docstring)

_AcpiGetName_docstring = """Get the name of an ACPI object"""
AcpiGetName = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_HANDLE, UINT32, POINTER(ACPI_BUFFER))(_acpi.AcpiGetName), _AcpiGetName_docstring)

_AcpiGetObjectInfo_docstring = """Get info about an ACPI object"""
AcpiGetObjectInfo = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_HANDLE, POINTER(c_void_p))(_acpi.AcpiGetObjectInfo), _AcpiGetObjectInfo_docstring)

_AcpiGetTable_docstring = """Return table specified by the signature and instance"""
AcpiGetTable = needs_early_init(CFUNCTYPE(ACPI_STATUS, ACPI_STRING, UINT32, POINTER(POINTER(TableHeader)))(_acpi.AcpiGetTable), _AcpiGetTable_docstring)

_AcpiGetTableByIndex_docstring = """Return table specified by index"""
AcpiGetTableByIndex = needs_early_init(CFUNCTYPE(ACPI_STATUS, UINT32, POINTER(POINTER(TableHeader)))(_acpi.AcpiGetTableByIndex), _AcpiGetTableByIndex_docstring)

_AcpiOsGetRootPointer_docstring = """Return the address of the ACPI RSDP table"""
AcpiOsGetRootPointer = needs_init(CFUNCTYPE(c_ulong)(_acpi.AcpiOsGetRootPointer), _AcpiOsGetRootPointer_docstring)

_AcpiInstallInterface_docstring = """Install an interface into the _OSI method"""
AcpiInstallInterface = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_STRING)(_acpi.AcpiInstallInterface), _AcpiInstallInterface_docstring)

_AcpiLoadTable_docstring = """Load an SSDT table binary into the ACPI namespace"""
AcpiLoadTable = needs_init(CFUNCTYPE(ACPI_STATUS, POINTER(TableHeader))(_acpi.AcpiLoadTable), _AcpiLoadTable_docstring)

_AcpiRemoveInterface_docstring = """Remove an interface from the _OSI method."""
AcpiRemoveInterface = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_STRING)(_acpi.AcpiRemoveInterface), _AcpiRemoveInterface_docstring)

_AcpiSubsystemStatus_docstring = """Get ACPI subsystem status"""
AcpiSubsystemStatus = needs_init(CFUNCTYPE(ACPI_STATUS)(_acpi.AcpiSubsystemStatus), _AcpiSubsystemStatus_docstring)

_AcpiWalkNamespace_docstring = """Walk the ACPI namespace with callbacks"""
AcpiWalkNamespace = needs_init(CFUNCTYPE(ACPI_STATUS, ACPI_OBJECT_TYPE, ACPI_HANDLE, UINT32, ACPI_WALK_CALLBACK, ACPI_WALK_CALLBACK, c_void_p, POINTER(c_void_p))(_acpi.AcpiWalkNamespace), _AcpiWalkNamespace_docstring)

def get_object_info(pathname):
    """Get object information for an ACPI object."""
    handle = ACPI_HANDLE()
    check_status(AcpiGetHandle(None, pathname, byref(handle)))
    assert handle

    info = c_void_p()
    check_status(AcpiGetObjectInfo(handle, byref(info)))
    assert info

    try:
        length = c_uint32.from_address(info.value).value
        buf = create_string_buffer(length)
        memmove(buf, info, length)
    finally:
        ACPI_FREE(info)

    return ObjectInfo(buf.raw, info.value)

def get_objpaths(objectname, depth=(2**32-1)):
    """Return a list of names of ACPI objects matching objectname

    If depth is specified, search only that deep in the namespace."""
    l = []
    def callback(handle, nesting_level, context, return_value):
        buf = ACPI_BUFFER(ACPI_ALLOCATE_BUFFER, None)
        status = AcpiGetName(handle, ACPI_FULL_PATHNAME, byref(buf))
        if status:
            print "AcpiGetName:", ACPIException(status)
            return 0
        name = string_at(buf.Pointer)
        ACPI_FREE(buf.Pointer)
        if objectname in name:
            l.append(name)
        return 0
    check_status(AcpiWalkNamespace(ACPI_TYPE_ANY, ACPI_ROOT_OBJECT, depth, ACPI_WALK_CALLBACK(callback), ACPI_WALK_CALLBACK(0), None, None))
    return l

def install_interface(name):
    check_status(AcpiInstallInterface(name))

def get_rsdt_addr():
    """Return the address of the RSDT"""
    return RSDP(AcpiOsGetRootPointer()).rsdt_address

def get_xsdt_addr():
    """Return the address of the XSDT

    Returns None if the RSDP does not point to an XSDT, or if the XSDT lives
    above 4GB when running in 32-bit mode."""
    rsdp = RSDP(AcpiOsGetRootPointer())
    try:
        xsdt = rsdp.xsdt_address
    except AttributeError as e:
        return None
    if sizeof(c_void_p) == 4 and xsdt >= 2**32:
        raise RuntimeError("XSDT located above 4G; cannot access on 32-bit")
    return xsdt

def get_table(signature, instance=1):
    """Get the requested ACPI table based on signature"""
    if signature in ('RSDP', 'RSD PTR', 'RSD PTR '):
        if instance == 1:
            rsdp_addr = AcpiOsGetRootPointer()
            rsdp = RSDP(rsdp_addr)
            return string_at(rsdp_addr, sizeof(rsdp))
        return None
    addr = get_table_addr(signature, instance)
    if addr is None:
        return None
    header = TableHeader.from_address(addr)
    return string_at(addr, header.length)

def get_table_addr(signature, instance=1):
    """Get the requested ACPI table address based on signature"""
    special_get = {
        'RSDP': AcpiOsGetRootPointer,
        'RSD PTR': AcpiOsGetRootPointer,
        'RSD PTR ': AcpiOsGetRootPointer,
        'RSDT': get_rsdt_addr,
        'XSDT': get_xsdt_addr,
    }.get(signature)
    if special_get is not None:
        if instance == 1:
            return special_get()
        return None
    header = POINTER(TableHeader)()
    if AcpiGetTable(signature, instance, byref(header)):
        return None
    return addressof(header.contents)

def get_table_by_index(index):
    """Get ACPI table based on an index in the root table"""
    header = POINTER(TableHeader)()
    if AcpiGetTableByIndex(index, byref(header)):
        return None
    return string_at(addressof(header.contents), header.contents.length)

def get_table_addr_by_index(index):
    """Get ACPI table address based on an index in the root table"""
    header = POINTER(TableHeader)()
    if AcpiGetTableByIndex(index, byref(header)):
        return None
    return addressof(header.contents)

def get_table_list():
    """Get the list of ACPI table signatures"""
    tableptrs = itertools.chain(itertools.ifilter(bool, (get_table_addr_by_index(index) for index in range(3))),
                                itertools.takewhile(bool, (get_table_addr_by_index(index) for index in itertools.count(start=3))))
    signatures = [(ctypes.c_char * 4).from_address(ptr).value for ptr in tableptrs]
    signatures.extend([s for s in ['RSDP', 'RSDT', 'XSDT'] if get_table_addr(s)])
    signatures = sorted(set(signatures))
    return signatures

def load_table(table_data):
    """Load an SSDT table binary into the ACPI namespace

    Usage: acpi.load_table(table_data) where table_data contains an ACPI SSDT
    (including header).  The contents of the SSDT can be used to either patch
    existing or add new ACPI methods or data for debug purposes.

    Example usage steps:
    - Create an SSDT ASL source file.
    - Compile to generate a binary image (AML) file.
    - Include the SSDT's AML binary file on the BITS disk or ISO image.
    - Load the SSDT AML binary file into the ACPI namespace, with:
    acpi.load_table(open("/ssdt.aml").read())"""
    buf = create_string_buffer(table_data, len(table_data))
    check_status(AcpiLoadTable(cast(buf, POINTER(TableHeader))))

def display_objects(name="\\", depth=0xffffffff):
    s = ""
    for path in get_objpaths(name, depth):
        s += "{} ({})\n".format(path, acpi_object_types.get(get_object_info(path).object_type, "Reserved"))
    ttypager.ttypager_wrap(s, indent=False)

def dump(name="", depth=0xffffffff):
    s = ''
    for path in get_objpaths(name, depth):
        s += ttypager._wrap('{} : {!r}'.format(path, evaluate(path))) + '\n'
    return s

def dumptable(name="", instance=1):
    """Dump hexadecimal and printable ASCII bytes for an ACPI table specified by 4CC and instance"""
    s = ''
    data = get_table(name, instance)
    if data is None:
        s += "ACPI table with signature of {} and instance of {} not found.\n".format(name, instance)
        return s
    s += bits.dumpmem(data)
    return s

def dumptables():
    """Dump hexdecimal and printable ASCII bytes for all ACPI tables"""
    s = ''
    for signature in get_table_list():
        for instance in itertools.count(1):
            data = get_table(signature, instance)
            if data is None:
                break
            s += "ACPI Table {} instance {}\n".format(signature, instance)
            s += bits.dumpmem(data)
    return s

created_explore_acpi_tables_cfg = False

def create_explore_acpi_tables_cfg():
    global created_explore_acpi_tables_cfg
    if created_explore_acpi_tables_cfg:
        return
    cfg = ""
    try:
        import efi
        cfg += 'menuentry "Save all ACPI tables (raw and decoded) to files" {\n'
        cfg += '    echo "Saving all ACPI tables (raw and decoded) to files..."\n'
        cfg += "    py 'import acpi'\n"
        cfg += "    py 'acpi.efi_save_tables()'\n"
        cfg += '    echo "Done."\n'
        cfg += "    py 'from bits import pause ; pause.pause()'\n"
        cfg += '}\n\n'
        cfg += 'menuentry "Save all ACPI tables (raw only) to files" {\n'
        cfg += '    echo "Saving all ACPI tables (raw only) to files..."\n'
        cfg += "    py 'import acpi'\n"
        cfg += "    py 'acpi.efi_save_tables(decode=False)'\n"
        cfg += '    echo "Done."\n'
        cfg += "    py 'from bits import pause ; pause.pause()'\n"
        cfg += '}\n\n'
    except:
        cfg += 'menuentry "Dump all ACPI tables to log only" {\n'
        cfg += '    echo "Dumping ACPI tables to log..."\n'
        cfg += "    py 'import acpi, bits, redirect'\n"
        cfg += "    py 'with redirect.logonly(): print acpi.dumptables()'\n"
        cfg += '    echo "Done."\n'
        cfg += "    py 'from bits import pause ; pause.pause()'\n"
        cfg += '}\n\n'
    for signature in get_table_list():
        for instance in itertools.count(1):
            if get_table_addr(signature, instance) is None:
                break
            parse_method = 'parse_{}'.format(string.rstrip(str.lower(signature),"!"), instance)
            if parse_method in globals():
                cfg += 'menuentry "Decode {} Instance {}" {{\n'.format(signature, instance)
                cfg += '    py "import acpi ; acpi.{}(printflag=True, instance={})"\n'.format(parse_method, instance)
                cfg += '}\n\n'
            if signature in ("APIC", "SRAT"):
                cfg += 'menuentry "Decode {} Instance {} (enabled only)" {{\n'.format(signature, instance)
                cfg += '    py "import acpi ; acpi.{}(EnabledOnly=True, instance={})"\n'.format(parse_method, instance)
                cfg += '}\n\n'
            cfg += 'menuentry "Dump {} Instance {} raw" {{\n'.format(signature, instance)
            cfg += """    py 'import ttypager, acpi; ttypager.ttypager(acpi.dumptable("{}", {}))'\n""".format(signature, instance)
            cfg += '}\n'
    bits.pyfs.add_static("explore_acpi_tables.cfg", cfg)
    created_explore_acpi_tables_cfg = True

created_explore_acpi_cpu_methods_cfg = False

def create_explore_acpi_cpu_methods_cfg():
    global created_explore_acpi_cpu_methods_cfg
    if created_explore_acpi_cpu_methods_cfg:
        return
    methods = set()
    for c in get_cpupaths():
        for o in get_objpaths(c + "."):
            method = o[len(c)+1:]
            if "." in method:
                continue
            methods.add(method)
    cfg = ""
    for method in sorted(methods):
        # Whitelist for now until splitting this into its own module
        if method in ("_CSD", "_CST", "_MAT", "PDL", "_PPC", "_PCT", "_PTC", "_PSD", "_PSS", "_TDL", "_TPC", "_TSD", "_TSS"):
            parse_method = 'parse' + string.lower(method)
            cfg += 'menuentry "{} ({})" {{\n'.format(method, globals()[parse_method].__doc__)
            cfg += """    py 'import acpi ; acpi.display_cpu_method("{}")'\n""".format(method)
            cfg += '}\n'
    bits.pyfs.add_static("explore_acpi_cpu_methods.cfg", cfg)
    created_explore_acpi_cpu_methods_cfg = True

def show_checksum(signature, instance=1):
    """Compute checksum of ACPI table"""

    data = get_table(signature, instance)
    if data is None:
        print "ACPI table with signature of {} and instance of {} not found.\n".format(signature, instance)
        return

    csum = sum(ord(c) for c in data)
    print 'Full checksum is {:#x}'.format(csum)
    print '1-byte checksum is {:#x}'.format(csum & 0xff)

try:
    import efi

    def efi_save_tables(decode=True):
        """Save all ACPI tables to files; only works under EFI.

        Warning: All files in the /acpi directory will be deleted!"""
        root = efi.get_boot_fs()
        acpidir = root.mkdir("acpi")
        # delete all files in \acpi directory
        if "acpi" in os.listdir("/"):
            print "Deleting old files..."
            for f in os.listdir("/acpi"):
                print "Deleting {}...".format(f),
                acpidir.open(f, efi.EFI_FILE_MODE_READ | efi.EFI_FILE_MODE_WRITE).delete()
                print "Done"

        address_list = ''
        for signature in get_table_list():
            for instance in itertools.count(1):
                data = get_table(signature, instance)
                if data is None:
                    break
                basename = signature
                if instance > 1:
                    basename += "{}".format(instance)
                fname = "{}.bin".format(basename)
                print "Saving {}...".format(fname),
                acpidir.create(fname).write(data)
                print "Done"

                address = get_table_addr(signature, instance)
                address_list += "{:5}: {:#x}\n".format(basename, address)

                parse_method = 'parse_{}'.format(string.rstrip(str.lower(signature),"!"), instance)
                if (decode == True) and (parse_method in globals()):
                    data = "{} address = {:#x}\n".format(basename, address)
                    data += str(parse_table(signature, instance))
                    fname = "{}.txt".format(basename)
                    print "Saving {}...".format(fname),
                    acpidir.create(fname).write(data)
                    print "Done"

        fname = "address_list.txt"
        print "Saving {}...".format(fname),
        acpidir.create(fname).write(address_list)
        print "Done"

except:
    pass

def save_tables_object_format():
    """Save all ACPI tables to a single file.

    The origin is the physical address shifted right by 2 bits. Origins
    dont need to be in order and the length of any data block is
    arbitrary. The address shift by 2 requires all memory data dumps
    start on a 4-byte boundary and the 32-bit data blocks require a
    4-byte ending alignment. This may force data from before the actual
    table start and data beyond the actual table end."""

    def dumpmem_dwords(mem):
        """Dump hexadecimal dwords for a memory buffer"""
        s = ''
        for chunk in bits.grouper(16, mem):
            for dword in bits.grouper(4, chunk):
                s += "".join("  " if x is None else "{:02x}".format(ord(x)) for x in reversed(dword))
                s += " "
            s += '\n'
        return s

    details = ''
    data_list = ''
    for signature in get_table_list():
        for instance in itertools.count(1):
            data = get_table(signature, instance)

            if data is None:
                break

            basename = signature
            if instance > 1:
                basename += "{}".format(instance)

            address = get_table_addr(signature, instance)

            addr_adjust = address % 4
            len_adjust = (len(data) + addr_adjust) % 4
            if len_adjust:
                len_adjust = 4 - len_adjust

            if addr_adjust or len_adjust:
                # Data is not aligned on dword boundary or len is not multiple of dwords
                new_address = address - addr_adjust
                new_length = len(data) + len_adjust
                if addr_adjust:
                    print "Address modified from {} to {}".format(address, new_address)
                if len_adjust:
                    print "Length modified from {} to {}".format(len(data), new_length)
                data = bits.memory(new_address, new_length)
                address = new_address

            details += "{:5}: address={:#x}, address>>2={:#x}, len={}, len/4={}\n".format(basename, address, address>>2, len(data), len(data)/4)

            print "Saving {}...".format(basename),
            data_list += "/origin {:x}\n".format(address >> 2)
            data_list += dumpmem_dwords(data)
            print "Done"

    data_list += "/eof\n"

    fname = "acpi_memory.txt"
    print "Saving {}...".format(fname),
    bits.pyfs.add_static(fname, data_list)
    print "Done"

    fname = "acpi_details.txt"
    print "Saving {}...".format(fname),
    bits.pyfs.add_static(fname, details)
    print "Done"

    with ttypager.page():
        print "The following files have been created:"
        print "  (python)/acpi_details.txt -- the ACPI table details."
        print "  (python)/acpi_memory.txt  -- the ACPI table memory dump."
        print
        print open("(python)/acpi_details.txt").read()
        print
        print open("(python)/acpi_memory.txt").read()
