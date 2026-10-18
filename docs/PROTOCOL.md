# Mailbox protocol and implementation

This document describes the implemented subset, not a complete THQ Connect specification. Examples use dummy profile names and omit authentication tickets.

## Routing and transport

Exact configured THQ names receive the configured server IPv4 in DNS A replies and an empty successful AAAA reply. Other ordinary IN-class record lookups are forwarded for all domains, including reverse DNS, TXT and SRV. Public mode refuses reserved/meta query types, ANY and zone transfers as listed in [PUBLIC-SERVER.md](PUBLIC-SERVER.md). Both UDP and TCP are served with bounds/rate limits. Private mode also restricts source IPv4s. HTTPS peer/rate checks precede bounded worker TLS processing.

Observed Cloud hostname: `thqc-darksiders2-ps3-na.thqconnect.com:8443`. The examined European game and Japanese BLJS10199 also used this NA host. Other regions require a client trace; adding a DNS redirect alone does not add the hostname to the certificate. GDS uses `ds2.gds.thqconnect.com:443`; its protocol is outside the mailbox implementation.

`GET` and form-encoded `POST` are supported at `/thqconnect/cloud/execute`. Required parameters are `version=1`, `platform=PS3_PSN`, `title=Darksiders2`. Public mode requires exactly one base64 `auth` ticket, verifies its signature against the pinned public PSN key, and checks identity, game service and expiry. Private mode may enable the same checks with `verify_psn_tickets:true`. Authentication failure returns403; health is anonymous. POST fields and query fields are combined; duplicate required parameters are rejected. The collector accepts Content-Length bodies up to 64 KiB in public mode (512 KiB in private research mode), not chunked encoding.

## Operations and batches

`profileNames`, `ops`, `docKeys`, `keys`, and `values` are aligned comma-separated vectors. Empty positions must be preserved. A batch contains 1–64 operations. Optional `policy`, `worldPerms`, `friendPerms` may be scalar or aligned vectors. This limited representation does not escape commas inside individual batch values.

Profiles are `/psn/` followed by 1–32 ASCII letters, digits, underscores or hyphens and are stored lowercase. Supported documents are `TomeGift`, `TomeGiftJP` (Japanese BLJS10199 mailbox), and `GameToWeb`. The two gift documents are separate namespaces with identical authorization, envelope checks, retry rules and quotas. Gifts are not automatically copied or forwarded between them; cross-region delivery is not established.

| Operation | Implemented behavior |
|---|---|
| `GET` | Return full document map and metadata |
| `SET` with empty value | Initialize/update metadata, preserve queued entries |
| `SET` with JSON object value | Replace map; string values; authenticated gift-document replacement denied |
| `REMOVE` | Remove whole document |
| `MAP_GET` | Return full map as SDK entry array with per-key sender/date; keyed reads not implemented |
| `MAP_SET` | Store opaque value under nonempty key; authenticated gifts append with envelope/quota checks |
| `MAP_REMOVE` | Remove key, idempotent when missing |
| `SET_PERM` | Update stored policy metadata |

GET/SET, MAP_GET/MAP_SET and MAP_REMOVE requests were observed. The client downloads gift blobs into local storage and automatically removes the corresponding cloud keys; this precedes inventory acceptance. A MAP_REMOVE alone does not prove the player took the item. REMOVE and SET_PERM are supported server operations, not claimed as observed game flows. Friendship/world permission bits are accepted but not enforced against PSN. In authenticated mode `modified_by` records the signed sender; legacy unauthenticated research mode records the target profile.

The server validates the entire batch before changing the database. It executes changes under SQLite `BEGIN IMMEDIATE` and commits before responding. Later execution failures roll back earlier changes. Empty reads return an empty map. Gift values are stored unchanged. Authenticated mode checks bounded base64/BOD envelopes, not complete item semantics; it does not synthesize contents. Full-document removal is restricted to the signed owner; nonempty `SET` replacement of either gift document is denied in authenticated mode. Empty initialization preserves entries. A sender may append a new gift to another profile but cannot read/delete its gifts. Existing gift keys accept only identical retries. Cross-profile responses return just the sent entry, not the recipient map. Account/profile associations prevent ownership takeover. Bounded quotas apply and roll back the whole batch on failure; see [PUBLIC-SERVER.md](PUBLIC-SERVER.md).

## Version 1 response

The response is positional JSON, with the document itself encoded as a JSON string:

```json
[0, [[0, "{}", 0, 0, ""]]]
```

Outer array: `[resultCode, documents]`. Each document: `[status, documentJsonString, policyBits, lastModifiedSeconds, lastModifiedProfileName]`. The empty inbox response above is 22 bytes including its newline and was accepted in game. GET returns the stored compact map; a nonempty MAP_GET returns a serialized SDK entry array and outer document metadata. Cross-profile gift append returns only the sent entry and sender-operation metadata. Timestamps use Unix seconds; the original reader is signed 32-bit.

A gift request has `ops=MAP_SET`, `docKeys=TomeGift` (or `TomeGiftJP` for the observed Japanese client), the recipient in `profileNames`, an opaque gift identifier in `keys` and the game's base64-like payload in `values`. The payload is saved unchanged. An HTTP 200 is sent only after commit. Storage and protocol checks are covered by automated tests. OFW results are recorded in [STATUS.md](STATUS.md).

Authenticated unsupported/denied requests receive HTTP 503 from the collector; invalid/missing tickets receive403. Authentication runs before mailbox operations. This includes login/platformLogin, login/ssoStatus, news/getNews, GDS and unrecognized cloud operations. A 503 does not automatically mean TLS failed: TLS and application errors must be distinguished in traces.

## Database

SQLite table `documents`:

```sql
CREATE TABLE documents (
  profile TEXT NOT NULL,
  name TEXT NOT NULL,
  data TEXT NOT NULL,
  policy INTEGER NOT NULL,
  modified INTEGER NOT NULL,
  modified_by TEXT NOT NULL,
  PRIMARY KEY (profile, name)
);
```

`documents.data` remains compact JSON mapping keys to unchanged opaque strings. MAP_GET serializes nonempty maps for the original version-1 SDK as follows (this array is placed inside the outer document JSON string):

```json
[["gift-id", ["opaque-base64", "/psn/sender", 1700000000]]]
```

Each entry is `[key, data]`; data is `[value, lastModifiedName, lastModifiedDate]`. Version 1 reads positions, so labelled objects cannot substitute for these arrays. An empty map retains the already-tested `"{}"` representation. A letter without Gift/Items has no attachment to claim.

Per-key metadata is stored separately in `map_metadata(profile,name,key,modified,modified_by)` with a composite primary key. Legacy entries inherit the original document metadata on first access, before any initialization changes it. New writes record their signed sender/date. Identical gift retries and empty initialization preserve per-key metadata; removal deletes corresponding metadata transactionally. The service opens a connection per batch and serializes local operations. Transactions also prevent lost writes between independent store instances. The backup tool uses SQLite's backup API rather than copying a live file.

Authenticated mode adds:

```sql
CREATE TABLE profile_owners (
  profile TEXT PRIMARY KEY,
  account_id TEXT NOT NULL
);
```

The owner is inserted transactionally on first authenticated use. Another account claiming an already-bound profile is rejected. PSN Online ID changes/deletion requests currently require an operator procedure; there is no migration web endpoint. Existing private research documents remain stored, while subsequent signed operations use the access policy above.
