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

"""Error Injection EINJ module."""

from __future__ import print_function
import acpi
import bits
import contextlib
from cpudetect import cpulib
import ctypes
import functools
import ttypager

# Create constants for each value in these dictionaries for readability.  These
# names are too generic to put in the acpi module's namespace, but they make
# sense in the einj module.
globals().update(map(reversed, acpi._error_injection_action.iteritems()))
globals().update(map(reversed, acpi._error_injection_instruction.iteritems()))

read_mem = {
    1: bits.readb,
    2: bits.readw,
    3: bits.readl,
    4: bits.readq,
}

write_mem = {
    1: bits.writeb,
    2: bits.writew,
    3: bits.writel,
    4: bits.writeq,
}

out_port = {
    1: bits.outb,
    2: bits.outw,
    3: bits.outl,
}

error_injection_command_status = {
    0x0: 'SUCCESS',
    0x1: 'UNKNOWN_FAILURE',
    0x2: 'INVALID_ACCESS',
}
globals().update(map(reversed, error_injection_command_status.iteritems()))

# List of actions that can be executed with no custom processing
_action_simple = [
    BEGIN_INJECTION_OPERATION,
    END_OPERATION,
    EXECUTE_OPERATION,
    CHECK_BUSY_STATUS,
    GET_COMMAND_STATUS,
]

def _execute_action(entry, value=None):
    print("entry.injection_action = {:#x} ({})".format(entry.injection_action, acpi._error_injection_action.get(entry.injection_action, "Unknown")))
    if entry.injection_action in _action_simple:
        return _execute_instruction(entry)
    elif entry.injection_action == GET_TRIGGER_ERROR_ACTION_TABLE:
        return acpi.trigger_error_action(_execute_instruction(entry))
    elif entry.injection_action == SET_ERROR_TYPE:
        if value is None:
            raise ValueError("action SET_ERROR_TYPE but no input parameter provided")
        return _execute_instruction(entry, value.data)
    elif entry.injection_action == GET_ERROR_TYPE:
        _execute_instruction(entry)
        return acpi.error_type_flags.from_address(entry.register_region.address)
    elif entry.injection_action == SET_ERROR_TYPE_WITH_ADDRESS:
        if value is None:
            raise ValueError("action SET_ERROR_TYPE_WITH_ADDRESS but no input paramters provided")
        error_type = value[0]
        if error_type.processor_correctable or error_type.processor_uncorrectable_non_fatal or error_type.processor_uncorrectable_fatal:
            error_type, flags, apicid = value
            cpu_error = acpi.set_error_type_with_addr.from_address(entry.register_region.address)
            if cpu_error.error_type.vendor_defined and cpu_error.vendor_error_type_extension_structure_offset:
                vendor_err_addr = entry.register_region.address + cpu_error.vendor_error_type_extension_structure_offset
                vendor_error_type_extension = acpi.set_error_type_with_addr.from_address(vendor_err_addr)
                print(vendor_error_type_extension)
            print('WRITE_REGISTER SET_ERROR_TYPE_WITH_ADDRESS address - {0:#x}'.format(entry.register_region.address))
            cpu_error.error_type = error_type
            cpu_error.flags = flags
            cpu_error.apicid = apicid
            print(cpu_error)
        elif error_type.memory_correctable or error_type.memory_uncorrectable_non_fatal or error_type.memory_uncorrectable_fatal:
            error_type, flags, mem_addr, mem_addr_range = value
            mem_error = acpi.set_error_type_with_addr.from_address(entry.register_region.address)
            print('WRITE_REGISTER SET_ERROR_TYPE_WITH_ADDRESS address - {0:#x}'.format(entry.register_region.address))
            mem_error.error_type = error_type
            mem_error.flags = flags
            mem_error.memory_address = mem_addr
            mem_error.memory_address_range = mem_addr_range
            print(mem_error)
        elif error_type.pci_express_correctable or error_type.pci_express_uncorrectable_non_fatal or error_type.pci_express_uncorrectable_fatal:
            error_type, flags, segment, bus, device, function = value
            pcie_error = acpi.set_error_type_with_addr.from_address(entry.register_region.address)
            print('WRITE_REGISTER SET_ERROR_TYPE_WITH_ADDRESS address - {0:#x}'.format(entry.register_region.address))
            pcie_error.error_type = error_type
            pcie_error.flags = flags
            pcie_error.pcie_sbdf.bits.function_num = function
            pcie_error.pcie_sbdf.bits.device_num = device
            pcie_error.pcie_sbdf.bits.bus_num = bus
            pcie_error.pcie_sbdf.bits.pcie_segment = segment
            print(pcie_error)
        else:
            raise ValueError("action SET_ERROR_TYPE_WITH_ADDRESS has unsupported error_type {}".format(error_type))
    elif entry.injection_action == TRIGGER_ERROR:
        # Execute the actions specified in the trigger action table.
        trigger_table = get_trigger_action_table_op()
        for entry in trigger_table.entries:
            _execute_instruction(entry)
    else:
        raise ValueError("action is unsupported")

def _execute_instruction(entry, value=None):
    print("entry.instruction = {:#x} ({})".format(entry.instruction, acpi._error_injection_instruction.get(entry.instruction, "Unknown")))
    if entry.instruction is READ_REGISTER:
        return _read_register(entry)
    elif entry.instruction is READ_REGISTER_VALUE:
        return _read_register_value(entry)
    elif entry.instruction is WRITE_REGISTER_VALUE:
        return _write_register(entry)
    elif entry.instruction is WRITE_REGISTER:
        return _write_register(entry, value)
    elif entry.instruction is NOOP:
        return None

def _read_register(entry):
    if entry.register_region.address_space_id == acpi.ASID_SYSTEM_MEMORY:
        print('READ_REGISTER address - {:#x}'.format(entry.register_region.address))
        value = read_mem[entry.register_region.access_size](entry.register_region.address)
        value = value >> entry.register_region.register_bit_offset
        value = value & entry.mask
        print('READ_REGISTER value   - {:#x}'.format(value))
        return value
    return None

def _read_register_value(entry):
    read_value = _read_register(entry)
    read_value = read_value >> entry.register_region.register_bit_offset
    read_value = read_value & entry.mask
    print('entry.value - {:#x}'.format(entry.value))
    return read_value == entry.value

def _write_register(entry, value=None):
    if not value:
        value = entry.value
    if entry.register_region.address_space_id == acpi.ASID_SYSTEM_MEMORY:
        print('WRITE_REGISTER address      - {:#x}'.format(entry.register_region.address))
        read_value = read_mem[entry.register_region.access_size](entry.register_region.address)
        print('WRITE_REGISTER before value - {:#x}'.format(read_value))
        if entry.flags.bits.preserve_register:
            read_value = read_value & ~(entry.mask << entry.register_region.register_bit_offset)
        value = value | read_value
        write_mem[entry.register_region.access_size](entry.register_region.address, value)
        read_value = read_mem[entry.register_region.access_size](entry.register_region.address)
        print('WRITE_REGISTER after value  - {:#x}'.format(read_value))
    elif entry.register_region.address_space_id == acpi.ASID_SYSTEM_IO:
        print('WRITE_REGISTER_VALUE IO address     - {:#x}'.format(entry.register_region.address))
        print('WRITE_REGISTER_VALUE value to write - {:#x}'.format(entry.value))
        out_port[entry.register_region.access_size](entry.register_region.address, value)
    else:
        raise ValueError("Unsupported address_space_id: {}".format(entry.register_region.address_space_id))

def _write_register_value(entry, value):
    _write_register(entry, value)

def get_action(action):
    einj = acpi.parse_einj()
    if einj is None:
        raise RuntimeError("No ACPI EINJ table found")
    for entry in einj.entries:
        if entry.injection_action == action:
            return entry

def get_and_execute_op(action, value=None):
    entry = get_action(action)
    if entry is None:
        print('Error: Unexpected Action')
        return
    return _execute_action(entry, value)

def begin_inject_op():
    return get_and_execute_op(BEGIN_INJECTION_OPERATION)

def get_trigger_action_table_op():
    return get_and_execute_op(GET_TRIGGER_ERROR_ACTION_TABLE)

def set_error_type_op(error_type):
    return get_and_execute_op(SET_ERROR_TYPE, error_type)

def get_error_type_op():
    return get_and_execute_op(GET_ERROR_TYPE)

def end_inject_op():
    return get_and_execute_op(END_OPERATION)

def execute_inject_op():
    return get_and_execute_op(EXECUTE_OPERATION)

def _execute_trigger_error_op():
    # Create an Trigger Error action to execute
    entry = acpi.InjectionInstructionEntry()
    entry.injection_action = TRIGGER_ERROR
    return _execute_action(entry)

def check_busy_status_op():
    busy_status = get_and_execute_op(CHECK_BUSY_STATUS)
    print('busy_status = {}'.format('Busy' if busy_status else 'Not Busy'))
    return busy_status

def get_cmd_status_op():
    cmd_status = get_and_execute_op(GET_COMMAND_STATUS)
    print('cmd_status = {:#x} ({})'.format(cmd_status, error_injection_command_status.get(cmd_status, 'Unknown')))
    return cmd_status

# This routine is specific to setting a memory error
def _set_error_type_with_addr_op_mem(error_type, flags, mem_addr=None, mem_addr_range=None):
    return get_and_execute_op(SET_ERROR_TYPE_WITH_ADDRESS, (error_type, flags, mem_addr, mem_addr_range))

# This routine is specific to setting a processor error
def _set_error_type_with_addr_op_cpu(error_type, flags, apicid=None):
    return get_and_execute_op(SET_ERROR_TYPE_WITH_ADDRESS, (error_type, flags, apicid))

# This routine is specific to setting a PCIE error
def _set_error_type_with_addr_op_pcie(error_type, flags, segment=None, bus=None, device=None, function=None):
    return get_and_execute_op(SET_ERROR_TYPE_WITH_ADDRESS, (error_type, flags, (segment, bus, device, function)))

def einj_cpu_init():
    """Return the error injection cpu init method.

    Returns the cpu-specific method if available, otherwise default.
    Computed on first call, and cached for subsequent return."""
    global einj_cpu_init

    @contextlib.contextmanager
    def default_cpu_init():
        yield

    try:
        local_einj_cpu_init = cpulib.quirk_einj_cpu_init
        print("QUIRK: Setting processor-specific error injection init")
    except AttributeError:
        local_einj_cpu_init = default_cpu_init

    old_func = einj_cpu_init
    def einj_cpu_init():
        return local_einj_cpu_init()
    functools.update_wrapper(einj_cpu_init, old_func)

    return local_einj_cpu_init()

@contextlib.contextmanager
def _error_injection_op():
    with einj_cpu_init():
        begin_inject_op()
        yield
        execute_inject_op()
        while check_busy_status_op():
            continue
        cmd_status = get_cmd_status_op()
        if cmd_status != SUCCESS:
            return
        _execute_trigger_error_op()
        end_inject_op()

@contextlib.contextmanager
def _inject_memory_error(address=None, mask=None):
    # Constructor creates a structure with all zero init
    error_type = acpi.error_type_flags()
    yield error_type
    if (address is not None) and (mask is not None):
        # Constructor creates a structure with all zero init
        flags = acpi.set_error_type_with_addr_flags()
        flags.memory_addr_and_mask_valid = 1
        _set_error_type_with_addr_op_mem(error_type, flags, address, mask)
    else:
        set_error_type_op(error_type)

def inject_memory_correctable_err(address=None, mask=None):
    """ Inject memory correctable error.

    If address and mask are provided, then SET_ERROR_TYPE_WITH_ADDRESS
    Error Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().memory_correctable == 0:
        print('Memory Correctable error injection is not supported')
        return
    with _error_injection_op():
        with _inject_memory_error(address, mask) as error_type:
            error_type.memory_correctable = 1

def inject_memory_unc_nonfatal_err(address=None, mask=None):
    """Inject memory uncorrectable non-fatal error.

    If address and mask are provided, then SET_ERROR_TYPE_WITH_ADDRESS
    Error Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().memory_uncorrectable_non_fatal == 0:
        print('Memory Uncorrectable non-Fatal error injection is not supported')
        return
    with _error_injection_op():
        with _inject_memory_error(address, mask) as error_type:
            error_type.memory_uncorrectable_non_fatal = 1

def inject_memory_unc_fatal_err(address=None, mask=None):
    """Inject memory uncorrectable fatal error.

    If address and mask are provided, then SET_ERROR_TYPE_WITH_ADDRESS
    Error Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().memory_uncorrectable_fatal == 0:
        print('Memory Uncorrectable Fatal error injection is not supported')
        return
    with _error_injection_op():
        with _inject_memory_error(address, mask) as error_type:
            error_type.memory_uncorrectable_fatal = 1

@contextlib.contextmanager
def _inject_processor_error(apicid=None):
    # Constructor creates a structure with all zero init
    error_type = acpi.error_type_flags()
    yield error_type
    if apicid is not None:
        # Constructor creates a structure with all zero init
        flags = acpi.set_error_type_with_addr_flags()
        flags.processor_apic_valid = 1
        _set_error_type_with_addr_op_cpu(error_type, flags, apicid)
    else:
        set_error_type_op(error_type)

def inject_processor_correctable_err(apicid=None):
    """ Inject processor correctable error.

    If apicid is provided, then SET_ERROR_TYPE_WITH_ADDRESS Error
    Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().processor_correctable == 0:
        print('Processor Correctable error injection is not supported')
        return
    with _error_injection_op():
        with _inject_processor_error(apicid) as error_type:
            error_type.processor_correctable = 1

def inject_processor_unc_nonfatal_err(apicid=None):
    """Inject processor uncorrectable non-fatal error.

    If apicid is provided, then SET_ERROR_TYPE_WITH_ADDRESS Error
    Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().processor_uncorrectable_non_fatal == 0:
        print('Processor Uncorrectable non-Fatal error injection is not supported')
        return

    with _error_injection_op():
        with _inject_processor_error(apicid) as error_type:
            error_type.processor_uncorrectable_non_fatal = 1

def inject_processor_unc_fatal_err(address=None, mask=None):
    """Inject PCIE uncorrectable fatal error.

    If apicid is provided, then SET_ERROR_TYPE_WITH_ADDRESS Error
    Injection Action is used. Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().processor_uncorrectable_fatal == 0:
        print('Processor Uncorrectable Fatal error injection is not supported')
        return
    with _error_injection_op():
        with _inject_processor_error(apicid) as error_type:
            error_type.processor_uncorrectable_fatal = 1

@contextlib.contextmanager
def _inject_pcie_error(segment=None, bus=None, device=None, function=None):
    # Constructor creates a structure with all zero init
    error_type = acpi.error_type_flags()
    yield error_type
    if all(x is not None for x in (segment, bus, device, function)):
        # Constructor creates a structure with all zero init
        flags = acpi.set_error_type_with_addr_flags()
        flags.pcie_sbdf_valid = 1
        _set_error_type_with_addr_op_pcie(error_type, flags, segment, bus, device, function)
    else:
        set_error_type_op(error_type)

def inject_pcie_correctable_err(segment=None, bus=None, device=None, function=None):
    """ Inject PCIE correctable error.

    If segment, bus, device and function are provided, then
    SET_ERROR_TYPE_WITH_ADDRESS Error Injection Action is used.
    Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().pci_express_correctable == 0:
        print('PCI Express Correctable error injection is not supported')
        return
    with _error_injection_op():
        with _inject_pcie_error(segment=None, bus=None, device=None, function=None) as error_type:
            error_type.pcie_express_correctable = 1

def inject_pcie_unc_nonfatal_err(segment=None, bus=None, device=None, function=None):
    """Inject PCIE uncorrectable non-fatal error.

    If segment, bus, device and function are provided, then
    SET_ERROR_TYPE_WITH_ADDRESS Error Injection Action is used.
    Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().processor_uncorrectable_non_fatal == 0:
        print('PCI Express Uncorrectable non-Fatal error injection is not supported')
        return

    with _error_injection_op():
        with _inject_pcie_error(segment=None, bus=None, device=None, function=None) as error_type:
            error_type.pci_expresss_uncorrectable_non_fatal = 1

def inject_pcie_unc_fatal_err(segment=None, bus=None, device=None, function=None):
    """Inject PCIE uncorrectable fatal error.

    If segment, bus, device and function are provided, then
    SET_ERROR_TYPE_WITH_ADDRESS Error Injection Action is used.
    Otherwise, SET_ERROR_TYPE is used."""

    if get_error_type_op().pci_express_uncorrectable_fatal == 0:
        print('PCIE Uncorrectable Fatal error injection is not supported')
        return
    with _error_injection_op():
        with _inject_pcie_error(segment=None, bus=None, device=None, function=None) as error_type:
            error_type.processor_uncorrectable_fatal = 1

def _inject_platform_error():
    # Constructor creates a structure with all zero init
    error_type = acpi.error_type_flags()
    yield error_type
    set_error_type_op(error_type)

def inject_platform_correctable_err():
    """ Inject platform correctable error."""

    if get_error_type_op().platform_correctable == 0:
        print('Platform Correctable error injection is not supported')
        return
    with _error_injection_op():
        with _inject_platform_error() as error_type:
            error_type.platform_correctable = 1

def inject_platform_unc_nonfatal_err():
    """Inject platform uncorrectable non-fatal error."""

    if get_error_type_op().platform_uncorrectable_non_fatal == 0:
        print('Platform Uncorrectable non-Fatal error injection is not supported')
        return

    with _error_injection_op():
        with _inject_platform_error() as error_type:
            error_type.platform_uncorrectable_non_fatal = 1

def inject_platform_unc_fatal_err():
    """Inject platform uncorrectable fatal error."""

    if get_error_type_op().platform_uncorrectable_fatal == 0:
        print('Platform Uncorrectable Fatal error injection is not supported')
        return
    with _error_injection_op():
        with _inject_platform_error() as error_type:
            error_type.platform_uncorrectable_fatal = 1

def display_einj_address():
    address = acpi.get_table_addr("EINJ", 0)
    if address is not None:
        print('EINJ address {0:#x}'.format(address))

def display_supported_errors():
    print(get_error_type_op())

def display_triggers():
    with ttypager.page():
        print(get_trigger_action_table_op())

def display_vendor_error_type_extension():
    with ttypager.page():
        entry = get_action(SET_ERROR_TYPE_WITH_ADDRESS)
        set_err = acpi.set_error_type_with_addr.from_address(entry.register_region.address)
        vendor_err_addr = entry.register_region.address + set_err.vendor_error_type_extension_structure_offset
        vendor_err = acpi.vendor_error_type_extension.from_address(vendor_err_addr)
        print(vendor_err)

def display_einj():
    with ttypager.page():
        einj = acpi.parse_einj()
        if einj is None:
            raise RuntimeError("No ACPI EINJ table found")
        print(einj)

def demo():
    unc_methods = [
        inject_memory_unc_nonfatal_err,
        inject_memory_unc_fatal_err,
        inject_processor_unc_nonfatal_err,
        inject_processor_unc_fatal_err,
        inject_pcie_unc_nonfatal_err,
        inject_pcie_unc_fatal_err,
        inject_platform_unc_nonfatal_err,
        inject_platform_unc_fatal_err,
    ]
    corr_methods = [
        inject_memory_correctable_err,
        inject_processor_correctable_err,
        inject_pcie_correctable_err,
        inject_platform_correctable_err,
    ]
    display_methods = [
        display_einj,
        display_einj_address,
        display_supported_errors,
        display_triggers,
        display_vendor_error_type_extension,
    ]

    with ttypager.page():
        for item in display_methods:
            print("\n\n\nMethod name: {}".format(item.__name__))
            print("Method doc:\n{}\n\n".format(item.__doc__ if item.__doc__ else "No documentation for this method"))
            item()

        for item in corr_methods:
            print("\n\nMethod name: {}".format(item.__name__))
            print("Method doc: {}".format(item.__doc__ if item.__doc__ else "No documentation for this method"))
            item()

        for item in unc_methods:
            print("\n\n\nMethod name: {}".format(item.__name__))
            print("Method doc: {}\n\n".format(item.__doc__ if item.__doc__ else "No documentation for this method"))
            print("Based on the name and documentation of this item, it is likely to be fatal.")
            print("Execute it directly from the python command line.")
            print("Your mileage may vary and if it breaks, you get to keep all the pieces.")
