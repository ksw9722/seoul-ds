/* SPDX-License-Identifier: GPL-3.0-only */
ENTRY(_start)
SECTIONS {
    . = 0x02380000;
    .text : { KEEP(*(.text.start)) *(.text*) }
    /DISCARD/ : { *(.comment) *(.ARM.exidx*) *(.ARM.extab*) *(.note*) }
}
