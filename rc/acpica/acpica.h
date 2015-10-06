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

#ifndef ACPICA_H
#define ACPICA_H

#include <grub/err.h>

#include "portable.h"
#include "datatype.h"

#pragma GCC diagnostic ignored "-Wunused-parameter"
#include "acpi.h"
#include "accommon.h"
#include "acnamesp.h"
#include "amlresrc.h"
#pragma GCC diagnostic error "-Wunused-parameter"

extern bool acpica_cpus_initialized;
extern U32 acpica_cpus_init_caps;

asmlinkage bool acpica_early_init(void);
extern asmlinkage ACPI_STATUS (*AcpiOsReadPort_ptr)(ACPI_IO_ADDRESS Address, UINT32 *Value, UINT32 Width);
extern asmlinkage ACPI_STATUS (*AcpiOsWritePort_ptr)(ACPI_IO_ADDRESS Address, UINT32 Value, UINT32 Width);
asmlinkage bool acpica_init(void);
asmlinkage void acpica_terminate(void);
bool IsEnabledProcessor(ACPI_HANDLE ObjHandle);
bool IsEnabledProcessorDev(ACPI_HANDLE ObjHandle);

#endif
