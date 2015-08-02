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

"""Tests for EFI"""

import ctypes
import efi
import testsuite

def register_tests():
    testsuite.add_test("EFI System Table CRC", test_system_services_crc, submenu="EFI Tests")
    testsuite.add_test("EFI Runtime Services Table CRC", test_runtime_services_crc, submenu="EFI Tests")
    testsuite.add_test("EFI Boot Services Table CRC", test_boot_services_crc, submenu="EFI Tests")

def test_system_services_crc():
    testsuite.test("EFI System Table CRC32 is valid", efi.table_crc(efi.system_table))

def test_runtime_services_crc():
    testsuite.test("EFI Runtime Services Table CRC32 is valid", efi.table_crc(efi.system_table.RuntimeServices.contents))

def test_boot_services_crc():
    testsuite.test("EFI Boot Services Table CRC32 is valid", efi.table_crc(efi.system_table.BootServices.contents))
