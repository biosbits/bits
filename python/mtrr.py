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

"""Memory Type Range Register (MTRR) decoding."""

from __future__ import print_function
import bitfields
import bits
import bits.cdata
import ctypes
import functools
import struct
import ttypager
import unpack

IA32_MTRRCAP_REG = 0xfe
IA32_MTRR_PHYSBASE0_REG = 0x200
IA32_MTRR_PHYSBASE1_REG = 0x202
IA32_MTRR_PHYSBASE2_REG = 0x204
IA32_MTRR_PHYSBASE3_REG = 0x206
IA32_MTRR_PHYSBASE4_REG = 0x208
IA32_MTRR_PHYSBASE5_REG = 0x20A
IA32_MTRR_PHYSBASE6_REG = 0x20C
IA32_MTRR_PHYSBASE7_REG = 0x20E
IA32_MTRR_PHYSBASE8_REG = 0x210
IA32_MTRR_PHYSBASE9_REG = 0x212

IA32_MTRR_PHYSMASK0_REG = 0x201
IA32_MTRR_PHYSMASK1_REG = 0x203
IA32_MTRR_PHYSMASK2_REG = 0x205
IA32_MTRR_PHYSMASK3_REG = 0x207
IA32_MTRR_PHYSMASK4_REG = 0x209
IA32_MTRR_PHYSMASK5_REG = 0x20B
IA32_MTRR_PHYSMASK6_REG = 0x20D
IA32_MTRR_PHYSMASK7_REG = 0x20F
IA32_MTRR_PHYSMASK8_REG = 0x211
IA32_MTRR_PHYSMASK9_REG = 0x213

IA32_MTRR_DEF_TYPE_REG = 0x2ff

def max_phys_addr():
    """Return the max physical address width, in bits.

    Computed on first call, and cached for subsequent return."""
    global max_phys_addr
    max_extended_leaf = bits.cpuid(bits.bsp_apicid(), 0x80000000).eax
    if max_extended_leaf >= 0x80000008:
        # cpuid.(eax=0x80000008).eax[7:0] = max physical-address width supported by the processor
        local_max_phys_addr = bitfields.getbits(bits.cpuid(bits.bsp_apicid(), 0x80000008).eax, 7, 0)
    elif bitfields.getbits(bits.cpuid(bits.bsp_apicid(), 1).edx, 6): # PAE supported
        local_max_phys_addr = 36
    else:
        local_max_phys_addr = 32

    old_func = max_phys_addr
    def max_phys_addr():
        return local_max_phys_addr
    functools.update_wrapper(max_phys_addr, old_func)

    return local_max_phys_addr

def _memory_size_str(bytes):
    suffixes = ['B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    for i in range(1, len(suffixes)):
        div, mod = divmod(bytes, 1024**i)
        if div == 0 or mod != 0:
            i -= 1
            break
    return '{} {}'.format(bytes // (1024**i), suffixes[i])

def _physbase_str(physbase):
    return _memory_size_str(physbase << 12)

def _physmask_str(physmask):
    max_phys_mask = (1 << max_phys_addr()) - 1
    size = (~(physmask << 12) & max_phys_mask) + 1
    return _memory_size_str(size)

class IA32_MTRRCAP_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('VCNT', ctypes.c_uint64, 8),
        ('FIX', ctypes.c_uint64, 1),
        ('reserved_9_9', ctypes.c_uint64, 1),
        ('WRITE', ctypes.c_uint64, 1),
        ('SMRR', ctypes.c_uint64, 1),
        ('reserved_63_12', ctypes.c_uint64, 52),
    ]

class IA32_MTRRCAP(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ('bits',)
    _fields_ = [
        ('u64', ctypes.c_uint64),
        ('bits', IA32_MTRRCAP_bits),
    ]

_decode_memory_type = {
    0x00:   'Uncacheable (UC)',
    0x01:   'Write Combining (WC)',
    0x04:   'Write-through (WT)',
    0x05:   'Write-protected (WP)',
    0x06:   'Writeback (WB)',
}

def _memory_type_str(mem_type):
    return _decode_memory_type.get(mem_type, 'Reserved')

class IA32_MTRR_DEF_TYPE_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('type', ctypes.c_uint64, 8),
        ('reserved_9_8', ctypes.c_uint64, 2),
        ('FE', ctypes.c_uint64, 1),
        ('E', ctypes.c_uint64, 1),
        ('reserved_63_12', ctypes.c_uint64, 52),
    ]
    _formats = {
        'type': unpack.format_function('{:#x}', _memory_type_str),
    }

class IA32_MTRR_DEF_TYPE(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ('bits',)
    _fields_ = [
        ('u64', ctypes.c_uint64),
        ('bits', IA32_MTRR_DEF_TYPE_bits),
    ]

def IA32_MTRR_PHYSBASEn_REG(n):
    _IA32_MTRR_PHYSBASE = [
        IA32_MTRR_PHYSBASE0_REG,
        IA32_MTRR_PHYSBASE1_REG,
        IA32_MTRR_PHYSBASE2_REG,
        IA32_MTRR_PHYSBASE3_REG,
        IA32_MTRR_PHYSBASE4_REG,
        IA32_MTRR_PHYSBASE5_REG,
        IA32_MTRR_PHYSBASE6_REG,
        IA32_MTRR_PHYSBASE7_REG,
        IA32_MTRR_PHYSBASE8_REG,
        IA32_MTRR_PHYSBASE9_REG,
    ]
    assert n in range(len(_IA32_MTRR_PHYSBASE))
    return _IA32_MTRR_PHYSBASE[n]

class IA32_MTRR_PHYSBASE_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('Type', ctypes.c_uint64, 8),
        ('reserved_11_8', ctypes.c_uint64, 4),
        ('PhysBase', ctypes.c_uint64, max_phys_addr()-12),
        ('reserved_63_{}'.format(max_phys_addr()), ctypes.c_uint64, 63-max_phys_addr()),
    ]
    _formats = {
        'Type': unpack.format_function('{:#x}', _memory_type_str),
        'PhysBase': unpack.format_function('{:#x}', _physbase_str),
    }

class IA32_MTRR_PHYSBASE(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ('bits',)
    _fields_ = [
        ('u64', ctypes.c_uint64),
        ('bits', IA32_MTRR_PHYSBASE_bits),
    ]

def IA32_MTRR_PHYSMASKn_REG(n):
    _IA32_MTRR_PHYSMASK = [
        IA32_MTRR_PHYSMASK0_REG,
        IA32_MTRR_PHYSMASK1_REG,
        IA32_MTRR_PHYSMASK2_REG,
        IA32_MTRR_PHYSMASK3_REG,
        IA32_MTRR_PHYSMASK4_REG,
        IA32_MTRR_PHYSMASK5_REG,
        IA32_MTRR_PHYSMASK6_REG,
        IA32_MTRR_PHYSMASK7_REG,
        IA32_MTRR_PHYSMASK8_REG,
        IA32_MTRR_PHYSMASK9_REG,
    ]
    assert n in range(len(_IA32_MTRR_PHYSMASK))
    return _IA32_MTRR_PHYSMASK[n]

class IA32_MTRR_PHYSMASK_bits(bits.cdata.Struct):
    _pack_ = 1
    _fields_ = [
        ('reserved_10_0', ctypes.c_uint64, 11),
        ('V', ctypes.c_uint64, 1),
        ('PhysMask', ctypes.c_uint64, max_phys_addr()-12),
        ('reserved_63_{}'.format(max_phys_addr()), ctypes.c_uint64, 63-max_phys_addr()),
    ]
    _formats = {
        'PhysMask': unpack.format_function('{:#x}', _physmask_str),
    }

class IA32_MTRR_PHYSMASK(bits.cdata.Union):
    _pack_ = 1
    _anonymous_ = ('bits',)
    _fields_ = [
        ('u64', ctypes.c_uint64),
        ('bits', IA32_MTRR_PHYSMASK_bits),
    ]

def variable_mtrrs(apicid=bits.bsp_apicid()):
    assert apicid in bits.cpus()

    ia32_mtrrcap_msr = IA32_MTRRCAP( bits.rdmsr(apicid, IA32_MTRRCAP_REG) )
    ia32_mtrr_def_type_msr = IA32_MTRR_DEF_TYPE(bits.rdmsr(apicid, IA32_MTRR_DEF_TYPE_REG))

    with ttypager.page():
        print("Summary:")
        print("Default memory type: {}".format(_memory_type_str(ia32_mtrr_def_type_msr.type)))
        for i in range(ia32_mtrrcap_msr.VCNT):
            ia32_mtrr_physbase_msr = IA32_MTRR_PHYSBASE(bits.rdmsr(apicid, IA32_MTRR_PHYSBASEn_REG(i)))
            ia32_mtrr_physmask_msr = IA32_MTRR_PHYSMASK(bits.rdmsr(apicid, IA32_MTRR_PHYSMASKn_REG(i)))
            if (ia32_mtrr_physmask_msr.V):
                print("MTRR{}: type={:20}   base={:10}   size={:10}".format(i, _memory_type_str(ia32_mtrr_physbase_msr.Type), _physbase_str(ia32_mtrr_physbase_msr.PhysBase), _physmask_str(ia32_mtrr_physmask_msr.PhysMask)))
        print()
        print(ia32_mtrrcap_msr, end='\n\n')
        print(ia32_mtrr_def_type_msr, end='\n\n')
        for i in range(ia32_mtrrcap_msr.VCNT):
            msr_num = IA32_MTRR_PHYSBASEn_REG(i)
            ia32_mtrr_physbase_msr = IA32_MTRR_PHYSBASE( bits.rdmsr(apicid, msr_num) )
            print("IA32_MTRR_PHYSBASE[{}] MSR {:#x}".format(i, msr_num))
            print(ia32_mtrr_physbase_msr, end='\n\n')

            msr_num = IA32_MTRR_PHYSMASKn_REG(i)
            ia32_mtrr_physmask_msr = IA32_MTRR_PHYSMASK( bits.rdmsr(apicid, msr_num) )
            print("IA32_MTRR_PHYSMASK[{}] MSR {:#x}".format(i, msr_num))
            print(ia32_mtrr_physmask_msr, end='\n\n')
