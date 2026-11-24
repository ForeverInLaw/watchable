# Protocol

JSON schemas and examples are the contract between Companion, Watch app, and Relay.

Layout:
- `schema/` — JSON Schema files.
- `examples/` — valid request/response examples.

Rules:
- Every message has `v`, `id`, `type`, `sent_at`, `device_id`, `payload`.
- `snake_case` for JSON fields.
- Timestamps are RFC3339 UTC.
- Breaking changes bump `v`.

See `../docs/TZ.md` §5.
