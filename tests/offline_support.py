"""Import real integration modules with minimal HA test doubles; no HA install."""

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def load_modules(*names):
    """Test protocol/entity logic without setup, network I/O or recorder access."""
    enum = types.SimpleNamespace
    ha_modules = {
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.core": {"HomeAssistant": object},
        "homeassistant.helpers.aiohttp_client": {
            "async_get_clientsession": lambda _: None
        },
        "homeassistant.exceptions": {"HomeAssistantError": Exception},
        "homeassistant.helpers.entity": {
            "DeviceInfo": dict,
            "EntityCategory": enum(CONFIG="config", DIAGNOSTIC="diagnostic"),
        },
        "homeassistant.helpers.entity_platform": {"AddEntitiesCallback": object},
        "homeassistant.helpers.update_coordinator": {
            "CoordinatorEntity": CoordinatorEntity,
            "DataUpdateCoordinator": CoordinatorEntity,
            "UpdateFailed": Exception,
        },
        "homeassistant.const": {
            "Platform": enum(
                **{
                    k: k.lower()
                    for k in (
                        "BINARY_SENSOR",
                        "DATE",
                        "NUMBER",
                        "SELECT",
                        "SENSOR",
                        "TIME",
                        "SWITCH",
                    )
                }
            ),
            "PERCENTAGE": "%",
            "UnitOfRatio": enum(PARTS_PER_MILLION="ppm"),
            "UnitOfTemperature": enum(CELSIUS="°C"),
            "UnitOfTime": enum(YEARS="a", HOURS="h", DAYS="d", MINUTES="min"),
            "UnitOfVolumeFlowRate": enum(
                LITERS_PER_SECOND="L/s", CUBIC_METERS_PER_HOUR="m³/h"
            ),
        },
        "homeassistant.components.number": {
            "NumberEntity": type("NumberEntity", (), {}),
            "NumberDeviceClass": enum(TEMPERATURE="temperature"),
        },
        "homeassistant.components.sensor": {
            "SensorEntity": type("SensorEntity", (), {}),
            "SensorDeviceClass": enum(
                **{
                    k: k.lower()
                    for k in (
                        "CO2",
                        "DATE",
                        "DURATION",
                        "HUMIDITY",
                        "TEMPERATURE",
                        "VOLATILE_ORGANIC_COMPOUNDS_PARTS",
                    )
                }
            ),
            "SensorStateClass": enum(
                MEASUREMENT="measurement", TOTAL_INCREASING="total_increasing"
            ),
        },
    }
    stubs = {name: module(name, **attrs) for name, attrs in ha_modules.items()}
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "HeliosEasyControls3_HA"
    )
    spec = importlib.util.spec_from_file_location(
        "_helios_offline", path / "__init__.py"
    )
    package = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs | {spec.name: package}):
        spec.loader.exec_module(package)
        return (
            package,
            *(importlib.import_module(f"{spec.name}.{name}") for name in names),
        )
