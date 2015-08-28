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

# Docstrings from Python's Modules/socketmodule.c, under the Python license

"""Low-level socket module based on efi"""

from __future__ import print_function
from ctypes import *
import efi
import struct
import time

__all__ = [
    "error", "gaierror", "herror", "timeout",
    "AF_INET",
    "SOCK_STREAM", "SOCK_DGRAM", "SOCK_RAW",
    "IPPROTO_IP", "IPPROTO_TCP", "IPPROTO_UDP",
    "AI_PASSIVE",
    "socket", "SocketType", "has_ipv6",
    "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "gethostname",
    "getprotobyname", "getservbyname", "getservbyport", "getaddrinfo",
    "getnameinfo", "inet_aton", "inet_ntoa",
    "ntohs", "ntohl", "htons", "htonl",
    "getdefaulttimeout", "setdefaulttimeout",
    ]

class error(IOError):
    pass

class gaierror(error):
    pass

class herror(error):
    pass

class timeout(error):
    pass

AF_INET = 2

SOCK_STREAM = 1
SOCK_DGRAM = 2
SOCK_RAW = 3

IPPROTO_IP = 0
IPPROTO_TCP = 6
IPPROTO_UDP = 17

AI_PASSIVE = 0x1

SHUT_RD, SHUT_WR, SHUT_RDWR = range(3)

_configuration_started = False
_initialized = False

def _start_config():
    global _configuration_started, _ip4cp, _tcp4sbp, _done_event, _reconfig_event
    if _configuration_started:
        return

    handles = list(efi.locate_handles(efi.EFI_IP4_CONFIG_PROTOCOL_GUID))
    if not handles:
        raise IOError("EFI_IP4_CONFIG_PROTOCOL not available")
    _ip4cp = efi.EFI_IP4_CONFIG_PROTOCOL.from_handle(handles[0])
    handles = list(efi.locate_handles(efi.EFI_TCP4_SERVICE_BINDING_PROTOCOL_GUID))
    if not handles:
        raise IOError("EFI_TCP4_SERVICE_BINDING_PROTOCOL not available")
    _tcp4sbp = efi.EFI_TCP4_SERVICE_BINDING_PROTOCOL.from_handle(handles[0])

    _done_event = efi.event_signal()
    _reconfig_event = efi.event_signal()
    efi.check_status(_ip4cp.Start(_ip4cp, _done_event.event, _reconfig_event.event))
    print("IP configuration started")
    _configuration_started = True

def _init_sockets():
    global _initialized, _ip4cp, _done_event, _ip_address, _subnet_mask, _routes
    if _initialized:
        return
    _start_config()
    # Spin until configuration complete
    while not _done_event.status:
        pass
    data = efi.EFI_IP4_IPCONFIG_DATA()
    size = efi.UINTN(sizeof(data))
    status = _ip4cp.GetData(_ip4cp, byref(size), byref(data))
    if status == efi.EFI_BUFFER_TOO_SMALL:
        resize(data, size.value)
        status = _ip4cp.GetData(_ip4cp, byref(size), byref(data))
    efi.check_status(status)
    _ip_address = data.StationAddress
    _subnet_mask = data.SubnetMask
    _routes = [efi.EFI_IP4_ROUTE_TABLE.from_buffer_copy(data.RouteTable[i]) for i in range(data.RouteTableSize)]
    print("IP configuration complete: {}/{}".format(data.StationAddress, data.SubnetMask))
    _initialized = True

class socket(object):
    """socket([family[, type[, proto]]]) -> socket object

    Open a socket of the given type.  The family argument specifies the
    address family; it defaults to AF_INET.  The type argument specifies
    whether this is a stream (SOCK_STREAM, this is the default)
    or datagram (SOCK_DGRAM) socket.  The protocol argument defaults to 0,
    specifying the default protocol.  Keyword arguments are accepted.

    A socket object represents one endpoint of a network connection.

    Methods of socket objects (keyword arguments not allowed):

    accept() -- accept a connection, returning new socket and client address
    bind(addr) -- bind the socket to a local address
    close() -- close the socket
    connect(addr) -- connect the socket to a remote address
    connect_ex(addr) -- connect, return an error code instead of an exception
    dup() -- return a new socket object identical to the current one [*]
    fileno() -- return underlying file descriptor
    getpeername() -- return remote address [*]
    getsockname() -- return local address
    getsockopt(level, optname[, buflen]) -- get socket options
    gettimeout() -- return timeout or None
    listen(n) -- start listening for incoming connections
    makefile([mode, [bufsize]]) -- return a file object for the socket [*]
    recv(buflen[, flags]) -- receive data
    recv_into(buffer[, nbytes[, flags]]) -- receive data (into a buffer)
    recvfrom(buflen[, flags]) -- receive data and sender's address
    recvfrom_into(buffer[, nbytes, [, flags])
      -- receive data and sender's address (into a buffer)
    sendall(data[, flags]) -- send all data
    send(data[, flags]) -- send data, may not send all of it
    sendto(data[, flags], addr) -- send data to a given address
    setblocking(0 | 1) -- set or clear the blocking I/O flag
    setsockopt(level, optname, value) -- set socket options
    settimeout(None | float) -- set or clear the timeout
    shutdown(how) -- shut down traffic in one or both directions

     [*] not available on all platforms!"""
    def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0, _handle=None):
        global _default_timeout, _tcp4sbp
        _init_sockets()
        if family != AF_INET:
            raise error("Only AF_INET supported")
        if type != SOCK_STREAM:
            raise error("Only SOCK_STREAM supported")
        if proto != 0 and proto != IPPROTO_TCP:
            raise error("Only default TCP protocol supported")
        self.family = family
        self.type = type
        self.proto = proto
        self.timeout = _default_timeout
        if _handle is None:
            self._tcp4 = _tcp4sbp.child()
        else:
            self._tcp4 = efi.EFI_TCP4_PROTOCOL.from_handle(_handle)

    def __del__(self):
        global _tcp4sbp
        # Only clean up if __init__ finished and we have a protocol to destroy
        if hasattr(self, "_tcp4"):
            efi.check_status(_tcp4sbp.DestroyChild(_tcp4sbp, self._tcp4._handle))

    def __repr__(self):
        return "<socket object, family={}, type={}, proto={}>".format(self.family, self.type, self.proto)

    def _get_config(self):
        tcp4_state = efi.EFI_TCP4_CONNECTION_STATE()
        tcp4_config_data = efi.EFI_TCP4_CONFIG_DATA()
        ip4_mode_data = efi.EFI_IP4_MODE_DATA()
        mnp_config_data = efi.EFI_MANAGED_NETWORK_CONFIG_DATA()
        snp_mode_data = efi.EFI_SIMPLE_NETWORK_MODE()
        efi.check_status(self._tcp4.GetModeData(self._tcp4, byref(tcp4_state), byref(tcp4_config_data), byref(ip4_mode_data), byref(mnp_config_data), byref(snp_mode_data)))
        return tcp4_config_data

    def _wait(self, es, ct):
        """Spin until the specified completion token completes or timeout elapses

        es is an efi.event_signal; ct is a completion token.  If timeout
        elapses, raises socket.timeout.  If the token completes, checks
        ct.Status for errors."""
        if self.timeout < 0.0:
            while not es.status:
                efi.check_status(self._tcp4.Poll(self._tcp4))
        else:
            start = time.time()
            attempt_cancel = True
            while not es.status:
                if attempt_cancel and (time.time() - start >= self.timeout):
                    status = self._tcp4.Cancel(self._tcp4, byref(ct))
                    if status == efi.EFI_NOT_FOUND:
                        pass # Keep waiting for es.status
                    elif status == efi.EFI_UNSUPPORTED:
                        print("Warning: socket timeout expired but EFI can't Cancel; ignoring timeout")
                        attempt_cancel = False
                    else:
                        efi.check_status(status)
                        raise timeout("timed out")
                efi.check_status(self._tcp4.Poll(self._tcp4))
        efi.check_status(ct.Status)

    def accept(self):
        """accept() -> (socket object, address info)

        Wait for an incoming connection.  Return a new socket representing the
        connection, and the address of the client.  For IP sockets, the address
        info is a pair (hostaddr, port)."""
        e = efi.event_signal()
        token = efi.EFI_TCP4_LISTEN_TOKEN()
        token.CompletionToken.Event = e.event
        efi.check_status(self._tcp4.Accept(self._tcp4, byref(token)))
        self._wait(e, token.CompletionToken)
        s = socket(family=self.family, type=self.type, proto=self.proto, _handle=token.NewChildHandle)
        return s, s.getpeername()

    def bind(self, addr):
        """bind(address)

        Bind the socket to a local address.  For IP sockets, the address is a
        pair (host, port); the host must refer to the local host. For raw packet
        sockets the address is a tuple (ifname, proto [,pkttype [,hatype]])"""
        host, port = addr
        ip = efi.EFI_IPv4_ADDRESS.from_buffer_copy(inet_aton(gethostbyname(host)))
        if ip == efi.EFI_IPv4_ADDRESS((255,255,255,255)):
            raise error("Cannot bind to 255.255.255.255")
        self._bind_ip = ip
        self._bind_port = port

    def _close(self, abort=True):
        if hasattr(self, "closed") and self.closed:
            return
        e = efi.event_signal()
        token = efi.EFI_TCP4_CLOSE_TOKEN()
        token.CompletionToken.Event = e.event
        token.AbortOnClose = abort
        efi.check_status(self._tcp4.Close(self._tcp4, byref(token)))
        self._wait(e, token.CompletionToken)
        self.closed = True

    def close(self):
        """"close()

        Close the socket.  It cannot be used after this call."""
        self._close()

    def connect(self, addr):
        """connect(address)

        Connect the socket to a remote address.  For IP sockets, the address
        is a pair (host, port)."""
        global _ip_address, _subnet_mask, _routes
        host, port = addr
        ip = efi.EFI_IPv4_ADDRESS.from_buffer_copy(inet_aton(gethostbyname(host)))
        data = efi.EFI_TCP4_CONFIG_DATA()
        data.TypeOfService = 0
        data.TimeToLive = 60
        # UseDefaultAddress = True fails with EFI_ALREADY_STARTED, but using
        # the previously obtained address works.  The UEFI 2.5 specification
        # does not explain this behavior or document this error code as a
        # possible return from Configure.
        data.AccessPoint.UseDefaultAddress = False
        # Use the local IP and port from bind if set
        try:
            data.AccessPoint.StationAddress = self._bind_ip
            data.AccessPoint.StationPort = self._bind_port
        except AttributeError as e:
            data.AccessPoint.StationAddress = _ip_address
            data.AccessPoint.StationPort = 0
        data.AccessPoint.SubnetMask = _subnet_mask
        data.AccessPoint.RemoteAddress = ip
        data.AccessPoint.RemotePort = port
        data.AccessPoint.ActiveFlag = True
        efi.check_status(self._tcp4.Configure(self._tcp4, byref(data)))

        # Contradicting the UEFI 2.5 specification, the EFI_TCP4_PROTOCOL does
        # not automatically use all of the underlying IP4 routes.  Add them
        # manually, but ignore any failure caused by already having the route.
        for route in _routes:
            status = self._tcp4.Routes(self._tcp4, False, byref(route.SubnetAddress), byref(route.SubnetMask), byref(route.GatewayAddress))
            if status != efi.EFI_ACCESS_DENIED:
                efi.check_status(status)

        e = efi.event_signal()
        token = efi.EFI_TCP4_CONNECTION_TOKEN()
        token.CompletionToken.Event = e.event
        efi.check_status(self._tcp4.Connect(self._tcp4, byref(token)))
        self._wait(e, token.CompletionToken)

    def connect_ex(self, addr):
        """connect_ex(address) -> errno

        This is like connect(address), but returns an error code (the errno value)
        instead of raising an exception when an error occurs."""
        try:
            self.connect(addr)
        except efi.EFIException as e:
            return 5 # EIO
        except timeout as e:
            return 11 # EAGAIN

    def fileno(self):
        """fileno() -> integer

        Return the integer file descriptor of the socket."""
        raise NotImplementedError("socket.fileno() not supported")

    def getpeername(self):
        """getpeername() -> address info

        Return the address of the remote endpoint.  For IP sockets, the address
        info is a pair (hostaddr, port)."""
        config = self._get_config()
        return str(config.AccessPoint.RemoteAddress), config.AccessPoint.RemotePort

    def getsockname(self):
        """getsockname() -> address info

        Return the address of the local endpoint.  For IP sockets, the address
        info is a pair (hostaddr, port)."""
        config = self._get_config()
        return str(config.AccessPoint.StationAddress), config.AccessPoint.StationPort

    def getsockopt(self, level, option, buffersize=0):
        """getsockopt(level, option[, buffersize]) -> value

        Get a socket option.  See the Unix manual for level and option.
        If a nonzero buffersize argument is given, the return value is a
        string of that length; otherwise it is an integer."""
        raise error("socket.getsockopt not supported")

    def listen(self, backlog):
        """listen(backlog)

        Enable a server to accept connections.  The backlog argument must be at
        least 0 (if it is lower, it is set to 0); it specifies the number of
        unaccepted connections that the system will allow before refusing new
        connections."""
        # FIXME: Use queue depth as MaxSynBackLog
        global _subnet_mask, _routes
        if backlog < 0:
            backlog = 0
        data = efi.EFI_TCP4_CONFIG_DATA()
        data.TypeOfService = 0
        data.TimeToLive = 60
        # UseDefaultAddress = True fails with EFI_ALREADY_STARTED, but using
        # the previously obtained address works.  The UEFI 2.5 specification
        # does not explain this behavior or document this error code as a
        # possible return from Configure.
        data.AccessPoint.UseDefaultAddress = False
        # Use the local IP and port from bind if set
        try:
            # Special-case 0.0.0.0 because the EFI IP stack doesn't handle it
            if self._bind_ip == efi.EFI_IPv4_ADDRESS((0,0,0,0)):
                data.AccessPoint.StationAddress = _ip_address
            else:
                data.AccessPoint.StationAddress = self._bind_ip
            data.AccessPoint.StationPort = self._bind_port
        except AttributeError as e:
            data.AccessPoint.StationAddress = _ip_address
            data.AccessPoint.StationPort = 0
        data.AccessPoint.SubnetMask = _subnet_mask
        data.AccessPoint.ActiveFlag = False
        efi.check_status(self._tcp4.Configure(self._tcp4, byref(data)))

        # Contradicting the UEFI 2.5 specification, the EFI_TCP4_PROTOCOL does
        # not automatically use all of the underlying IP4 routes.  Add them
        # manually, but ignore any failure caused by already having the route.
        for route in _routes:
            status = self._tcp4.Routes(self._tcp4, False, byref(route.SubnetAddress), byref(route.SubnetMask), byref(route.GatewayAddress))
            if status != efi.EFI_ACCESS_DENIED:
                efi.check_status(status)

    def recv(self, buflen, flags=0):
        """recv(buffersize[, flags]) -> data

        Receive up to buffersize bytes from the socket.  For the optional flags
        argument, see the Unix manual.  When no data is available, block until
        at least one byte is available or until the remote end is closed.  When
        the remote end is closed and all data is read, return the empty string."""
        buf = create_string_buffer(0)
        resize(buf, buflen)
        nbytes_read = self.recv_into(buf, buflen, flags)
        resize(buf, nbytes_read)
        return buf.raw

    def recv_into(self, buffer, nbytes=0, flags=0):
        """recv_into(buffer, [nbytes[, flags]]) -> nbytes_read

        A version of recv() that stores its data into a buffer rather than creating
        a new string.  Receive up to buffersize bytes from the socket.  If buffersize
        is not specified (or 0), receive up to the size available in the given buffer.

        See recv() for documentation about the flags."""
        if nbytes == 0:
            # len returns the wrong thing for a resized ctypes buffer. But
            # ctypes.sizeof doesn't work on all buffery objects that len does.
            # So try both, in order of preference.
            try:
                nbytes = sizeof(buffer)
            except TypeError as e:
                nbytes = len(buffer)
        cbuf = (c_uint8 * nbytes).from_buffer(buffer)
        rx = efi.EFI_TCP4_RECEIVE_DATA()
        rx.DataLength = nbytes
        rx.FragmentCount = 1
        rx.FragmentTable[0].FragmentLength = nbytes
        rx.FragmentTable[0].FragmentBuffer = addressof(cbuf)
        e = efi.event_signal()
        token = efi.EFI_TCP4_IO_TOKEN()
        token.CompletionToken.Event = e.event
        token.Packet.RxData = pointer(rx)
        efi.check_status(self._tcp4.Receive(self._tcp4, byref(token)))
        self._wait(e, token.CompletionToken)
        return rx.DataLength

    def recvfrom(self, buffersize, flags=0):
        """recvfrom(buffersize[, flags]) -> (data, address info)

        Like recv(buffersize, flags) but also return the sender's address info."""
        return self.recv(buffersize, flags), self.getpeername()

    def recvfrom_into(self, buffer, nbytes=0, flags=0):
        """recvfrom_into(buffer[, nbytes[, flags]]) -> (nbytes, address info)

        Like recv_into(buffer[, nbytes[, flags]]) but also return the sender's address info."""
        return self.recv_into(buffer, nbytes, flags), self.getpeername()

    def sendall(self, data, flags=0):
        """sendall(data[, flags])

        Send a data string to the socket.  For the optional flags
        argument, see the Unix manual.  This calls send() repeatedly
        until all data is sent.  If an error occurs, it's impossible
        to tell how much data has been sent."""
        tx = efi.EFI_TCP4_TRANSMIT_DATA()
        tx.DataLength = len(data)
        tx.FragmentCount = 1
        tx.FragmentTable[0].FragmentLength = len(data)
        if isinstance(data, memoryview):
            data = data.tobytes()
        ptr = c_char_p(data)
        tx.FragmentTable[0].FragmentBuffer = cast(ptr, c_void_p)
        e = efi.event_signal()
        token = efi.EFI_TCP4_IO_TOKEN()
        token.CompletionToken.Event = e.event
        token.Packet.TxData = pointer(tx)
        efi.check_status(self._tcp4.Transmit(self._tcp4, byref(token)))
        self._wait(e, token.CompletionToken)

    def send(self, data, flags=0):
        """send(data[, flags]) -> count

        Send a data string to the socket.  For the optional flags
        argument, see the Unix manual.  Return the number of bytes
        sent; this may be less than len(data) if the network is busy."""
        self.sendall(data, flags)
        return len(data)

    def sendto(self, data, flags, address=None):
        """sendto(data[, flags], address) -> count

        Like send(data, flags) but allows specifying the destination address.
        For IP sockets, the address is a pair (hostaddr, port)."""
        if address is None:
            address = flags
            flags = 0
        self.send(data, flags)

    def shutdown(self, how):
        """"shutdown(flag)

        Shut down the reading side of the socket (flag == SHUT_RD), the writing side
        of the socket (flag == SHUT_WR), or both ends (flag == SHUT_RDWR)."""
        if how == SHUT_RDWR:
            self._close(abort=False)
        else:
            raise error("socket.shutdown(how={}) not supported".format(how))

    def gettimeout(self):
        """gettimeout() -> timeout

        Returns the timeout in seconds (float) associated with socket
        operations. A timeout of None indicates that timeouts on socket
        operations are disabled."""
        return _timeout_internal_to_external(self.timeout)

    def setblocking(self, flag):
        """setblocking(flag)

        Set the socket to blocking (flag is true) or non-blocking (false).
        setblocking(True) is equivalent to settimeout(None);
        setblocking(False) is equivalent to settimeout(0.0)."""
        if flag:
            self.timeout = -1.0
        else:
            self.timeout = 0.0

    def setsockopt(self, level, option, value):
        """setsockopt(level, option, value)

        Set a socket option.  See the Unix manual for level and option.
        The value argument can either be an integer or a string."""
        raise error("socket.setsockopt not supported")

    def settimeout(self, timeout):
        """settimeout(timeout)

        Set a timeout on socket operations.  'timeout' can be a float,
        giving in seconds, or None.  Setting a timeout of None disables
        the timeout feature and is equivalent to setblocking(1).
        Setting a timeout of zero is the same as setblocking(0)."""
        self.timeout = _timeout_external_to_internal(timeout)

SocketType = socket

has_ipv6 = False

# fromfd not supported

def _is_ip(ip):
    try:
        a, b, c, d = map(int, ip.split(".", 3))
        return a >= 0 and a <= 255 and b >= 0 and b <= 255 and c >= 0 and c <= 255 and d >= 0 and d <= 255
    except ValueError as e:
        return False

def gethostbyname(hostname):
    """gethostbyname(host) -> address

    Return the IP address (a string of the form '255.255.255.255') for a
    host."""
    if hostname == "":
        return "0.0.0.0"
    if hostname == "<broadcast>":
        return "255.255.255.255"
    if hostname == "localhost":
        return "127.0.0.1"
    if _is_ip(hostname):
        return hostname
    raise gaierror("DNS not supported")

def gethostbyname_ex(hostname):
    if hostname == "localhost":
        return ("localhost", [], ["127.0.0.1"])
    if _is_ip(hostname):
        return (hostname, [], [hostname])
    raise gaierror("DNS not supported")

def gethostbyaddr(ip):
    """gethostbyaddr(ip) -> (name, aliaslist, addresslist)

    Return the true host name, a list of aliases, and a list of IP addresses,
    for a host.  The host argument is a string giving a host name or IP
    number."""
    if ip == "127.0.0.1":
        return ("localhost", [], ["127.0.0.1"])
    raise herror("Reverse DNS not supported")

def gethostname():
    """gethostname() -> string

    Return the current host name."""
    return "localhost"

def getprotobyname(name):
    """getprotobyname(name) -> integer

    Return the protocol number for the named protocol.  (Rarely used.)"""
    raise error("protocol not found")

def getservbyname(servicename, protocolname=None):
    """getservbyname(servicename[, protocolname]) -> integer

    Return a port number from a service name and protocol name.  The optional
    protocol name, if given, should be 'tcp' or 'udp', otherwise any protocol
    will match."""
    raise error("service/proto not found")

def getservbyport(port, protocolname=None):
    """getservbyport(port[, protocolname]) -> string

    Return the service name from a port number and protocol name.
    The optional protocol name, if given, should be 'tcp' or 'udp',
    otherwise any protocol will match."""
    if port < 0 or port > 0xffff:
        raise OverflowError("getservbyport: port must be 0-65535")
    raise error("port/proto not found")

def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
    """getaddrinfo(host, port [, family, socktype, proto, flags])
        -> list of (family, socktype, proto, canonname, sockaddr)

    Resolve host and port into addrinfo struct."""
    if flags & AI_PASSIVE:
        if host is None:
            host = "0.0.0.0"
    if host is None or host == "localhost":
        host = "127.0.0.1"
    elif not _is_ip(host):
        raise gaierror("DNS not supported")
    return [(AF_INET, SOCK_STREAM, IPPROTO_TCP, "", (host, port))]

def getnameinfo(sockaddr, flags):
    """getnameinfo(sockaddr, flags) --> (host, port)

    Get host and port for a sockaddr."""
    host, port = sockaddr
    return gethostbyaddr(host), getservbyport(port)

def inet_aton(string):
    """inet_aton(string) -> packed 32-bit IP representation

    Convert an IP address in string format (123.45.67.89) to the 32-bit packed
    binary format used in low-level network functions."""
    a, b, c, d = map(int, string.split(".", 3))
    return struct.pack("BBBB", a, b, c, d)

def inet_ntoa(packed_ip):
    """inet_ntoa(packed_ip) -> ip_address_string

    Convert an IP address from 32-bit packed binary format to string format"""
    return "{}.{}.{}.{}".format(*struct.unpack("BBBB", packed_ip))

# inet_pton not supported
# inet_ntop not supported
# socketpair not supported

def ntohs(integer):
    """ntohs(integer) -> integer

    Convert a 16-bit integer from network to host byte order."""
    return struct.unpack("=H", struct.pack("!H", integer))[0]

def ntohl(integer):
    """ntohl(integer) -> integer

    Convert a 32-bit integer from network to host byte order."""
    return struct.unpack("=I", struct.pack("!I", integer))[0]

def htons(integer):
    """htons(integer) -> integer

    Convert a 16-bit integer from host to network byte order."""
    return struct.unpack("!H", struct.pack("=H", integer))[0]

def htonl(integer):
    """htonl(integer) -> integer

    Convert a 32-bit integer from host to network byte order."""
    return struct.unpack("!I", struct.pack("=I", integer))[0]

_default_timeout = -1.0

def _timeout_internal_to_external(timeout):
    if timeout < 0.0:
        return None
    return timeout

def _timeout_external_to_internal(timeout):
    if timeout is None:
        return -1.0
    else:
        timeout = float(timeout)
        if timeout < 0.0:
            raise ValueError("Timeout value out of range")
        return timeout

def getdefaulttimeout():
    """getdefaulttimeout() -> timeout

    Returns the default timeout in seconds (float) for new socket objects.
    A value of None indicates that new socket objects have no timeout.
    When the socket module is first imported, the default is None."""
    global _default_timeout
    return _timeout_internal_to_external(_default_timeout)

def setdefaulttimeout(timeout):
    """setdefaulttimeout(timeout)

    Set the default timeout in seconds (float) for new socket objects.
    A value of None indicates that new socket objects have no timeout.
    When the socket module is first imported, the default is None."""
    global _default_timeout
    _default_timeout = _timeout_external_to_internal(timeout)
