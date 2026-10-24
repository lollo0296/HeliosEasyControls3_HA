# Uptime component evidence

The saved firmware 1.0.9 and 1.0.29 frontend bundles read
`A_CYC_TOTAL_UP_TIME_YEARS` (4617) and `A_CYC_TOTAL_UP_TIME_HOURS` (4618), and pass
them together as `{years, hours}` to `EXT_CYC_TOTAL_UP_TIME`.
The UI formats the years component alongside `floor(hours / 24)` days.
It does not present the hours register as an independent lifetime-hours total.

This supports clearer component names. It does not establish the exact rollover
threshold, calendar/leap-year behavior, reset semantics or a conversion to total
hours. Accordingly this change preserves raw readings, units, existing IDs and
statistics behavior. It adds no entity or computed counter.

Run `python -m unittest discover -s tests -v` with `python-dateutil` and
`websockets` installed. The test imports the real parser and sensor classes with
minimal HA doubles and verifies the unchanged identities, raw values and state
classes. It does not test recorder migration or a physical rollover.
