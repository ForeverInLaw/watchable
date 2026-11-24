# Full clone as a research track next to the public-API companion

Supersedes the scope limit in ADR 0001. Notification delivery is the core of the product, and only a full clone (the Android phone taking the iPhone's place in the system pairing) delivers it over Bluetooth with native notifications and no relay. We therefore research a full clone in parallel, as track R1, while the public-API companion stays the working product that every milestone builds on.

Protocol knowledge comes from three sources only: public research, traffic captured between our own iPhone and watch, and a protocol specification relayed by the human. The human may consult an existing implementation and describes message sequences, frame layouts, field meanings and algorithm names in their own words. Code, strings, keys, certificates and constants copied from that implementation are never relayed or committed. Everything learned is written down in `protocol/` before any code depends on it.

R1 ends with a go/no-go ADR. The main open risk is whether pairing depends on Apple servers (activation, Activation Lock, device attestation) in a way an Android phone cannot satisfy.

## Consequences

- ADR 0001 still governs M0–M8; the full clone replaces nothing until R1 reaches a go decision.
- Agents ask the human for protocol details instead of guessing them, and record each answer in `protocol/`.
- The public repository never contains material taken from another implementation.
