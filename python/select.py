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

# Docstrings from Python's select module, under the Python license

"""select module for EFI-based sockets"""

import errno
import _socket
import time

class error(Exception):
    pass

def select(rlist, wlist, xlist, timeout=None):
    """select(rlist, wlist, xlist[, timeout]) -> (rlist, wlist, xlist)

    Wait until one or more sockets are ready for some kind of I/O.
    The first three arguments are sequences of file descriptors to be waited for:
    rlist -- wait until ready for reading
    wlist -- wait until ready for writing
    xlist -- wait for an ``exceptional condition''
    If only one kind of condition is required, pass [] for the other lists.
    A file descriptor is either a socket object or the value gotten from a
    fileno() method call on a socket object.

    The optional 4th argument specifies a timeout in seconds; it may be
    a floating point number to specify fractions of seconds.  If it is absent
    or None, the call will never time out.

    The return value is a tuple of three lists corresponding to the first three
    arguments; each contains the subset of the corresponding file descriptors
    that are ready."""
    if timeout is not None and timeout < 0:
        raise error(errno.EINVAL, "timeout must not be negative")
    if xlist:
        raise error(errno.EINVAL, "xlist not supported")
    start = time.time()
    rlist_ret = []
    wlist_ret = []
    # do-while loop, to go through the sockets once for timeout == 0
    while True:
        for fd in rlist:
            s = _socket._to_socket(fd)
            if s._read_ready():
                rlist_ret.append(fd)
        for fd in wlist:
            s = _socket._to_socket(fd)
            if s._write_ready():
                wlist_ret.append(fd)
        if rlist_ret or wlist_ret:
            break
        if timeout is not None and (time.time() - start >= timeout):
            break
    return rlist_ret, wlist_ret, []
