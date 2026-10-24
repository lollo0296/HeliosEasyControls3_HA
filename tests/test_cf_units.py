"""Offline unit selection, entity identity and unscaled setpoint tests."""

import gzip
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from offline_support import load_modules

integration, protocol, numbers, capabilities = load_modules(
    "EasyControls3Instance", "number", "cf_units"
)
FIXTURES = Path(__file__).parent / "fixtures"
OLD_BUNDLE = (FIXTURES / "cf-1.0.9.txt").read_text(encoding="utf-8")
NEW_BUNDLE = (FIXTURES / "cf-1.0.29.txt").read_text(encoding="utf-8")


def frame(unit=0, version=29):
    data = bytearray(514)
    # General version words are little-endian; settings are big-endian.
    data[16:22] = b"\x01\x00\x00\x00" + version.to_bytes(2, "little")
    for offset, value in ((200, unit), (248, 1), (249, 1), (250, 26)):
        data[offset * 2 : offset * 2 + 2] = value.to_bytes(2, "big")
    return bytes(data)


class CfUnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device = protocol.EasyControls3Instance("unused.invalid")
        self.device._bundle_loader = AsyncMock(return_value=NEW_BUNDLE)
        await self.device._refresh_cf_unit_mapping(frame())
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
        self.device._parse_settings(frame(unit))

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

    async def test_old_reserved_zero_and_unknown_mapping_have_no_unit(self):
        for bundle in (OLD_BUNDLE, "", "unknown future mapping"):
            with self.subTest(bundle=bundle[:32]):
                self.device._cf_mapping_version = None
                self.device._bundle_loader = AsyncMock(return_value=bundle)
                await self.device._refresh_cf_unit_mapping(frame(version=9))
                self.parse_unit(0)
                for entity in self.entities:
                    self.assertIsNone(entity.native_unit_of_measurement)

    async def test_version_change_invalidates_mapping_and_caches_failure(self):
        loader = self.device._bundle_loader
        await self.device._refresh_cf_unit_mapping(frame())
        loader.assert_awaited_once()
        self.parse_unit(0)
        self.assertEqual(self.entities[0].native_unit_of_measurement, "L/s")

        async def fail():
            self.assertFalse(self.device._cf_unit_mapping)
            self.assertIsNone(self.device.cfFanSpeedUnit)
            raise TimeoutError

        self.device._bundle_loader = AsyncMock(side_effect=fail)
        await self.device._refresh_cf_unit_mapping(frame(version=30))
        self.parse_unit(0)
        self.assertIsNone(self.entities[0].native_unit_of_measurement)
        await self.device._refresh_cf_unit_mapping(frame(version=30))
        self.device._bundle_loader.assert_awaited_once()
        self.device._bundle_loader = AsyncMock(return_value=NEW_BUNDLE)
        await self.device._refresh_cf_unit_mapping(frame(version=31))
        self.parse_unit(0)
        self.assertEqual(self.entities[0].native_unit_of_measurement, "L/s")

    async def test_missing_invalid_version_or_loader_has_no_unit(self):
        for data in (b"", bytes(22), b"\0" * 4 + b"\xff\xff" * 9):
            await self.device._refresh_cf_unit_mapping(data)
            self.parse_unit(0)
            self.assertIsNone(self.device.cfFanSpeedUnit)
        self.device._bundle_loader = None
        await self.device._refresh_cf_unit_mapping(frame())
        self.parse_unit(0)
        self.assertIsNone(self.device.cfFanSpeedUnit)

    async def test_read_refresh_uses_guard_and_survives_bundle_failure(self):
        device = protocol.EasyControls3Instance(
            "unused.invalid", bundle_loader=AsyncMock(side_effect=OSError)
        )
        device._exchangeData = AsyncMock(return_value=frame())
        with patch.object(device, "_parseData", wraps=device._parse_settings) as parse:
            await device.readCurrentData()
            parse.assert_called_once_with(frame())
        self.assertIsNone(device.cfFanSpeedUnit)


class MappingTests(unittest.TestCase):
    def test_real_sanitized_symbol_and_ui_excerpts(self):
        self.assertTrue(capabilities.supports_cf_units(NEW_BUNDLE))
        self.assertFalse(capabilities.supports_cf_units(OLD_BUNDLE))
        self.assertTrue(
            capabilities.supports_cf_units(
                NEW_BUNDLE + "VlxDevConstants.A_CYC_FAULT_FIRST_DATE_23=37e3;"
            )
        )

    def test_incomplete_ambiguous_or_changed_contract_fails_closed(self):
        for bundle in (
            NEW_BUNDLE.replace("A_CYC_CF_FAN_SPEED_UNIT=20498;", ""),
            NEW_BUNDLE.replace("CYC_NUM_OF_CF=16;", "CYC_NUM_OF_CF=17;"),
            NEW_BUNDLE.replace("CYC_CF_HOME_SUPPLY_BASE_AIRFLOW=3;", ""),
            NEW_BUNDLE.replace("RANGE_START_g_constant_flow=32768;", ""),
            NEW_BUNDLE.replace(
                'txt:"cf_unit_liters",data:{value:0}',
                'txt:"cf_unit_liters",data:{value:1}',
            ),
            NEW_BUNDLE + "VlxDevConstants.A_CYC_CF_FAN_SPEED_UNIT=42;",
            NEW_BUNDLE + "VlxDevConstants.A_CYC_CF_FAN_SPEED_UNIT=20498+1;",
            NEW_BUNDLE + "VlxDevConstants.A_CYC_SUPP_FAN_TEST=32769;",
            NEW_BUNDLE + "VlxDevConstants.A_CYC_SUPP_FAN_TEST=0x8001;",
            NEW_BUNDLE + "VlxDevConstants.A_CYC_SUPP_FAN_TEST=32769e0;",
            NEW_BUNDLE + "VlxDevConstants.A_CYC_SUPP_FAN_TEST=32768+1;",
            NEW_BUNDLE.replace("VlxDevConstants.", "OtherVlxDevConstants."),
            NEW_BUNDLE.replace("VlxReadConstants.", "Other.VlxReadConstants."),
            NEW_BUNDLE.replace("=20498;", "=20498e1;"),
            NEW_BUNDLE.replace("=20498;", "=0x5012;"),
        ):
            with self.subTest(bundle=bundle[-100:]):
                self.assertFalse(capabilities.supports_cf_units(bundle))


class FetchTests(unittest.IsolatedAsyncioTestCase):
    def session(self, payload, status=200):
        class Content:
            async def iter_chunked(self, size):
                for index in range(0, len(payload), 7):
                    yield payload[index : index + 7]

        response = SimpleNamespace(status=status, content=Content())
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        return session

    async def test_plain_and_gzip_download_without_redirects(self):
        for payload in (b"bundle", gzip.compress(b"bundle")):
            session = self.session(payload)
            self.assertEqual(
                await capabilities.fetch_bundle(session, "unused.invalid"), "bundle"
            )
            session.get.assert_called_once_with(
                "http://unused.invalid/js/bundle.js",
                allow_redirects=False,
                auto_decompress=False,
            )

    async def test_http_compression_encoding_and_size_failures(self):
        for session in (
            self.session(b"", 302),
            self.session(b"", 404),
            self.session(b"\x1f\x8bgarbage"),
            self.session(b"\xff"),
            self.session(b"x" * 65),
            self.session(gzip.compress(b"x" * 65)),
        ):
            with (
                self.subTest(session=session),
                patch.object(capabilities, "_MAX_BUNDLE_BYTES", 64),
                self.assertRaises((ValueError, OSError, EOFError)),
            ):
                await capabilities.fetch_bundle(session, "unused.invalid")
        session = MagicMock()
        session.get.side_effect = TimeoutError
        with self.assertRaises(TimeoutError):
            await capabilities.fetch_bundle(session, "unused.invalid")
