/* SPDX-License-Identifier: GPL-3.0-only
 * Original idle ARM7 payload. No touch, audio, filesystem or network services.
 * See ../../LICENSE.
 */
.syntax unified
.cpu arm7tdmi
.arm
.section .text.start, "ax", %progbits
.global _start
.type _start, %function
_start:
    msr cpsr_c, #0xdf
    ldr r0, =0x04000208
    mov r1, #0
    str r1, [r0]
1:
    b 1b
.size _start, .-_start
.section .note.GNU-stack, "", %progbits
