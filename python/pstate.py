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

"""Test P-State ratios directly on the CPU."""

import bits
import bits.mwait
import testmsr
import testsuite
import testutil
import time

__all__ = ["turbo_max_plus_one", "turbo_msr", "test_hardware_pstates"]

def turbo_max_plus_one(ratio, min_ratio, max_ratio):
    return ratio

def turbo_msr(ratio, min_ratio, max_ratio):
    MSR_TURBO_RATIO_LIMIT = 0x1ad
    if ratio > max_ratio:
        ratio = testmsr.MSR("turbo ratio", bits.bsp_apicid(), MSR_TURBO_RATIO_LIMIT, highbit=7, lowbit=0)[0]
    return ratio << 8

def test_hardware_pstates(ratio_to_control_value):
    with bits.mwait.use_hint():
        MSR_PLATFORM_INFO = 0xce
        IA32_PERF_CTL = 0x199
        min_ratio = testmsr.MSR("maximum efficiency ratio", bits.bsp_apicid(), MSR_PLATFORM_INFO, highbit=47, lowbit=40)[0]
        max_ratio = testmsr.MSR("max non-turbo ratio", bits.bsp_apicid(), MSR_PLATFORM_INFO, highbit=15, lowbit=8)[0]

        # Get the Turbo Mode Availability flag
        turbo_mode_available = bits.cpuid(bits.bsp_apicid(),0).eax >= 6 and (bits.cpuid(bits.bsp_apicid(),6).eax & 0x2)
        last_ratio = max_ratio
        if turbo_mode_available:
            last_ratio += 1

        duration = last_ratio - min_ratio + 1
        if turbo_mode_available:
            duration += 2
        print "Test duration is ~{} seconds...".format(duration)

        bclk = testutil.adjust_to_nearest(bits.bclk(), 100.0/12) * 1000000

        for ratio in range(min_ratio, last_ratio + 1):
            control_value = ratio_to_control_value(ratio, min_ratio, max_ratio)
            for apicid in bits.cpus():
                bits.wrmsr(apicid, IA32_PERF_CTL, control_value)

            if ratio == max_ratio + 1:
                # Needs to busywait, not sleep
                start = time.time()
                while (time.time() - start < 2):
                    pass

            aperf = bits.cpu_frequency()[1]
            aperf = testutil.adjust_to_nearest(aperf, bclk/2)
            aperf = int(aperf / 1000000)

            expected = int(ratio * bclk / 1000000)

            if ratio == max_ratio + 1:
                testsuite.test("Turbo measured frequency {} >= expected {} MHz".format(aperf, expected), aperf >= expected)
            else:
                testsuite.test("Ratio {} measured frequency {} MHz == expected {} MHz".format(ratio, aperf, expected), aperf == expected)
