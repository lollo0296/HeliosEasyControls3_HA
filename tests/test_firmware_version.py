"""Offline version decoding and device-registry metadata regression tests."""

import unittest
from types import SimpleNamespace

from offline_support import load_modules

integration, protocol = load_modules("EasyControls3Instance")


def frame(parts):
    data = bytearray(36)
    for offset, value in enumerate(parts, start=2):
        data[offset * 2 : offset * 2 + 2] = value.to_bytes(2, "little")
    return bytes(data)


class FirmwareVersionTests(unittest.TestCase):
    def test_versions_and_byte_order(self):
        for parts, expected in (
            ([0] * 6 + [1, 0, 9], "1.0.9"),
            ([0] * 6 + [1, 0, 29], "1.0.29"),
            ([0] * 5 + [1, 2, 300, 0], "1.2.300.0"),
            ([0] * 8 + [1], "1"),
        ):
            with self.subTest(parts=parts):
                self.assertEqual(protocol._firmware_version(frame(parts)), expected)

    def test_unavailable_and_truncated_version(self):
        for data in (
            b"",
            bytes(21),
            frame([0] * 9),
            frame([65535] * 9),
            frame([0] * 6 + [1, 65535, 29]),
        ):
            with self.subTest(data=data):
                self.assertIsNone(protocol._firmware_version(data))

    def test_device_info_uses_device_version_and_keeps_identity(self):
        device = protocol.EasyControls3Instance("unused.invalid")
        entity = integration.EasyControls3BaseEntity(SimpleNamespace(data=device))
        self.assertIsNone(entity.device_info["sw_version"])
        device._parse_device_info(frame([0] * 6 + [1, 0, 29]))
        identity = entity.device_info["identifiers"]
        self.assertEqual(entity.device_info["sw_version"], "1.0.29")
        device._parse_device_info(frame([65535] * 9))
        self.assertIsNone(entity.device_info["sw_version"])
        self.assertEqual(entity.device_info["identifiers"], identity)
