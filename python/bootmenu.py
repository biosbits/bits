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

"""Boot menu generation"""

from __future__ import print_function
import bits
import ttypager

created_boot_menu = False

try:
    import efi
    boot_str = "{}-bit EFI".format(str(efi.ptrsize * 8))
    have_efi = True

except ImportError as e:
    boot_str = "32-bit BIOS"
    have_efi = False

def generate_boot_menu():
    global created_boot_menu, boot_str

    if created_boot_menu:
        return

    cfg = ""
    cfg += 'menuentry "{} boot detected" {{\n'.format(boot_str)
    cfg += """    py 'import bootmenu; bootmenu.callback()'\n"""
    cfg += '}\n'

    if have_efi:
        cfg += 'menuentry "Exit to EFI" {\n'
        cfg += """    py 'import efi; efi.exit()'\n"""
        cfg += '}\n'

    bits.pyfs.add_static("bootmenu.cfg", cfg)
    created_boot_menu = True

def callback():
    with ttypager.page():
        print("{} boot detected".format(boot_str))
        print("Tests and other menu entries tailored for this environment")
