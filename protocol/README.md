# Protocol

JSON schemas and examples are the contract between Companion, Watch app, and Relay.

Layout:
- `schema/` — JSON Schema files.
- `examples/` — valid request/response examples.

Rules:
- FCM and BLE messages are wrapped in the envelope `v`, `id`, `type`, `sent_at`, `device_id`, `payload`; HTTP bodies and APNs pushes are not (`../docs/TZ.md` §5.3).
- Schemas for HTTP endpoints describe the bare body; FCM and BLE schemas describe the `payload` of their `type`.
- `snake_case` for JSON fields.
- Timestamps are RFC3339 UTC.
- Breaking changes bump the protocol version: the `/v1` path prefix and the envelope `v`.

See `../docs/TZ.md` §5.
