/* This header undefines everything defined in grub header files that conflict
 * with Python, including config.h and various generic names. */

#ifndef GRUBUNCONFIG_H
#define GRUBUNCONFIG_H

#undef LOCAL

/* config.h */
#undef ADDR32
#undef BSS_START_SYMBOL
#undef DATA32
#undef ENABLE_NLS
#undef END_SYMBOL
#undef HAVE_ASPRINTF
#undef HAVE_DCGETTEXT
#undef HAVE_FT2BUILD_H
#undef HAVE_GETTEXT
#undef HAVE_INTTYPES_H
#undef HAVE_MEMALIGN
#undef HAVE_MEMORY_H
#undef HAVE_POSIX_MEMALIGN
#undef HAVE_STDINT_H
#undef HAVE_STDLIB_H
#undef HAVE_STRINGS_H
#undef HAVE_STRING_H
#undef HAVE_SYS_STAT_H
#undef HAVE_SYS_TYPES_H
#undef HAVE_UNISTD_H
#undef HAVE_VASPRINTF
#undef HAVE___ASHLDI3
#undef HAVE___ASHRDI3
#undef HAVE___BSWAPDI2
#undef HAVE___BSWAPSI2
#undef HAVE___LSHRDI3
#undef HAVE___UCMPDI2
#undef PACKAGE
#undef PACKAGE_BUGREPORT
#undef PACKAGE_NAME
#undef PACKAGE_STRING
#undef PACKAGE_TARNAME
#undef PACKAGE_URL
#undef PACKAGE_VERSION
#undef SIZEOF_LONG
#undef SIZEOF_VOID_P
#undef STDC_HEADERS
#undef _ALL_SOURCE
#undef _GNU_SOURCE
#undef _POSIX_PTHREAD_SEMANTICS
#undef _TANDEM_SOURCE
#undef __EXTENSIONS__
#undef VERSION
#undef WORDS_BIGENDIAN
#undef YYTEXT_POINTER

#endif /* GRUBUNCONFIG_H */
