/*
Copyright (c) 2010, Intel Corporation
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

#ifndef MCU_H
#define MCU_H

#include "datatype.h"

#ifndef signature_defined
#define signature_defined
#define SIGNATURE(s) (((U32)(s[3]) << 0)  \
                     |((U32)(s[2]) << 8)  \
                     |((U32)(s[1]) << 16) \
                     |((U32)(s[0]) << 24))
#endif

#ifndef UPDATE_INFO_TYPEDEF
#define UPDATE_INFO_TYPEDEF
typedef struct {
    bool valid;
    U32 offset;
    U32 revision;
    U32 processor;
    U32 flags;
} UPDATE_INFO;
#endif

#ifndef PROC_INFO_TYPEDEF
#define PROC_INFO_TYPEDEF
typedef struct {
    U32 apic_id;
    U32 signature;
    U32 platform_id;
    U32 ucode_rev;
} PROC_INFO;
#endif

// Structure defining Update header
typedef struct {
    U32 version;
    U32 revision;
    U32 date;
    U32 processor;
    U32 checksum;
    U32 loader;
    U32 resv[6];
    U32 data[500];
} pep_t;

typedef struct {
    U32 version;
    U32 revision;
    U32 date;
    U32 processor;
    U32 checksum;
    U32 loader;
    U32 flags;
    U32 data_size;
    U32 total_size;
    U32 resv[3];
} pep_hdr_t;

typedef struct {
    U32 count;
    U32 checksum;
    U32 resv[3];
} ext_sig_hdr_t;

typedef struct {
    U32 processor;
    U32 flags;
    U32 checksum;
} ext_sig_t;

#endif /* MCU_H */
