This document, README.Developers.txt, provides documentation useful for the
prospective BITS developer.  See README.txt for user documentation, or
INSTALL.txt for instructions on creating a bootable USB disk.

Please send any bug reports, patches, or other mail about BITS to the BITS
mailing list at <bits@lists.01.org>, and please include the git commit ID
(included in README.txt in BITS builds) for reference.

You can find the BITS homepage at http://biosbits.org/

BITS incorporates the following components as git submodules, with changes
recorded as commits in those repositories:
- GRUB2
- Python
- libffi
- ACPICA
- fdlibm


BITS scripting
==============

BITS includes the Python interpreter, and BITS tests and other functionality
use Python whenever possible.  In addition to a subset of the Python standard
library, BITS provides additional Python modules supporting access to platform
functionality such as CPUID, MSRs, PCI, and ACPI.

You can run arbitrary Python from the GRUB command line using the 'py' command;
you'll need to quote its argument so GRUB passes it as a single uninterpreted
string.  For example:

grub> py 'print "Hello world!"'

BITS loads Python modules from /boot/python, and you can add your own modules
there as well.

The standard Python library lives in /boot/python/lib.zip; to include more
modules from the standard library, edit the Makefile.  Remember to include
any other modules imported by the one you want, recursively.

Low-level Python functions implemented in C live in the _bits module, defined
in rc/python/bitsmodule.c.  Define new C functionality there, and re-export or
wrap it in the bits module.

BITS automatically generates the test menu from all the available tests for the
current system.  To add new tests to the test menu, call testsuite.add_test on
them from the register_tests() function of an appropriate test* module (for
non-CPU-specific tests) or of the cpu_* module for a particular target CPU (for
CPU-specific tests).  To add a new test module, call its register_tests()
function from init.init().

Note that if you edit scripts directly on your USB disk, and then rebuild your
USB disk by running ./mkdisk, your scripts will get overwritten.  Edit them in
the BITS source tree instead, or save a separate copy of them before running
./mkdisk.  Even better, they might prove more generally useful, so send them
along to get incorporated into BITS.

Also note that BITS pre-compiles all of its Python code to bytecode files
(.pyc); the version of GRUB2 used by BITS does not support file modification
times, so Python's usual check for whether the source code matches the .pyc
file will not work.  If you edit a .py file directly on your USB disk, you'll
need to remove the corresponding .pyc file manually, or your changes will not
take effect.  However, see above about making changes in the BITS source tree
instead.


Building BITS from source
=========================

BITS incorporates various other projects at build time, via git submodules.  To
build BITS from git, you need to have all the submodules cloned and checked
out.  Use "git clone --recursive" when doing the initial clone of BITS, or use
"git submodule update --init" if you already cloned without --recursive.  If
you obtained BITS via a snapshot tarball, that tarball will include the
corresponding versions of all of the dependencies.

GRUB2 itself has a few build dependencies; review the file "INSTALL" in the
GRUB2 source code for a full list.  Note that because BITS provides additional
GRUB modules and thus extends the GRUB build system, you will need the
additional tools described as required for development snapshots or hacking on
GRUB.

BITS requires GNU binutils 2.20 or newer, due to a bug in the GNU assembler in
older versions which causes it to incorrectly assemble parts of BITS.

The BITS build procedure requires the following additional build dependencies:
- xorriso 1.3.0 or newer, to construct an .iso image using
  grub-mkrescue.  Older versions will fail to recognize the options
  needed to build a single .iso bootable as an EFI CD, EFI hard disk,
  BIOS CD, and BIOS hard disk.
- mtools, to construct the EFI image embedded in an EFI-bootable .iso
- GNU Make 3.81 or newer.

If you build BITS repeatedly, you'll want to install and configure ccache to
speed up these repeated builds.

Once you have the source code unpacked and the build dependencies installed,
you can build BITS by running "make" in the top of the BITS source tree.  (You
probably want to build in parallel by running "make -jN" where N is the number
of CPUs you have.)  This will produce a binary distribution of BITS as a zip
file, which includes installation instructions (INSTALL.txt) and full
corresponding source code.  Read INSTALL.txt for more information on building a
bootable USB disk, including the additional software you will need to do so.

Once you have a bootable USB disk, you can quickly update that disk to include
a new version of BITS by running ./mkdisk after building.  NOTE: ./mkdisk
assumes you have a USB disk /dev/sdb with a partition /dev/sdb1 that you want
to use for BITS.  If you want to use some device other than /dev/sdb, EDIT
MKDISK FIRST!  mkdisk will refuse to write to a non-removable disk as a safety
check; if for some reason you want to write to a non-removable disk, you'll
have to comment out that check as well.  Sorry for making it inconvenient to
overwrite your hard disk.


Coding style
============

C code in BITS follows the K&R coding style, with four space indents, and no
tabs.

Python code in BITS should follow PEP 8
(https://www.python.org/dev/peps/pep-0008/), the Style Guide for Python Code,
which also specifies four-space indents.

Don't try to wrap lines to fit an arbitrary line width, but do wrap lines when
it improves readability by lining up similar code.

The script "bits-indent" roughly approximates the right style for C code,
except that it will un-wrap all lines, even those which look better wrapped.
Use good taste.
