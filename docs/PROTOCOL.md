# Protocol

Implemented THQ Connect subset for Darksiders II PS3.

## Transport

- Cloud: `thqc-darksiders2-ps3-na.thqconnect.com:8443`.
- GDS: `ds2.gds.thqconnect.com:443`; application API unsupported.
- Mail: `GET` or form-encoded `POST /thqconnect/cloud/execute`.
- Required values: `version=1`, `platform=PS3_PSN`, `title=Darksiders2`.
- Query and POST fields are combined; duplicate required parameters are rejected.

The experimental TLS chain uses intermediate signature OID
`1.3.6.1.4.1.55555.123`. It is not publicly trusted; client acceptance is not
established for every firmware or newly generated chain. DNS redirection does
not remove hostname or certificate requirements.

## Authentication

Cloud requests require one base64 PSN ticket in `auth` when verification is
enabled. Public mode always enables verification. Health and news are public reads.

The verifier checks the ECDSA signature, signed account/profile, game service,
issue time and expiry. Protocol algorithms: secp192r1 and SHA-1.
Supported signer: `4ca0c71d`. Service: `UP1005-BLUS30829_00`.
The bundled key is public verification material, not a private signing key.
Service IDs do not identify the disc region. Key rotation or another service
requires an explicit verification-key configuration.

Invalid authentication returns HTTP 403. Authenticated unsupported or denied
operations, invalid batches and quota failures return HTTP 503. HTTP 200 is
sent after database commit. GDS and THQ login/SSO remain unsupported.

## Mail operations

`profileNames`, `ops`, `docKeys`, `keys` and `values` are aligned comma-separated
vectors. Preserve empty positions; commas inside values are not escaped.
A batch contains 1–64 operations. `policy`, `worldPerms` and `friendPerms` may
be scalar or aligned vectors.

Profiles are `/psn/` followed by 1–32 ASCII letters, digits, underscores or
hyphens, normalized to lowercase. Documents: `TomeGift`, `TomeGiftJP` and
`GameToWeb`. Japanese and international gift documents are separate.

| Operation | Behavior |
| --- | --- |
| `GET` | Return document map and metadata |
| `SET` with empty value | Initialize metadata; preserve queued gifts |
| `SET` with JSON object | Replace map; denied for authenticated gift documents |
| `REMOVE` | Remove own document |
| `MAP_GET` | Return all entries with sender/time metadata |
| `MAP_SET` | Store a value; cross-profile gifts are append-only |
| `MAP_REMOVE` | Remove own key; missing keys succeed |
| `SET_PERM` | Store policy metadata |

The signed account is bound to its profile on first use. Owners may read and
remove their gifts. Other accounts may append new gifts but cannot read or
delete recipient mail. Identical retries succeed; conflicting gift keys fail.
Cross-profile responses contain only the sent entry. Friendship and permission
bits are not checked against PSN. Online ID changes require operator handling.

Gift payloads remain unchanged. Validation checks bounded base64/BOD envelopes,
not full equipment semantics. The server does not generate items or invoke trophy
APIs. The client downloads gifts to local storage and removes their cloud keys
before inventory claim; cloud removal alone does not establish item receipt.

## Response format

Version 1 uses positional JSON. Empty document:

```json
[0, [[0, "{}", 0, 0, ""]]]
```

Outer fields: `[resultCode, documents]`. Document fields:
`[status, documentJsonString, policyBits, modifiedSeconds, modifiedBy]`.
A nonempty `MAP_GET` encodes this array inside `documentJsonString`:

```json
[["gift-id", ["opaque-base64", "/psn/sender", 0]]]
```

An entry is `[key, [value, sender, modifiedSeconds]]`. Timestamps use Unix
seconds. The original reader uses positional arrays and signed 32-bit time.

## News

`GET /thqconnect/news/getNews` requires the same version/platform/title values.
Optional `limit` is 0–32, default 32; `language` defaults to English.

```json
[0, [["COMMUNITY SERVER", "Announcement text", "Full body", 0]]]
```

Entry fields: `[prefix, title, body, datePosted]`. Invalid query: HTTP 400;
invalid configured feed: HTTP 503. [Configuration](CONFIGURATION.md#news).

## Storage

SQLite tables: `documents`, `map_metadata` and `profile_owners`.
Batches are validated before mutation, executed under `BEGIN IMMEDIATE` and
committed atomically. Failures roll back the batch. Per-key sender/time metadata
survives identical retries and document initialization. Backups use SQLite's
backup API rather than copying a live database file.
