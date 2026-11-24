# Public-API companion instead of a full system clone

> Scope limit superseded by ADR 0005: the full clone is now researched as track R1.

We will implement an Android companion and a watchOS app using only public Apple APIs, without using Apple's private iPhone-Watch pairing protocol. A full system clone would require private BLE work that Apple does not document and that an Apple Developer account does not grant; the public path covers notifications, replies, health, music, alarms, and Find Watch with acceptable limits.

## Consequences

- No system-level call/SMS handling, automatic Wi-Fi join, or critical alerts.
- A paired iPhone is still required to install and update the watchOS app.
- A2093 without LTE needs Wi-Fi or a nearby iPhone to receive APNs pushes.
