"""Preserve existing uptime entities and statistics while clarifying labels."""

import unittest
from types import SimpleNamespace

from offline_support import load_modules

integration, protocol, sensors = load_modules("EasyControls3Instance", "sensor")


class UptimeLabelTests(unittest.TestCase):
    def test_components_preserve_identity_units_values_and_statistics(self):
        device = protocol.EasyControls3Instance("unused.invalid")
        device._SerialNR = 0
        data = bytearray(260)
        for offset, value in ((115, 4), (116, 5559), (117, 72)):
            data[offset * 2 : offset * 2 + 2] = value.to_bytes(2, "big")
        device._parse_sw_state(bytes(data))
        coordinator = SimpleNamespace(data=device)
        for cls, suffix, name, unit, value, state_class in (
            (
                sensors.TotalUptimeYearsSensor,
                "TotalUptimeYears",
                "Uptime Years Component",
                "a",
                4,
                "total_increasing",
            ),
            (
                sensors.TotalUptimeHoursSensor,
                "TotalUptimeHours",
                "Uptime Hours Component",
                "h",
                5559,
                "total_increasing",
            ),
            (
                sensors.CurrentUptimeHoursSensor,
                "CurrentUptimeHours",
                "Current Uptime Hours",
                "h",
                72,
                "measurement",
            ),
        ):
            with self.subTest(sensor=suffix):
                entity = cls(coordinator)
                self.assertEqual(entity._attr_unique_id, f"0_{suffix}")
                self.assertEqual(entity._attr_name, name)
                self.assertEqual(entity.native_value, value)
                self.assertEqual(entity.native_unit_of_measurement, unit)
                self.assertEqual(entity.state_class, state_class)
