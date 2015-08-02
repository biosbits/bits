# Copyright (c) 2013, Intel Corporation
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

"""Model-specific register (MSR) decoding"""

from bits.platformbase import MSR, msrfield

class IA32_MONITOR_FILTER_SIZE(MSR):
    """IA32_MONITOR_FILTER_SIZE: System coherence line size."""
    addr = 0x6
    size = msrfield(63, 0, doc="System coherence line size.")

class IA32_TIME_STAMP_COUNTER(MSR):
    """IA32_TIME_STAMP_COUNTER: Time stamp counter."""
    addr = 0x10
    tsc = msrfield(63, 0, doc="Time stamp counter.")

class IA32_APIC_BASE(MSR):
    """IA32_APIC_BASE: The status and location of the local APIC."""
    addr = 0x1B

    bsp = msrfield(8, 8, doc="Indicates if this is the bootstrap processor.")
    x2apic_enable = msrfield(10, 10, doc="Enables or disables x2APIC mode")
    apic_enable = msrfield(11, 11, doc="Enables or disables the local APIC")

    apicbase_docstring = """Specifies base address of the APIC registers.

    This 24-bit value is extended by 12 bits at the low end to form
    the base address. This automatically aligns the address on a
    4-KByte boundary. Following a power-up or reset, the field is set
    to FEE0 0000H."""
    apicbase = msrfield(38, 12, doc=apicbase_docstring)

def sample_msrs():
    return [IA32_MONITOR_FILTER_SIZE, IA32_TIME_STAMP_COUNTER, IA32_APIC_BASE]
