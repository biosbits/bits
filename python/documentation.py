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

"""Documentation menu."""

import bits.pyfs
import os
import os.path

created_documentation_cfg = False

def grub_escape(s):
    return "'{}'".format("'\\''".join(s.split("'")))

def create_documentation_cfg():
    global created_documentation_cfg
    if created_documentation_cfg:
        return
    cfg = ""
    docpath = "/boot/Documentation"
    for basename in sorted(os.listdir(docpath)):
        assert '"' not in basename
        assert "'" not in basename
        filename = os.path.join(docpath, basename)
        title = file(filename).readline().strip()
        cfg += 'menuentry {} {{\n'.format(grub_escape("{}: {}".format(basename, title)))
        cfg += """    py 'import ttypager; ttypager.ttypager(file(r"{}").read())'\n""".format(filename)
        cfg += '}\n'
    bits.pyfs.add_static("documentation.cfg", cfg)
    created_documentation_config = True
