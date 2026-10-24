# Constant-flow setpoint units

The six Base Airflow numbers use the current device unit selection, not a fixed
airflow unit. Firmware 1.0.29's frontend binds the setting to
`A_CYC_CF_FAN_SPEED_UNIT = 20498` (`0x5012`); the corresponding settings-relative
read offset is 18, hence absolute buffer offset 200. The address is also present
in `docs/registers.json`.

The frontend's `service.diagnostics.airflow` enum and `airflowunit` renderer map
0 to l/s, 1 to cubic metres per hour and 2 to percent. Each of the six profile
base-airflow controls uses that renderer. The read path copies the raw register
value to the control, and the setpoint write path writes integer values without
a unit conversion. The integration therefore updates the unit on each read and
leaves native values and writes unscaled. Missing/unknown selections have no
unit rather than an assumed one. A plausible enum value alone is insufficient:
the saved 1.0.9 frame contains zero at offset 200, but that firmware has no
`A_CYC_CF_FAN_SPEED_UNIT` symbol. Its `0x8001` through `0x8006` registers mean
`SUPP_FAN_TEST`, `EXTR_FAN_TEST`, `BY_PASS_TEST`, `HEATER_TEST`,
`EXTRA_HEATER_TEST` and `EFFICIENCY_TEST`, respectively. Calling that zero
"litres per second" would be incorrect.

## Positive mapping check

Before attaching a unit, the integration reads the configured device's
`/js/bundle.js` using Home Assistant's HTTP session. It recognizes static text;
it does not execute JavaScript. Recognition requires all seven expected register
names and addresses, their read offsets, the preceding range boundaries and
block sizes, and the associated unit selector's generic, CF and Helios lists.
Conflicting assignments or another register name at a protected address reject
the mapping. An unfamiliar bundle format also rejects it conservatively.

No model number or firmware-version threshold grants support. The version words
only key the per-instance cache. A version change clears the previous mapping
and unit before loading again. Missing/invalid version words disable the unit.
Downloads and decompression are bounded to 16 MiB, with a 10-second timeout and
no HTTP redirects. Fetch/decoding failures leave the ordinary register refresh
working without CF units. Recognition failures and transient download failures
are cached until integration reload or a firmware identity change; reload the
integration to retry. No private URL or exception details are logged.

This recognizes a known register and enum contract, not a hardware capability.
It is deliberately conservative: a device with an equivalent but differently
formatted UI bundle may have no unit until that format has been reviewed.

Existing unique IDs, default-disabled status, bounds and setters are retained.
These are number entities, so no sensor statistics migration is introduced.
This metadata guard does not establish CF hardware support or fix the existing
firmware-dependent control exposure: it does not hide the six existing entities,
change their bounds, or protect their setters. A separate compatibility change
must protect both entity creation and writes. Do not interpret a displayed unit
as a new authorization to write these registers.

## Evidence and coverage

`tests/fixtures/cf-1.0.9.txt` and `cf-1.0.29.txt` contain only the relevant symbol
and declarative UI excerpts from saved device bundles. Assignment separators
are normalized to semicolons; no host, serial number or instance ID is included.
Original bundle SHA-256 values:

- 1.0.9: `ef9e3482f6cf2ef9feaa25c41b7b97befb751fefdab0fa3aa5c910b53be959ef`
- 1.0.29: `edd8b09d6b72ebc8c8628f9660b384d9eccc36a61214183e8dea9e88611d87f1`

The checked-in `docs/registers.json` independently lists the newer addresses
(its provenance names KWL 360 W ET); the saved two-version evidence comes from
the KWL300WL device history. This is not live validation of every Helios model.

Tests cover the supported mapping, old reserved zero, unknown/missing/conflicting
symbols, changed layout/enums, invalid versions/units, cache invalidation, loader
failure, plain/gzip HTTP responses and download/decompression limits. Existing
identity and unscaled read/write assertions remain in place.

Run offline tests with `python -m unittest discover -s tests -v` after installing
`python-dateutil` and `websockets`. Tests use minimal HA doubles, synthetic frames
and a replaced transport; no device is contacted.
