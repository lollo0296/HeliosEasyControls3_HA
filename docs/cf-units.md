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
unit rather than an assumed one.

Existing unique IDs, default-disabled status, bounds and setters are retained.
These are number entities, so no sensor statistics migration is introduced.
This metadata change does not establish CF hardware support or fix the separate
firmware-dependent register-map compatibility problem: 0x8001-0x8006 have other
meanings in firmware 1.0.9. A future capability/map guard must protect both entity
creation and writes. Unit selection alone is not such a guard.

Run offline tests with `python -m unittest discover -s tests -v` after installing
`python-dateutil` and `websockets`. Tests use minimal HA doubles, synthetic frames
and a replaced transport; no device is contacted.
