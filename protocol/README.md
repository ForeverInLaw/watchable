# Protocol

JSON schemas and examples are the contract between Companion, Watch app, and Relay.

Layout:
- `schema/` — JSON Schema files.
- `examples/` — valid request/response examples.

Rules:
- FCM and BLE messages are wrapped in the envelope `v`, `id`, `type`, `sent_at`, `device_id`, `payload`.
- HTTP bodies and APNs pushes have no envelope. Over HTTP the `/v1/...` path gives the version and type, the bearer token gives the device, and `Idempotency-Key` gives the id. APNs follows Apple's payload format.
- Schemas for HTTP endpoints describe the bare body; FCM and BLE schemas describe the `payload` of their `type`.
- `snake_case` for JSON fields.
- Timestamps are RFC3339 UTC.
- Breaking changes bump `v`.

See `../docs/TZ.md` §5.3.
