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

"""testsuite module."""

import bits
import bits.pause
import bits.pyfs
from collections import namedtuple
import functools
import itertools
import os
import textwrap
import ttypager

# Set to true when the most recently run test failed, to support the default
# verbosity level, which shows detail only for failures.
last_test_failed = False

V_NONE, V_FAIL, V_DETAIL, V_PASS = range(4)
verbose = V_DETAIL

def set_verbose(value):
    global verbose
    if value < V_NONE or value > V_PASS:
        raise ValueError("set_verbose: value out of range: {}".format(value))
    verbose = value

def show_verbose():
    ttypager.ttypager(text=
"""Current test verbosity level: {}

Test verbosity levels
    0 = Summary of PASS / FAIL counts only
    1 = Test string output for FAIL only
    2 = Detailed output for FAIL only (default)
    3 = Detailed output for PASS / FAIL
""".format(verbose))

pass_count = fail_count = 0

def passed():
    global last_test_failed, pass_count
    pass_count += 1
    last_test_failed = False

def failed():
    global last_test_failed, fail_count
    fail_count += 1
    last_test_failed = True

def reset():
    global last_test_failed, pass_count, fail_count
    pass_count = fail_count = 0
    last_test_failed = False

def CSR(name, uncore_bus_num, dev, fun, reg, bytes=4, highbit=63, lowbit=0):
    if bytes == 4:
        highbit = min(highbit, 31)
    elif bytes == 2:
        highbit = min(highbit, 15)
    elif bytes == 1:
        highbit = min(highbit, 7)
    value = (bits.pcie_read(uncore_bus_num, dev, fun, reg, bytes) & ((1 << (highbit + 1)) - 1)) >> lowbit
    detail = "{0} (CSR B{1:x}h:D{2}:F{3}:{4:x}h [{5:d}:{6:d}])".format(name, uncore_bus_num, dev, fun, reg, highbit, lowbit)
    detail += " = 0x{0:x}".format(value)
    return value, detail

def get_summary_count():
    return pass_count, fail_count

def test(desc, value):
    """Test a condition; pass if bool(value) is True. Returns bool(value)."""
    condition = bool(value)
    passed() if condition else failed()
    if verbose == V_PASS or (verbose >= V_FAIL and not(condition)):
        print "[assert] {0} {1}".format(desc, pass_fail_str(condition))
    return condition

def pass_fail_str(condition):
    if condition:
        return 'PASS'
    return 'FAIL'

_wrapper = textwrap.TextWrapper(width=78, initial_indent='  ', subsequent_indent='  ')

def print_info(text):
    """Print informative text"""
    if verbose == V_PASS:
        print "[info] {}".format(text)

def show_detail():
    return verbose == V_PASS or (verbose == V_DETAIL and last_test_failed)

def format_detail(data):
    return "\n".join(_wrapper.fill(line) for line in data.splitlines(True))

def print_detail(data):
    if show_detail():
        print format_detail(data)

def summary():
    print 'Summary: {} passed, {} failed'.format(pass_count, fail_count)
    reset()

tests = {}
submenus = []
test_cfg = ""
test_submenu_cfgs = []

class _Test(namedtuple("_Test", ("name", "func", "runall", "runsub"))):
    __slots__ = ()
    def __str__(self):
        tags = []
        if not self.runall:
            tags.append("!all")
        if not self.runsub:
            tags.append("!sub")
        if tags:
            tagstr = " ({})".format(",".join(tags))
        else:
            tagstr = ""
        return self.name + tagstr

def add_test(name, func, submenu=None, runall=True, runsub=None):
    """Add a new test to the test menu.

    Set submenu to a string to put the test in a submenu with that name.  Set
    runall=False to exclude the test from the top-level "Run all tests"; runall
    defaults to True.  Set runsub=False to exclude the test from "Run all
    tests" in its submenu; runsub defaults to the same as runall."""
    if runsub is None:
        runsub = runall
    if submenu not in tests:
        tests[submenu] = []
        if submenu is not None:
            i = len(submenus)
            submenus.append(submenu)
    tests[submenu].append(_Test(name, func, runall, runsub))

def generate_test_cfg():
    global test_cfg, test_submenu_cfgs
    if not tests:
        return ""
    test_cfg = textwrap.dedent('''
        py 'import testsuite'
        menuentry "Run all tests (excluding tests marked !all)" {
            py 'testsuite.test_cfg_callback_all()'
        }''')
    for i, name in enumerate(submenus):
        test_cfg += textwrap.dedent('''
        menuentry "{}" {{
            configfile (python)/test.{}.cfg
        }}'''.format(name, i))
    test_cfg += generate_submenu_config(None, None)
    test_submenu_cfgs = [generate_submenu_config(i, submenu) for i, submenu in enumerate(submenus)]

def generate_submenu_config(submenu_index, submenu):
    cfg = ""
    if submenu is not None:
        cfg += textwrap.dedent('''
        menuentry "Run all tests (excluding tests marked !sub)" {{
            py 'testsuite.test_cfg_callback_suball({})'
        }}'''.format(submenu_index))
    for i, t in enumerate(tests.get(submenu, [])):
        cfg += textwrap.dedent('''
        menuentry "{}" {{
            py 'testsuite.test_cfg_callback({}, {})'
        }}'''.format(str(t), submenu_index, i))
    return cfg

def test_cfg_callback(submenu_index, test_index):
    try:
        if submenu_index is None:
            t = tests[None][test_index]
        else:
            t = tests[submenus[submenu_index]][test_index]
        os.putenv("pager", "1")
        print '\n==== {} ===='.format(t.name)
        reset()
        t.func()
    except Exception as e:
        test("Internal error; test threw exception", False)
        import traceback
        traceback.print_exc()
    finally:
        summary()
        bits.pause.pause()
        os.putenv("pager", "0")

def test_cfg_callback_suball(submenu_index):
    total_passed = total_failed = 0
    submenu = submenus[submenu_index]
    try:
        os.putenv("pager", "1")
        print '\n==== {} ===='.format(submenu)
        reset()
        for t in tests[submenu]:
            if not t.runsub:
                continue
            print '---- {} ----'.format(t.name)
            try:
                t.func()
            except Exception as e:
                test("Internal error; test threw exception", False)
                import traceback
                traceback.print_exc()
            total_passed += pass_count
            total_failed += fail_count
            summary()
    finally:
        print '\n==== Overall summary: {} passed, {} failed ===='.format(total_passed, total_failed)
        bits.pause.pause()
        os.putenv("pager", "0")

def test_cfg_callback_all():
    try:
        os.putenv("pager", "1")
        run_all_tests()
    finally:
        bits.pause.pause()
        os.putenv("pager", "0")

def run_all_tests():
    total_passed = total_failed = 0
    try:
        print "\nRunning all tests"
        reset()
        for submenu in itertools.chain(submenus, [None]):
            heading_printed = False
            for t in tests[submenu]:
                if not t.runall:
                    continue
                if not heading_printed and submenu is not None:
                    print '\n==== {} ===='.format(submenu)
                    heading_printed = True
                try:
                    if submenu is None:
                        print '\n==== {} ===='.format(t.name)
                    else:
                        print '---- {} ----'.format(t.name)
                    t.func()
                except Exception as e:
                    test("Internal error; test threw exception", False)
                    import traceback
                    traceback.print_exc()
                total_passed += pass_count
                total_failed += fail_count
                summary()
    finally:
        print '\n==== Overall summary: {} passed, {} failed ===='.format(total_passed, total_failed)

def finalize_cfgs():
    generate_test_cfg()
    bits.pyfs.add_static("test.cfg", test_cfg)
    for i in range(len(submenus)):
        bits.pyfs.add_static("test.{}.cfg".format(i), test_submenu_cfgs[i])
