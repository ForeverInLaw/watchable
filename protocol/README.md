# Protocol

JSON schemas and examples are the contract between Companion, Watch app, and Relay.

Layout:
- `schema/` — JSON Schema draft 2020-12, one `<name>.schema.json` per message. Schemas reference each other by file name.
- `examples/` — valid examples named `<name>[.<variant>].json`; each is checked against `<name>.schema.json` by `relay/tests/test_protocol.py`, and every schema needs at least one.

Rules:
- FCM and BLE messages are wrapped in the envelope `v`, `id`, `type`, `sent_at`, `device_id`, `payload`; HTTP bodies and APNs pushes are not (`../docs/TZ.md` §5.3).
- Schemas for HTTP endpoints describe the bare body; FCM and BLE schemas describe the `payload` of their `type`, such as `reply-execute`.
- `fcm-envelope` is the envelope as FCM `data` carries it: every value a string, `payload` the JSON text of that object (`../docs/TZ.md` §9.4). JSON Schema does not look inside that text, so `relay/tests/test_protocol.py` decodes the example's `payload` and checks it against its schema.
- `snake_case` for JSON fields.
- Timestamps are RFC3339 UTC.
- Breaking changes bump the protocol version: the `/v1` path prefix and the envelope `v`.

See `../docs/TZ.md` §5.
