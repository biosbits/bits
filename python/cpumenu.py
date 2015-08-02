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

"""CPU menu generation"""

from __future__ import print_function
from cpudetect import cpulib
import bits
import ttypager

created_cpu_menu = False

def generate_cpu_menu():
    global created_cpu_menu
    if created_cpu_menu:
        return

    cfg = ""
    cfg += 'menuentry "{}: {}" {{\n'.format(cpulib.name, bits.brandstring())
    cfg += """    py 'import cpumenu; cpumenu.callback()'\n"""
    cfg += '}\n'

    bits.pyfs.add_static("cpumenu.cfg", cfg)
    created_cpu_menu = True

def callback():
    with ttypager.page():
        print(bits.brandstring())
        if cpulib.__name__ == "cpu_gen":
            print("No processor-specific test exists!")
            print("Menu entries will only include generic tests that apply to all processors.")
        else:
            print("Detected as CPU codename: {}".format(cpulib.name))
            print("Menu entries have been tailored to target this specific processor")
