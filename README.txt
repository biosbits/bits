                     BIOS Implementation Test Suite (BITS)

Build ID: @@BUILDID@@
Build number: @@BUILDNUM@@

Please send any bug reports, patches, or other mail about BITS to the BITS
mailing list, <bits@lists.01.org>, and please include the build ID for
reference.

You can find the BITS homepage at http://biosbits.org/

Disclaimer
==========

None of the menu options provided by this toolkit should affect your system
permanently, only for the current boot.  If you *ever* find that this toolkit
affects your system in any permanent way, that represents a serious bug.
However, poking around at the GRUB command line may turn up some commands
provided by GRUB that can affect your system; if it breaks, you get to keep
both pieces.


Other sources of information
============================

This README.txt file documents how to use BITS.

For instructions to build a bootable USB disk from a BITS binary distribution,
refer to INSTALL.txt included in the top-level directory of that that binary
distribution.

For more detailed documentation on specific components of BITS, see the files
in the Documentation directory.

If you want to do BITS development, start with the BITS source code; on a BITS
USB disk built from this version of BITS, you can find the source code under
/boot/src/bits-@@BUILDNUM@@.tar.gz; for more information, see
README.Developers.txt in the BITS source.


Getting Started
===============

BITS has two modes of operation: an interactive mode that provides a menu of
available functionality, and a batch mode that automatically runs operations
such as the testsuite or structure decoding and saves a log of the results
without any user interaction.  By default, BITS runs in interactive mode.  To
configure batch mode, edit the configuration file /boot/bits-cfg.txt and set
the batch option to include one or more batch operations.

BITS will detect your processor signature and enable appropriate menu options
for your CPU and general CPU family.  For instance, if you have a Westmere
processor, you will see menu options specific to the Westmere processor, menu
options for the Nehalem family of processors, and menu options for all Intel
processors.

The available options in BITS fall into several broad categories:

- "Test Menu" contains various test suites designed to test your system and
  its BIOS configuration.  When run normally, these test suites will produce
  a list of all test failures, and a summary of the tests run.  Tests that
  pass will generate no output, and if the entire test suite passes, you will
  see only the summary at the end.  If you want to see more verbose failure
  information from each test, you can set the verbosity level via the
  "test_options" command from the GRUB command line.  If you turn it up high
  enough it will show tests that pass, but that will quickly drown out the
  useful information about test failures; apart from the novelty of seeing
  how many tests BITS includes, this serves little useful purpose.  Turn it
  back off and get back to fixing bugs. :)

- "Configure Menu" contains options to temporarily reconfigure your system.
  None of these options will touch your BIOS or permanently change your system
  configuration, but they will override that configuration for the current boot
  only.

- "Explore Menu" contains options that let you explore your system's existing
  configuration and behavior, as well as experimental tests which produce
  results beyond just PASS/FAIL.  For example, you can explore the latency
  incurred to wake CPUs from deeper C-states.

- "View and Save Log" contains options to review the log of BITS test
  results, clear the log, or save the log to /boot/bits-log.txt.

- "Boot an OS from disk" provides options that allow you to boot your
  existing operating system from a hard disk.  You can use these options to
  test OS behavior after running options from the Configure menu to change
  your system's configuration; for instance, after running Intel's power
  management reference code to overwrite your BIOS's power management
  configuration, you could boot Linux and run powertop, or boot your own test
  workload and run benchmarks.


Credits
=======

Authors:
Burt Triplett <burt@pbjtriplett.org>
Josh Triplett <josh@joshtriplett.org>

Based on:
GNU GRUB2 - https://www.gnu.org/software/grub/
Python - https://www.python.org/
ACPICA - https://acpica.org/
fdlibm - http://www.netlib.org/fdlibm/

For more details, see README.Developers.txt
