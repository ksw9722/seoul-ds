/* SPDX-License-Identifier: GPL-3.0-only */
ENTRY(_start)
SECTIONS {
    . = 0x02000000;
    .text : { KEEP(*(.text.start)) *(.text*) }
    .rodata : ALIGN(4) { *(.rodata*) }
    .data : ALIGN(4) { *(.data*) }
    .bss (NOLOAD) : ALIGN(4) {
        __bss_start__ = .;
        *(.bss*) *(COMMON)
        . = ALIGN(4);
        __bss_end__ = .;
    }
    /DISCARD/ : { *(.comment) *(.ARM.exidx*) *(.ARM.extab*) *(.note*) }
}
ASSERT(__bss_end__ < 0x02380000, "ARM9 payload overlaps ARM7 memory")
