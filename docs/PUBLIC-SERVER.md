# Public hosting and authenticated mailbox access

## Modes

`public_mode:true` accepts all source IPv4 addresses without registration. Every cloud request must contain one valid, unexpired signed PSN ticket. `allowed_clients` is ignored for access in this mode; it may be retained for rollback. `capture_raw:true` is rejected. Use [config.public.example.json](../deployment/config.public.example.json), replace example addresses and provide local TLS material.

Private mode (`public_mode:false`) requires a nonempty explicit IPv4 allowlist. `verify_psn_tickets:true` keeps the same authentication/permissions; false is a legacy local-research setting and must not be exposed publicly. The exporter supports `--public`, or repeated `--client` entries for private mode. The installed config is preserved during upgrades; review `config.json.new` rather than assuming an upgrade switched modes.

## Identity and public-key provenance

The independent Python verifier implements the published [NP ticket format and ECDSA signature description](https://github.com/LBPUnion/ProjectLighthouse/blob/main/Documentation/Tickets.md): secp192r1 with SHA-1. These are properties of the original protocol, not newly chosen authentication algorithms.

The pinned verification point in `assets/psn-darksiders2-key.json` was recovered offline from three independently issued operator-owned tickets. All three selected the same point and verified with cryptography; changed signed bytes were rejected. This process derives a public key, not Sony's private key. Runtime requests never recover/install keys. Captures and recovery inputs are excluded from the release.

Supported signer identifier: `4ca0c71d`. Supported game service: `UP1005-BLUS30829_00`, observed with European BLES01597 update 1.02 using the NA Cloud host. Other regions/services or key rotation need explicit new evidence and an operator-reviewed public key configuration; arbitrary service IDs are not accepted.

Expiry, issue time (five-minute future clock tolerance), account identity, signed profile and key/service identity are verified. Duplicate tickets, invalid base64/DER, nonzero signature padding and tampered signatures are refused. Fixed-width signature padding may contain varying numbers of zero bytes; the strict DER signature is still cryptographically verified over the original signed prefix. The VPS clock must be correct. Cache: at most 2048 verified ticket hashes, with expiry rechecked.

## Mailbox permissions

The signed account is bound to its profile on first authenticated use. It may read/change its own `TomeGift`, `TomeGiftJP` and `GameToWeb`. It may append a new `MAP_SET` entry in either gift document to another recipient; its response contains only that sent entry, not other gifts. A different value under an existing gift key is rejected; identical retries are idempotent. The server commits before success.

Another player's reads, deletions and whole-mailbox replacement are denied. Nonempty whole-document `SET` for either gift document is denied in authenticated mode; empty initialization preserves gifts. Friendship/world/friend permission bits are not validated against PSN. Gift payloads must be bounded valid base64 with the observed BOD marker, but the server does not fully decode/validate equipment or invent rewards. OFW results: [STATUS.md](STATUS.md).

## Current resource limits

| Resource | Limit |
|---|---|
| HTTPS accepted connections | Per IP 5/s, burst 20; global 40/s, burst 80 |
| Pending HTTPS workers | 32 shared across listeners; at most 8 per IP; 10-second socket timeout |
| Public request body | 64 KiB; no chunked encoding |
| DNS requests | Per IP 20/s, burst 60; global 300/s, burst 600 |
| DNS TCP clients | 32 per listener, at most 4 per IP; bounded requests/idle time |
| DNS UDP answer | 512 bytes, then TC and TCP retry |
| Signed mailbox mutations | Per account 1/s, burst 10; global 20/s, burst 40 |
| Operations per batch | 64 |
| Gift decoded payload | 32 bytes–32 KiB, observed `BOD` marker |
| Value/document | 64 KiB value; 512 KiB document |
| Gift entries per mailbox | 128 |
| Database document payload / documents / profile owners | 64 MiB total / 20,000 / 20,000 |

These are code defaults, not a capacity guarantee. Quota failure rolls back the batch. Storage limits cover document payloads, not total SQLite/backup/journal size. Per-IP limits may affect many consoles sharing one NAT. Monitor load/backups and adjust only with tests; provider protections handle network-level floods.

## DNS and operator checks

Public DNS permits only IN A/AAAA within `playstation.net`, `playstation.com`, `ndmdhs.com`, `thqconnect.com`. Exact configured THQ hosts resolve to this server. Other permitted game/PSN queries are forwarded; arbitrary Internet names and ANY/TXT/etc. return REFUSED. It is unsuitable as a household general-purpose resolver.

Open UDP/TCP 53 and TCP 443/8443 for players. Optional UDP/TCP 1053 supports a routing workaround and is not entered in normal PS3 settings. Verify from a second network: game A redirect, PSN A forwarding, unrelated name/ANY refusal, anonymous health 200 and anonymous cloud 403. Use actual gameplay to check signed read/send, then recipient claim. The legacy health field `ofw_verified:false` is not a live gameplay test. Current player-confirmed OFW transfer/receipt and trophy evidence, with its scope and remaining checks, is recorded in [STATUS.md](STATUS.md).
