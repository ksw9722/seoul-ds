/* SPDX-License-Identifier: GPL-3.0-only
 * Original Seoul DS test fixture, 2026. See ../../LICENSE.
 * No SDK library, game code, graphics, BIOS or proprietary logo is included.
 * This intentionally tests only two display fields, A/B input and state restore.
 */

typedef unsigned short u16;
typedef unsigned int u32;

#define MMIO16(address) (*(volatile u16 *)(address))
#define MMIO32(address) (*(volatile u32 *)(address))

enum {
    DISPLAY_MAIN = 0x04000000,
    DISPLAY_SUB = 0x04001000,
    VCOUNT = 0x04000006,
    KEYS = 0x04000130,
    INTERRUPT_MASTER = 0x04000208,
    POWER_CONTROL = 0x04000304,
    MAIN_BACKDROP = 0x05000000,
    SUB_BACKDROP = 0x05000400,
    MAIN_BRIGHTNESS = 0x0400006C,
    SUB_BRIGHTNESS = 0x0400106C,
};

/* Volatile RAM state is deliberately included in emulator save states. */
static volatile struct {
    u32 top_alternate;
    u32 bottom_alternate;
    u32 previous_keys;
    u32 frames;
} state;

static u16 colour(u32 r, u32 g, u32 b) {
    return (u16)(r | (g << 5) | (b << 10));
}

static void update_fields(void) {
    MMIO16(MAIN_BACKDROP) = state.top_alternate
        ? colour(31, 6, 18) : colour(4, 20, 24);
    MMIO16(SUB_BACKDROP) = state.bottom_alternate
        ? colour(12, 7, 27) : colour(31, 17, 4);
}

void fixture_main(void) {
    /* Polling only: neither processor needs a BIOS IRQ handler. */
    MMIO32(INTERRUPT_MASTER) = 0;
    /* LCDs + both 2D engines; main engine on the top LCD. No 3D required. */
    MMIO16(POWER_CONTROL) = 0x8203;
    MMIO16(MAIN_BRIGHTNESS) = 0;
    MMIO16(SUB_BRIGHTNESS) = 0;
    /* Normal graphics display, all layers disabled: palette entry 0 fills it. */
    MMIO32(DISPLAY_MAIN) = 1u << 16;
    MMIO32(DISPLAY_SUB) = 1u << 16;
    update_fields();

    for (;;) {
        /* One edge sample per vertical blank, without BIOS calls or timers. */
        while (MMIO16(VCOUNT) >= 192) { }
        while (MMIO16(VCOUNT) < 192) { }
        u32 pressed = (u32)(~MMIO16(KEYS)) & 3u;
        u32 edges = pressed & ~state.previous_keys;
        if (edges & 1u) state.top_alternate ^= 1u;    /* A */
        if (edges & 2u) state.bottom_alternate ^= 1u; /* B */
        state.previous_keys = pressed;
        state.frames += 1u;
        update_fields();
    }
}
