/*
Copyright (c) 2011, Intel Corporation
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of Intel Corporation nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

#include <grub/dl.h>
#include <grub/err.h>
#include <grub/misc.h>

#include "portable.h"
#include "datatype.h"
#include "bitsutil.h"

#include "acpi.h"
#include "accommon.h"
#include "acnamesp.h"
#include "amlresrc.h"

#include "acpica.h"

GRUB_MOD_LICENSE("GPLv3+");
GRUB_MOD_DUAL_LICENSE("3-clause BSD");

ACPI_MODULE_NAME("grub2-acpica")

static U32 acpica_early_init_state = 0;
static U32 acpica_init_state = 0;
bool acpica_cpus_initialized = false;
U32 acpica_cpus_init_caps = 0;

/* Stubs to link the ACPICA disassembler */
void
MpSaveGpioInfo (
    ACPI_PARSE_OBJECT       *Op,
    AML_RESOURCE            *Resource,
    UINT32                  PinCount,
    UINT16                  *PinList,
    char                    *DeviceName)
{
    (void)Op;
    (void)Resource;
    (void)PinCount;
    (void)PinList;
    (void)DeviceName;
}

void
MpSaveSerialInfo (
    ACPI_PARSE_OBJECT       *Op,
    AML_RESOURCE            *Resource,
    char                    *DeviceName)
{
    (void)Op;
    (void)Resource;
    (void)DeviceName;
}

bool IsEnabledProcessor(ACPI_HANDLE ObjHandle)
{
    bool ret = false;
    ACPI_DEVICE_INFO *Info;

    if (ACPI_SUCCESS(AcpiGetObjectInfo(ObjHandle, &Info)))
        if ((Info->Type == ACPI_TYPE_PROCESSOR) && (Info->Valid & ACPI_VALID_STA) && (Info->CurrentStatus & ACPI_STA_DEVICE_ENABLED))
            ret = true;
    ACPI_FREE(Info);

    return ret;
}

bool IsEnabledProcessorDev(ACPI_HANDLE ObjHandle)
{
    bool ret = false;
    ACPI_DEVICE_INFO *Info;

    if (ACPI_SUCCESS(AcpiGetObjectInfo(ObjHandle, &Info)))
        if ((Info->Type == ACPI_TYPE_DEVICE) && (Info->Valid & ACPI_VALID_STA) && (Info->CurrentStatus & ACPI_STA_DEVICE_ENABLED) &&
            (Info->Valid & ACPI_VALID_HID) && (grub_strncmp(Info->HardwareId.String, "ACPI0007", Info->HardwareId.Length) == 0))
            ret = true;
    ACPI_FREE(Info);

    return ret;
}

asmlinkage bool acpica_early_init(void)
{
    if (!acpica_early_init_state) {
        if (AcpiInitializeTables(NULL, 0, 0) != AE_OK)
            return false;

        acpica_early_init_state = 1;
    }

    return true;
}

asmlinkage bool acpica_init(void)
{
    ACPI_STATUS err;

    if (!acpica_early_init())
        return false;

    if (acpica_init_state == 1)
        return true;

    err = AcpiInitializeSubsystem();
    if (err != AE_OK) {
        dprintf("acpica", "%s failed with error = %x\n", "AcpiInitializeSubsystem", err);
        return false;
    }

    err = AcpiLoadTables();
    if (err != AE_OK) {
        dprintf("acpica", "%s failed with error = %x\n", "AcpiLoadTables", err);
        return false;
    }

    err = AcpiEnableSubsystem(ACPI_NO_ACPI_ENABLE);
    if (err != AE_OK) {
        dprintf("acpica", "%s failed with error = %x\n", "AcpiEnableSubsystem", err);
        return false;
    }

    err = AcpiInitializeObjects(ACPI_FULL_INITIALIZATION);
    if (err != AE_OK) {
        dprintf("acpica", "%s failed with error = %x\n", "AcpiInitializeObjects", err);
        return false;
    }

    acpica_init_state = 1;

    return true;
}

asmlinkage void acpica_terminate(void)
{
    AcpiTerminate();
    acpica_early_init_state = 0;
    acpica_init_state = 0;
    acpica_cpus_initialized = false;
}

GRUB_MOD_INIT(acpica)
{
    // Bit field that enables/disables debug output from entire subcomponents within the ACPICA subsystem.
    // AcpiDbgLevel = 0;

    // Bit field that enables/disables the various debug output levels
    // AcpiDbgLayer = 0;

    dprintf("acpica", "ACPI_CA_VERSION = %x\n", ACPI_CA_VERSION);
}

GRUB_MOD_FINI(acpica)
{
    AcpiTerminate();
}
