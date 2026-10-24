"""Offline unit selection, entity identity and unscaled setpoint tests."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from offline_support import load_modules

integration, protocol, numbers = load_modules("EasyControls3Instance", "number")


class CfUnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device = protocol.EasyControls3Instance("unused.invalid")
        self.device._SerialNR = 0
        self.coordinator = SimpleNamespace(
            data=self.device, async_request_refresh=AsyncMock()
        )
        self.entities = []
        await numbers.async_setup_entry(
            SimpleNamespace(data={numbers.DOMAIN: {"test": self.coordinator}}),
            SimpleNamespace(entry_id="test"),
            self.entities.extend,
        )
        self.entities = [
            e for e in self.entities if isinstance(e, numbers.CfBaseAirflowNumber)
        ]

    def parse_unit(self, unit):
        data = bytearray(514)
        # A_CYC_CF_FAN_SPEED_UNIT = 0x5012; settings buffer starts at 182.
        offset = 182 + 0x12
        data[offset * 2 : offset * 2 + 2] = unit.to_bytes(2, "big")
        for offset, value in ((248, 1), (249, 1), (250, 26)):
            data[offset * 2 : offset * 2 + 2] = value.to_bytes(2, "big")
        self.device._parse_settings(bytes(data))

    async def test_all_six_entities_follow_current_unit(self):
        self.assertEqual(len(self.entities), 6)
        keys = (
            "away_supply",
            "away_extract",
            "home_supply",
            "home_extract",
            "boost_supply",
            "boost_extract",
        )
        for entity, key in zip(self.entities, keys, strict=True):
            self.assertEqual(entity._attr_unique_id, f"0_cfBaseAirflow_{key}")
            self.assertFalse(entity._attr_entity_registry_enabled_default)
            self.assertIsNone(entity.native_unit_of_measurement)
        for raw, expected in (
            (0, "L/s"),
            (1, "m³/h"),
            (2, "%"),
            (3, None),
            (65535, None),
        ):
            self.parse_unit(raw)
            for entity in self.entities:
                self.assertEqual(entity.native_unit_of_measurement, expected)

    async def test_unit_metadata_does_not_rescale_values_or_writes(self):
        self.device._exchangeData = AsyncMock(
            return_value=bytes.fromhex("0200f500f700")
        )
        for raw in (0, 1, 2):
            self.parse_unit(raw)
            for index, entity in enumerate(self.entities):
                key = entity._attr_unique_id.removeprefix("0_cfBaseAirflow_")
                self.device._cfBaseAirflow[key] = 42
                self.assertEqual(entity.native_value, 42)
                await entity.async_set_native_value(42)
                command = self.device._exchangeData.await_args.args[0]
                self.assertEqual(int.from_bytes(command[4:6], "little"), 0x8001 + index)
                self.assertEqual(int.from_bytes(command[6:8], "little"), 42)
