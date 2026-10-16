# Verification status

Updated: 2026-10-16. Scope: recorded OFW results and client protocol checks. [Editions](COMPATIBILITY.md).

## Recorded OFW result

| Property | Result |
| --- | --- |
| Game | European BLES01597 |
| Console | Clean OFW, as reported by the player |
| Firmware / game update | Exact versions not recorded |
| Cloud TLS and PSN ticket | Accepted by the deployed service |
| Inbox | Opened |
| Gift sending | Player reported success and item removal |
| Item receipt | Player reported item added to inventory on October 15 |
| Pay It Forward | Reported unlocked on October 14 |

At 06:54:07 UTC on October 15, the recipient Cloud request returned HTTP 200
with a 950-byte response. The player subsequently confirmed inventory receipt.
The exact request triggering the trophy was not recorded. Console state is
player-reported, not independently attested. No universal firmware or region
compatibility is claimed.

## US BLUS30829 client check — 2026-10-16

Mounted game metadata and native save folders identified BLUS30829.
At 08:10:49 UTC, GET/GET for TomeGift and GameToWeb returned HTTP 200.
At 08:14:44 UTC, MAP_GET/TomeGift returned HTTP 200 with a 51-byte response.
TLS 1.2 / AES256-SHA256 completed and mandatory PSN ticket verification passed.
This records connection and mailbox reading. Clean OFW verification, gift
sending/receipt and a fresh trophy result are still pending for BLUS30829.

## Implementation verification

33 automated tests passed for the release candidate. Coverage includes signed
synthetic tickets, tampering, expiry, mailbox access, quotas, metadata,
Japanese document isolation, transactions, restart persistence, DNS and logs.
Automated clients use local certificates and synthetic signing keys; these
checks are not OFW tests.

The experimental certificate chain used in the deployed configuration has
PEM SHA-256 `7dc3793719fe783371f9cae5ae7e6ba39566c22cacb9109fc622599fa7a1e4d0`.
Fresh generation changes keys and certificate fingerprints and requires a
separate client check. The internal reason for client acceptance is unresolved.

## Pending

- Exact OFW and game update numbers for the recorded result.
- Japanese BLJS10199 and US BLUS30829 on clean OFW.
- Repeated delivery/claim/restart scenarios on OFW.
- Fresh trophy capture correlating the game UI with the server request.
- Independent clean deployment from the public release.

GDS, THQ login/SSO and news are outside the implementation. The historical
`ofw_verified:false` field in health/export output is a fixed value, not an
automatic console attestation. PSNProfiles approval has not been obtained.
