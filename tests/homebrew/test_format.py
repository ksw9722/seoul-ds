#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Mutation checks for the locally compiled fixture; no downloaded test ROMs."""
from pathlib import Path
import struct
import unittest

from validate_nds import crc16, validate_bytes, validate_manifest

ROOT = Path(__file__).resolve().parents[2]


class FixtureFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = (ROOT / "artifacts/homebrew/seoul-ds-test.nds").read_bytes()

    def test_valid_local_fixture(self):
        self.assertEqual("PASS", validate_bytes(self.rom)["format_status"])

    def test_source_manifest_matches(self):
        self.assertGreater(validate_manifest(ROOT / "artifacts/homebrew/manifest.json", self.rom), 5)

    def test_known_crc_vector(self):
        self.assertEqual(0x4B37, crc16(b"123456789"))

    def test_nonzero_boot_logo_rejected(self):
        changed = bytearray(self.rom)
        changed[0xC0] = 1
        with self.assertRaisesRegex(ValueError, "Boot-logo"):
            validate_bytes(changed)

    def test_damaged_header_rejected(self):
        changed = bytearray(self.rom)
        changed[0x20] ^= 4
        with self.assertRaisesRegex(ValueError, "Header CRC"):
            validate_bytes(changed)

    def test_damaged_banner_rejected(self):
        changed = bytearray(self.rom)
        banner = struct.unpack_from("<I", changed, 0x68)[0]
        changed[banner + 0x20] ^= 1
        with self.assertRaisesRegex(ValueError, "Banner CRC"):
            validate_bytes(changed)

    def test_overlapping_payload_rejected_even_with_recomputed_header_crc(self):
        changed = bytearray(self.rom)
        arm9_offset = struct.unpack_from("<I", changed, 0x20)[0]
        struct.pack_into("<I", changed, 0x30, arm9_offset)
        struct.pack_into("<H", changed, 0x15E, crc16(changed[:0x15E]))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            validate_bytes(changed)

    def test_truncated_rom_rejected(self):
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            validate_bytes(self.rom[:-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
