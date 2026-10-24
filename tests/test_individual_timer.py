"""Offline protocol regressions; no Home Assistant installation or device needed.

Run with: python -m unittest discover -s tests -v
Dependencies: python-dateutil and websockets (the protocol client's imports).
"""

import datetime
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


def load_protocol():
    """Load the real protocol module without executing HA integration setup."""
    package = types.ModuleType("_helios_test_protocol")
    package.__path__ = [
        str(
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "HeliosEasyControls3_HA"
        )
    ]
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    with patch.dict(
        sys.modules,
        {
            package.__name__: package,
            "homeassistant.exceptions": exceptions,
        },
    ):
        return importlib.import_module(f"{package.__name__}.EasyControls3Instance")


protocol = load_protocol()
KWLState = protocol.KWLState


class IndividualTimerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = protocol.EasyControls3Instance("unused.invalid")
        self.transport = AsyncMock(return_value=bytes.fromhex("0200f500f700"))
        self.device._exchangeData = self.transport
        self.device._instanceState = KWLState.AtHome
        self.device._boostTimerRemaining = 7
        self.device._individualTimerRemaining = 0

    def assert_cached_state_unchanged(self):
        self.assertIs(self.device.instanceState, KWLState.AtHome)
        self.assertEqual(self.device.BoostTimerRemaining, 7)
        self.assertEqual(self.device.IndividualTimerRemaining, 0)

    def assert_command(self, expected_items):
        self.transport.assert_awaited_once()
        command = self.transport.await_args.args[0]
        words = [
            int.from_bytes(command[i : i + 2], "little")
            for i in range(0, len(command), 2)
        ]
        self.assertEqual(words[0], 2 * len(expected_items) + 2)
        self.assertEqual(words[1], 0xF9)
        self.assertEqual(list(zip(words[2:-1:2], words[3:-1:2])), expected_items)
        self.assertEqual(words[-1], sum(words[:-1]) & 0xFFFF)

    async def test_configured_duration_from_settings(self):
        for minutes in (1, 15, 30, 150, 1439):
            with self.subTest(minutes=minutes):
                # Settings range starts at buffer 182 / register 0x5000.
                data = bytearray(2 * 257)
                offset = 182 + (0x5041 - 0x5000)
                data[offset * 2 : offset * 2 + 2] = minutes.to_bytes(2, "big")
                # A valid filter-change date is required by the settings parser.
                for offset, value in ((248, 1), (249, 1), (250, 26)):
                    data[offset * 2 : offset * 2 + 2] = value.to_bytes(2, "big")
                self.device._parse_settings(bytes(data))
                await self.device.switchMode(KWLState.Individual)
                self.assert_command([(0x1204, 0), (0x1205, minutes)])
                self.assert_cached_state_unchanged()
                self.transport.reset_mock()

    async def test_invalid_duration_rejected_before_transport(self):
        for duration in (
            None,
            datetime.time(0, 0),
            datetime.time(0, 15, 1),
            datetime.time(0, 15, microsecond=1),
            datetime.time(0, 15, tzinfo=datetime.timezone.utc),
            15,
            "00:15:00",
        ):
            with self.subTest(duration=duration):
                self.device._individualModeDuration = duration
                with self.assertRaisesRegex(
                    protocol.HomeAssistantError, "configured duration"
                ):
                    await self.device.switchMode(KWLState.Individual)
                self.transport.assert_not_awaited()
                self.assert_cached_state_unchanged()

    async def test_rejected_write_preserves_state(self):
        self.device._individualModeDuration = datetime.time(0, 15)
        self.transport.return_value = b""
        with self.assertRaises(protocol.WriteRejected):
            await self.device.switchMode(KWLState.Individual)
        self.assert_command([(0x1204, 0), (0x1205, 15)])
        self.assert_cached_state_unchanged()

    async def test_transport_failure_preserves_state(self):
        self.device._individualModeDuration = datetime.time(2, 30)
        self.transport.side_effect = OSError("offline transport failure")
        with self.assertRaises(OSError):
            await self.device.switchMode(KWLState.Individual)
        self.assert_cached_state_unchanged()

    async def test_other_mode_timer_commands_unchanged(self):
        self.device._intensivDuration = datetime.time(0, 30)
        for mode, items in (
            (KWLState.AtHome, [(0x1201, 0), (0x1204, 0), (0x1205, 0)]),
            (KWLState.Away, [(0x1201, 1), (0x1204, 0), (0x1205, 0)]),
            (KWLState.Intensive, [(0x1204, 30), (0x1205, 0)]),
        ):
            with self.subTest(mode=mode):
                await self.device.switchMode(mode)
                self.assert_command(items)
                self.transport.reset_mock()


if __name__ == "__main__":
    unittest.main()
