# Copyright (c) 2015, Intel Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * Neither the name of Intel Corporation nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
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

LOCAL?=
V?=0

GNUMAKEFLAGS:=--output-sync=line

BITS:=$(abspath $(dir $(lastword $(MAKEFILE_LIST))))

buildid:=$(shell cd '$(BITS)' && (GIT_CEILING_DIRECTORIES='$(BITS)' git rev-parse HEAD 2>/dev/null || echo 'Unknown - not built from repository'))
gitbuildnum:=$(shell cd '$(BITS)' && (GIT_CEILING_DIRECTORIES='$(BITS)' git rev-list HEAD 2>/dev/null | wc -l) )
ifeq ($(gitbuildnum),0)
buildnum:=snapshot
else
buildnum:=$(shell expr 2000 + '$(gitbuildnum)')
endif

ifeq ($(V),0)
Q:=@
else
Q:=
endif

workdir:=$(BITS)/build

bits-src-orig:=$(BITS)
# bits-src intentionally does not exist
grub-src:=$(workdir)/grub
grub-contrib-src-orig:=$(BITS)/rc
grub-contrib-src:=$(workdir)/bits
contrib-deps:=$(grub-src)/grub-core/contrib-deps
python-host-src:=$(workdir)/python-host

export GRUB_CONTRIB:=$(grub-contrib-src)
grub-prefix:=$(workdir)/grub-inst
grub-libdir:=$(grub-prefix)/lib
target:=$(workdir)/bits-$(buildnum)
srcdir:=$(target)/boot/src

setup-dirs:='$(workdir)' '$(target)' '$(target)/boot' '$(target)/boot/grub' '$(target)/boot/mcu' '$(target)/boot/mcu.first' '$(target)/boot/python' '$(srcdir)' '$(target)/efi/boot' '$(contrib-deps)' '$(python-host-src)'

cleanfiles='$(BITS)/bits-$(buildnum).iso' '$(BITS)/bits-$(buildnum).zip' '$(BITS)/bits-latest.iso' '$(BITS)/bits-latest.zip'

all: dist

clean:
	$(Q)rm -rf '$(workdir)'
	$(Q)rm -f $(cleanfiles)

# setup should always be the first target invoked
setup:
ifneq ($(LOCAL),)
	@echo 'Including local-files in the build; DO NOT DISTRIBUTE THIS BUILD.'
endif
	$(Q)rm -rf '$(workdir)'
	$(Q)mkdir -p $(setup-dirs)

copy-%: setup
	$(Q)cp -a '$($*-src-orig)/.' '$($*-src)'

copygrub: setup
	$(Q)tar -cf - --exclude=.git -C $(BITS)/deps/grub . | tar -xf - -C $(grub-src)

copydeps: setup
	$(Q)tar -cf - --exclude=.git --exclude=./grub -C $(BITS)/deps . | tar -xf - -C $(contrib-deps)

fixup-libffi: copydeps
	$(Q)sed -e 's/#ifndef @TARGET@/#ifdef GRUB_TARGET_CPU_I386/' \
	        -e 's/#define @TARGET@/#define X86\n#else\n#define X86_64/' \
	        -e 's/@HAVE_LONG_DOUBLE@/1/' \
	        -e 's/@HAVE_LONG_DOUBLE_VARIANT@/0/' \
	        -e 's/@FFI_EXEC_TRAMPOLINE_TABLE@/0/' \
	        '$(contrib-deps)/libffi/include/ffi.h.in' > '$(contrib-deps)/libffi/include/ffi.h'

autogen-grub: copygrub copy-grub-contrib fixup-libffi copydeps
	$(Q)cd '$(grub-src)' && ./autogen.sh

i386-pc-img:=boot/grub/core.img
i386-efi-img:=efi/boot/bootia32.efi
x86_64-efi-img:=efi/boot/bootx64.efi
i386-pc-extra-modules:=biosdisk
common-modules:=fat part_msdos part_gpt iso9660

build-grub-%: autogen-grub
	$(Q)mkdir '$(workdir)/grub-build-$*'
	$(Q)cd '$(workdir)/grub-build-$*' && '$(grub-src)/configure' --prefix='$(grub-prefix)' --libdir='$(grub-libdir)' --program-prefix= --target=$(firstword $(subst -, ,$*)) --with-platform=$(lastword $(subst -, ,$*)) --disable-nls --disable-efiemu --disable-grub-emu-usb --disable-grub-emu-sdl --disable-grub-mkfont --disable-grub-mount --disable-device-mapper --disable-libzfs MAKEINFO=/bin/true TARGET_CFLAGS='-Os -Wno-discarded-array-qualifiers'
	$(Q)cd '$(workdir)/grub-build-$*' && $(MAKE) install
	$(Q)mkdir -p '$(target)/boot/grub/$*'
	$(Q)for suffix in img lst mod ; do \
	    cp '$(grub-libdir)/grub/$*/'*.$$suffix '$(target)/boot/grub/$*/' ;\
	done
	$(Q)'$(grub-prefix)/bin/grub-mkimage' -O $* --output='$(target)/$($*-img)' --prefix=/boot/grub $($*-extra-modules) $(common-modules)

# Workaround for syslinux 5 bug booting lnxboot.img
fixup-grub-i386-pc: build-grub-i386-pc
	$(Q)cat '$(target)/boot/grub/i386-pc/lnxboot.img' '$(target)/boot/grub/core.img' > '$(target)/boot/grub/lnxcore.img'
	$(Q)rm '$(target)/boot/grub/core.img'

dist: fixup-grub-i386-pc build-grub-i386-efi build-grub-x86_64-efi

install-syslinux: setup
	$(Q)cp -a '$(BITS)/syslinux' '$(target)/boot/'
dist: install-syslinux

install-doc: setup
	$(Q)cp -a '$(BITS)/Documentation' '$(target)/boot/'
dist: install-doc

install-grub-cfg: setup
	$(Q)cp -a '$(BITS)/cfg' '$(target)/boot/'
dist: install-grub-cfg

# Add a 512k preallocated file, full of newlines, to hold BITS logs.
install-log: setup
	$(Q)yes '' | head -c 524288 > '$(target)/boot/bits-log.txt'
dist: install-log

install-bitsversion: setup
	$(Q)echo 'buildid = "$(buildid)"' >'$(target)/boot/python/bitsversion.py'
	$(Q)echo 'buildnum = "$(buildnum)"' >>'$(target)/boot/python/bitsversion.py'
dist: install-bitsversion

install-bitsconfigdefaults: setup
	$(Q)echo '# Built-in configuration defaults.' >'$(target)/boot/python/bitsconfigdefaults.py'
	$(Q)echo '# Do not edit; edit /boot/bits-cfg.txt instead.' >>'$(target)/boot/python/bitsconfigdefaults.py'
	$(Q)echo 'defaults = """' >>'$(target)/boot/python/bitsconfigdefaults.py'
	$(Q)cat '$(BITS)/bits-cfg.txt' >>'$(target)/boot/python/bitsconfigdefaults.py'
	$(Q)echo '"""' >>'$(target)/boot/python/bitsconfigdefaults.py'
dist: install-bitsconfigdefaults

install-toplevel-cfg: setup
	$(Q)echo 'source /boot/cfg/toplevel.cfg' >'$(target)/boot/grub/grub.cfg'
dist: install-toplevel-cfg

install-bits-cfg: setup
	$(Q)cp '$(BITS)/bits-cfg.txt' '$(target)/boot/'
dist: install-bits-cfg

install-readme: setup
	$(Q)sed 's/@@BUILDID@@/$(buildid)/g; s/@@BUILDNUM@@/$(buildnum)/g' '$(BITS)/README.txt' > '$(target)/boot/README.txt'
dist: install-readme

install-news: setup
	$(Q)cp '$(BITS)/NEWS.txt' '$(target)/boot/NEWS.txt'
dist: install-news

install-src-bits: setup
	$(Q)tar -czf '$(srcdir)/$(notdir $(bits-src-orig))-$(buildnum).tar.gz' --exclude=.git --exclude-from='$(BITS)/.gitignore' -C '$(bits-src-orig)/..' '$(notdir $(bits-src-orig))'
dist: install-src-bits

build-python-host: setup
	$(Q)tar -cf - --exclude=.git -C $(BITS)/deps/python . | tar -xf - -C $(python-host-src)
	$(Q)cd '$(python-host-src)' && ./configure
	$(Q)cd '$(python-host-src)' && $(MAKE)

pylibtmp:=$(workdir)/python-lib
pylibs:=\
	__future__.py \
	_abcoll.py \
	_weakrefset.py \
	abc.py \
	argparse.py \
	atexit.py \
	base64.py \
	bdb.py \
	bisect.py \
	cmd.py \
	codecs.py \
	collections.py \
	ConfigParser.py \
	contextlib.py \
	copy.py \
	copy_reg.py \
	csv.py \
	ctypes/__init__.py \
	ctypes/_endian.py \
	difflib.py \
	dis.py \
	dummy_thread.py \
	encodings \
	fnmatch.py \
	formatter.py \
	functools.py \
	genericpath.py \
	getopt.py \
	gettext.py \
	glob.py \
	hashlib.py \
	heapq.py \
	httplib.py \
	inspect.py \
	keyword.py \
	locale.py \
	linecache.py \
	logging/__init__.py \
	mimetools.py \
	opcode.py \
	optparse.py \
	pdb.py \
	pickle.py \
	pkgutil.py \
	posixpath.py \
	pprint.py \
	profile.py \
	pstats.py \
	pydoc.py \
	pydoc_data \
	re.py \
	repr.py \
	rfc822.py \
	rlcompleter.py \
	shlex.py \
	socket.py \
	sre_compile.py \
	sre_constants.py \
	sre_parse.py \
	stat.py \
	string.py \
	StringIO.py \
	struct.py \
	textwrap.py \
	timeit.py \
	token.py \
	tokenize.py \
	traceback.py \
	types.py \
	unittest \
	urlparse.py \
	urllib.py \
	urllib2.py \
	UserDict.py \
	uuid.py \
	warnings.py \
	weakref.py

install-pylib: setup
	$(Q)mkdir -p '$(pylibtmp)'
	$(Q)cd '$(pylibtmp)' && mkdir -p $(filter-out ./,$(dir $(pylibs)))
	$(Q)cd '$(BITS)/deps/python/Lib' && cp --parents -a $(pylibs) '$(pylibtmp)'

# The dd invocation sets the mtime to zero in all bytecode files, since GRUB2
# (and thus our implementation of fstat) doesn't support mtime.
define bytecompile
$(Q)'$(python-host-src)/python' -m compileall -d '' '$(1)'
$(Q)find '$(1)' -name '*.pyc' -exec dd if=/dev/zero of={} bs=4 count=1 seek=1 conv=notrunc status=none \;
endef

bytecompile-pylib: install-pylib build-python-host
	$(call bytecompile,$(pylibtmp))
	$(Q)cd '$(pylibtmp)' && zip -qr '$(target)/boot/python/lib.zip' . -i '*.pyc'
dist: bytecompile-pylib

install-bits-python: setup
	$(Q)cp -a '$(BITS)/python/.' '$(target)/boot/python/'

bytecompile-bits-python: install-bits-python build-python-host
	$(call bytecompile,$(target)/boot/python)
dist: bytecompile-bits-python

install-install: setup
	$(Q)cp '$(BITS)/INSTALL.txt' '$(target)/'
dist: install-install

install-copying: setup
	$(Q)cp '$(BITS)/COPYING' '$(target)/boot/'
dist: install-copying

dist:
ifneq ($(LOCAL),)
	$(Q)cp -a '$(BITS)/local-files/.' '$(target)/'
endif
	$(Q)rm -f '$(BITS)/bits-$(buildnum).iso' '$(BITS)/bits-$(buildnum).zip'
	$(Q)'$(grub-prefix)/bin/grub-mkrescue' -o '$(BITS)/bits-$(buildnum).iso' '$(target)'
	$(Q)cp '$(BITS)/bits-$(buildnum).iso' '$(BITS)/bits-latest.iso'
	$(Q)cp '$(BITS)/bits-$(buildnum).iso' '$(target)/'
	$(Q)cd '$(workdir)' && zip -qr '$(BITS)/bits-$(buildnum).zip' 'bits-$(buildnum)'
	$(Q)cp '$(BITS)/bits-$(buildnum).zip' '$(BITS)/bits-latest.zip'
