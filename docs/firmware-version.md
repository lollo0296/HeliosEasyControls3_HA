# Device firmware version

The device registry's software version comes from the ventilation unit, not the
integration manifest. No extra request or entity is introduced.

The saved easyControls frontend bundles for firmware 1.0.9 and 1.0.29 use
`A_CYC_APPL_SW_VERSION_1` through `_9` (registers 2 through 10). The matching
`VlxReadConstants` offsets are 2 through 10 in the general-information block.
The UI swaps each 16-bit word, strips the leading zero components, then joins
the remaining decimal components with dots. Both saved read frames have six
leading zero components followed by `1, 0, 9` or `1, 0, 29` respectively.
Only synthetic versions of these words are included in the tests.

The UI treats an all-65535 version as unavailable. This implementation also
returns no version for incomplete data, all-zero data or a partially unavailable
version, rather than displaying an invented version. Interior and trailing zero
components are retained. Existing model/type/serial handling is unchanged.

Offline tests use minimal Home Assistant doubles and real protocol code; they
do not prove Home Assistant device-registry lifecycle behavior. Run with
`python -m unittest discover -s tests -v` after installing `python-dateutil` and
`websockets`. Full integration typing remains covered by the existing CI job.
