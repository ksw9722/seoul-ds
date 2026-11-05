/* SPDX-License-Identifier: GPL-3.0-only
 * Original Seoul DS test startup; no firmware boot code. See ../../LICENSE.
 */
.syntax unified
.cpu arm946e-s
.arm
.section .text.start, "ax", %progbits
.global _start
.type _start, %function
_start:
    msr cpsr_c, #0xdf
    ldr sp, =0x023f0000
    ldr r0, =__bss_start__
    ldr r1, =__bss_end__
    mov r2, #0
1:
    cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
    bl fixture_main
2:
    b 2b
.size _start, .-_start
.section .note.GNU-stack, "", %progbits
