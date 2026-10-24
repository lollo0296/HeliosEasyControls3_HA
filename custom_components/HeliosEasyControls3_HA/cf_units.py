"""Recognize the CF unit contract in the device's own web UI, without executing it."""

from __future__ import annotations

import asyncio
import gzip
import io
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession

_MAX_BUNDLE_BYTES = 16 * 1024 * 1024
_CF_NAMES = (
    "AWAY_SUPPLY",
    "AWAY_EXTRACT",
    "HOME_SUPPLY",
    "HOME_EXTRACT",
    "BOOST_SUPPLY",
    "BOOST_EXTRACT",
)
_REGISTERS = {"A_CYC_CF_FAN_SPEED_UNIT": 0x5012} | {
    f"A_CYC_CF_{name}_BASE_AIRFLOW": 0x8001 + index
    for index, name in enumerate(_CF_NAMES)
}
_RANGES = {
    f"RANGE_{edge}_g_{name}": value
    for name, start, end in (
        ("cyclone_general_info", 0, 35),
        ("typhoon_general_info", 256, 282),
        ("cyclone_hw_state", 4352, 4394),
        ("cyclone_sw_state", 4608, 4632),
        ("cyclone_time", 4848, 4854),
        ("cyclone_output", 4864, 4870),
        ("cyclone_input", 5120, 5126),
        ("cyclone_config", 8192, 8221),
        ("cyclone_settings", 20480, 20555),
        ("typhoon_settings", 21760, 21782),
        ("constant_flow", 32768, 32783),
    )
    for edge, value in (("START", start), ("END", end))
}
_READ_LAYOUT = {
    "CYC_NUM_OF_GENERAL_INFO": 36,
    "CYC_NUM_OF_GENERAL_TYP_INFO": 27,
    "CYC_NUM_OF_HW_STATES": 43,
    "CYC_NUM_OF_SW_STATES": 25,
    "CYC_NUM_OF_TIME_ELEMENTS": 7,
    "CYC_NUM_OF_OUTPUTS": 7,
    "CYC_NUM_OF_INPUTS": 7,
    "CYC_NUM_OF_CONFIGS": 30,
    "CYC_NUM_OF_CYC_SETTINGS": 76,
    "CYC_NUM_OF_TYP_SETTINGS": 23,
    "CYC_NUM_OF_CF": 16,
    "CYC_CF_FAN_SPEED_UNIT": 18,
} | {f"CYC_CF_{name}_BASE_AIRFLOW": 1 + index for index, name in enumerate(_CF_NAMES)}

# Deliberately recognize a known declarative UI contract, not arbitrary JavaScript.
# A changed format fails closed until its meaning has been reviewed.
_UNIT_BINDING = (
    'airflow:{txt:"fan_speed_units",data:{value:2,'
    "modbus:VlxDevConstants.A_CYC_CF_FAN_SPEED_UNIT},"
    'list:[{txt:"cf_unit_liters",data:{value:0}},'
    '{txt:"cf_unit_cubes",data:{value:1}},'
    '{txt:"percent_short",data:{value:2}}],'
    'cflist:[{txt:"cf_unit_liters",data:{value:0}},'
    '{txt:"cf_unit_cubes",data:{value:1}}],'
    'helios_list:[{txt:"cf_unit_liters_defined",data:{value:0}},'
    '{txt:"cf_unit_cubes_defined",data:{value:1}},'
    '{txt:"percent_short",data:{value:2}}]}'
)


def supports_cf_units(bundle: str) -> bool:
    """Require register names, read layout and enum semantics; never infer from values."""
    for namespace, expected in (
        ("VlxDevConstants", _REGISTERS | _RANGES),
        ("VlxReadConstants", _READ_LAYOUT),
    ):
        assignments: dict[str, set[str]] = {}
        for name, value in re.findall(
            rf"(?<![\w.$]){namespace}\.([A-Za-z][A-Za-z_0-9]+)\s*=\s*([^,;]+)",
            bundle,
        ):
            assignments.setdefault(name, set()).add(value.strip())
        if any(
            assignments.get(name) != {str(value)} for name, value in expected.items()
        ):
            return False
        if namespace == "VlxDevConstants":
            for name, values in assignments.items():
                if not name.startswith("A_") or name in expected:
                    continue
                for value in values:
                    # Reject unknown expressions; never evaluate downloaded code.
                    if re.fullmatch(r"[0-9]+", value):
                        address = int(value, 10)
                    elif re.fullmatch(
                        r"0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+", value
                    ):
                        address = int(value, 0)
                    elif match := re.fullmatch(r"([0-9]{1,6})[eE]\+?([0-5])", value):
                        # The recorded minified bundle uses 37e3 and 41e3.
                        address = int(match[1]) * 10 ** int(match[2])
                    else:
                        return False
                    if address in _REGISTERS.values():
                        return False
    compact = re.sub(r"\s+", "", bundle)
    return compact.count(_UNIT_BINDING) == 1


def _decode_bundle(raw: bytes) -> str:
    if raw.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(_MAX_BUNDLE_BYTES + 1)
    if len(raw) > _MAX_BUNDLE_BYTES:
        raise ValueError("Firmware bundle exceeds size limit")
    return raw.decode("utf-8")


async def fetch_bundle(session: ClientSession, host: str) -> str:
    """Read a bounded local bundle; follow no redirects and execute no scripts."""
    async with asyncio.timeout(10):
        async with session.get(
            f"http://{host}/js/bundle.js",
            allow_redirects=False,
            auto_decompress=False,
        ) as response:
            if response.status != 200:
                raise ValueError("Firmware bundle unavailable")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > _MAX_BUNDLE_BYTES:
                    raise ValueError("Firmware bundle exceeds size limit")
        return await asyncio.to_thread(_decode_bundle, bytes(raw))
