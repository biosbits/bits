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

"""Base classes and infrastructure for CPUID and MSR decoding"""

from __future__ import print_function
import bits
import functools
import inspect
import operator
import textwrap

_wrapper = textwrap.TextWrapper(width=78, initial_indent='  ', subsequent_indent='    ')

class CPUID(object):
    # Subclasses must define a "leaf" field as part of the class definition.

    def __init__(self, regs):
        self.regs = regs

    @classmethod
    def read(cls, apicid, subleaf=0):
        r = cls(bits.cpuid(apicid, cls.leaf, subleaf))
        r.apicid = apicid
        r.subleaf = subleaf
        return r

    # FIXME: This allows getting subleaves, but requires having an instance of
    # the class first, which means always reading subleaf 0 and then the
    # desired subleaf.
    def __getitem__(self, subleaf):
        return self.read(self.apicid, subleaf)

    def __eq__(self, other):
        return self.regs == other.regs

    def __ne__(self, other):
        return self.regs != other.regs

    def __str__(self):
        T = type(self)
        fields = dict((regnum, {}) for regnum in range(len(self.regs._fields)))
        properties = list()
        for field_name in dir(T):
            field = getattr(T, field_name)
            if isinstance(field, cpuidfield):
                fields[field.reg][field_name] = field
            elif isinstance(field, property):
                properties.append(field_name)

        heading = "APIC ID {:#x} -- ".format(self.apicid)
        heading += "CPUID (EAX={:#x}".format(self.leaf)
        if self.subleaf:
            heading += ", ECX={:#x}".format(self.subleaf)
        heading += ")"
        s = heading + "\n" + "-"*len(heading) + "\n"
        doc = inspect.getdoc(self)
        if doc:
            s += doc + "\n"

        def format_range(msb, lsb):
            if msb == lsb:
                return "[{}]".format(msb)
            return "[{}:{}]".format(msb, lsb)
        def format_field(msb, lsb, value):
            """Field formatter that special-cases single bits and drops the 0x"""
            if msb == lsb:
                return str(value)
            return "{:#x}".format(value)
        for regnum, regname in enumerate(self.regs._fields):
            s += "\n"
            s1 = "  {}={:#010x} ".format(regname, self.regs[regnum])
            s += s1
            inner = ("\n " + " " * len(s1)).join(
                    "{}{} {}={}".format(regname, format_range(field.msb, field.lsb), field_name, format_field(field.msb, field.lsb, getattr(self, field_name)))
                for field_name, field in sorted(fields[regnum].iteritems(), key=(lambda (k, v): v.lsb))
                )
            if inner:
                s += " {}".format(inner)

        properties = sorted(set(properties))
        if len(properties):
            s += "\n  Attributes derived from one or more fields:"
            for property_name in properties:
                s += '\n'
                temp = "{}={}".format(property_name, getattr(self, property_name))
                s += '\n'.join(_wrapper.wrap(temp))
        return s

class cpuidfield(property):
    def __init__(self, reg, msb, lsb, doc="Bogus"):
        self.reg = reg
        self.msb = msb
        self.lsb = lsb

        max_value = (1 << (msb - lsb + 1)) - 1
        field_mask = max_value << lsb

        def getter(self):
            return (self.regs[reg] & field_mask) >> lsb
        super(cpuidfield, self).__init__(getter, doc=doc)

def make_CPUIDS(classes):
    class CPUIDS(object):
        leafs = dict()
        def __init__(self, apicid):
            self.apicid = apicid
        def __getitem__(self, leaf_in):
            l = self.leafs.get(leaf_in)
            if l is not None:
                return getattr(self, l)
            class DYNAMIC_LEAF_(CPUID):
                __doc__ = "Dynamic CPUID leaf {:#X}".format(leaf_in)
                leaf = leaf_in
            DYNAMIC_LEAF_.__name__ += "{:X}".format(leaf_in)
            return DYNAMIC_LEAF_.read(self.apicid)
        def __iter__(self):
            for leaf_num in sorted(self.leafs.keys()):
                yield self[leaf_num]

    for c in classes:
        assert CPUIDS.leafs.get(c.leaf) is None, "Internal error: Duplicate CPUID leaf {:#X}".format(c.leaf)
        def getter(inner_c, self):
            return inner_c.read(self.apicid)
        setattr(CPUIDS, c.__name__, property(functools.partial(getter, c), None))
        CPUIDS.leafs[c.leaf] = c.__name__
    return CPUIDS

class MSR(object):
    # Subclasses must define a "addr" field as part of the class definition.

    def __init__(self, value=0):
        self.value = value

    def __eq__(self, other):
        return self.value == other.value

    def __ne__(self, other):
        return self.value != other.value

    @classmethod
    def rdmsr(cls, apicid):
        r = cls(bits.rdmsr(apicid, cls.addr))
        r.apicid = apicid
        return r

    def wrmsr(self, apicid=None):
        if apicid is None:
            apicid = self.apicid
        bits.wrmsr(apicid, self.addr, self.value)

    def __str__(self):
        T = type(self)
        fields = {}
        properties = []
        for field_name in dir(T):
            field = getattr(T, field_name)
            if isinstance(field, msrfield):
                fields[field_name] = field
            elif isinstance(field, property):
                properties.append(field_name)

        heading = "APIC ID {:#x} -- ".format(self.apicid)
        heading += "MSR {:#x}".format(self.addr)
        s = heading + "\n" + "-"*len(heading) + "\n"
        doc = inspect.getdoc(self)
        if doc:
            s += doc + "\n\n"
        s += "MSR {:#x}".format(self.addr)
        if self.value is None:
            s += ' value=GPF'
            return s

        s += ' value={:#x}'.format(self.value)

        for field_name, field in sorted(fields.iteritems(), key=(lambda (k, v): v.lsb)):
            s += '\n'
            temp = "[{}:{}] {}={:#x}".format(field.msb, field.lsb, field_name, getattr(self, field_name))
            # FIXME: check wrapper, and use a hanging indent to wrap the docstring to len(temp)+1
            if field.__doc__:
                temp += " " + inspect.getdoc(field)
            s += '\n'.join(_wrapper.wrap(temp))

        if properties:
            s += "\n  Attributes derived from one or more fields:"
            for property_name in sorted(properties):
                s += '\n'
                temp = "{}={}".format(property_name, getattr(self, property_name))
                # FIXME: check wrapper, get the property documentation string if any, and use a hanging indent to wrap the docstring to len(temp)+1
                s += '\n'.join(_wrapper.wrap(temp))
        return s

class msrfield(property):
    def __init__(self, msb, lsb, doc=None):
        self.msb = msb
        self.lsb = lsb

        max_value = (1 << (msb - lsb + 1)) - 1
        field_mask = max_value << lsb

        def getter(self):
            return (self.value & field_mask) >> lsb

        def setter(self, value):
            if value > max_value:
                if msb == lsb:
                    field = "[{0}]".format(msb)
                else:
                    field = "[{0}:{1}]".format(msb, lsb)
                raise OverflowError("Value {value:#x} too big for MSR {self.addr:#x} field {field}".format(**locals()))
            self.value = (self.value & ~field_mask) | (value << lsb)

        super(msrfield, self).__init__(getter, setter, doc=doc)

def make_MSRS(classes):
    class MSRS(object):
        addrs = dict()
        def __init__(self, apicid):
            self.apicid = apicid
        def __getitem__(self, addr_in):
            addr = self.addrs.get(addr_in)
            if addr is not None:
                return getattr(self, addr)
            class DYNAMIC_MSR_(MSR):
                __doc__ = "Dynamic MSR addr {:#x}".format(addr_in)
                addr = addr_in
            DYNAMIC_MSR_.__name__ += "{:x}".format(addr_in)
            return DYNAMIC_MSR_.rdmsr(self.apicid)
        def __iter__(self):
            for addr in sorted(self.addrs.keys()):
                yield self[addr]

    for c in classes:
        if not hasattr(c, "addr"):
            print("Internal error: MSR addr missing {}".format(c.__name__))
        assert MSRS.addrs.get(c.addr) is None, "Internal error: Duplicate MSR addr {:#x}".format(c.addr)
        def getter(inner_c, self):
            return inner_c.rdmsr(self.apicid)
        def setter(inner_c, self, value):
            inner_c(getattr(value, "value", value)).wrmsr(self.apicid)
        setattr(MSRS, c.__name__, property(functools.partial(getter, c), functools.partial(setter, c)))
        MSRS.addrs[c.addr] = c.__name__
    return MSRS
