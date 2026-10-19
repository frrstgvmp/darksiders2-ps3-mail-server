# Darksiders II PS3 Mail Server

Self-hosted THQ Connect mailbox service for Darksiders II on PS3 OFW.
DNS redirection, signed PSN ticket verification and persistent gift storage.

## Status

OFW/BLES01597: mailbox access, gift sending, receipt into inventory and
Pay It Forward were reported by a player on October 14–15, 2026. The exact
firmware number and game update were not recorded. Other editions require
separate OFW verification. [Compatibility](docs/COMPATIBILITY.md).

The service stores game-generated gift payloads unchanged. It does not edit
saves or invoke trophy APIs. Trophy handling remains in the game.

## Connect

1. Set primary PS3 DNS to **193.232.178.202**. The existing secondary DNS can remain; `1.1.1.1` has been reported working. For troubleshooting, use **193.232.178.202** for both entries.
2. Keep the working gateway. Disable any unnecessary network proxy.
3. Sign in to PSN and restart Darksiders II.
4. Open the network inbox. Both participants must use this server.

No client executable replacement or console certificate installation is
required for the reported OFW configuration. The current server address is
operator-provided and may change. [Player guide](docs/PLAYER-GUIDE.md).

The DNS service redirects only configured game hosts and forwards ordinary
lookups for all other domains. A public secondary DNS does not provide the
game redirects; if the console switches to it, the game may reach the original
addresses. Router/VPN DNS interception can also override the console settings.

## Implementation

| Component | Behavior |
| --- | --- |
| DNS | UDP/TCP; redirects configured THQ names and forwards other ordinary DNS lookups |
| HTTPS | Cloud API on port 8443; experimental certificate chain |
| Authentication | PSN ticket signature, service, identity and lifetime verification |
| Storage | SQLite; atomic batches and commit before successful response |
| Gifts | Owner reads/deletes; another signed user may append a new entry |
| Operations | GET, SET, REMOVE, MAP_GET, MAP_SET, MAP_REMOVE, SET_PERM |
| News | Public read-only version-1 feed; configurable community posts and translations; main-menu prefix/title display confirmed in a player screenshot |

GDS and THQ account login/SSO are not implemented. PSN friendship and
full item semantics are not validated. Japanese `TomeGiftJP` is implemented
as a separate mailbox; Japanese OFW and cross-region delivery are unverified.

## Deploy

Debian 13, Python 3.10+, systemd, public IPv4 and `python3-cryptography`.
Open UDP/TCP 53 and TCP 443/8443. Follow [installation](docs/INSTALL.md).

The deployment uses an experimental chain with an unknown intermediate
signature algorithm. It is not publicly trusted. A newly generated chain
requires an OFW client check; acceptance on every firmware is not established.
The release contains a public root certificate and generator, not operational
private keys, player databases or game files.

## Documentation

- [Installation](docs/INSTALL.md)
- [Protocol](docs/PROTOCOL.md)
- [Public access and limits](docs/PUBLIC-SERVER.md)
- [Community news](docs/NEWS.md)
- [Compatibility](docs/COMPATIBILITY.md)
- [Verification status](docs/STATUS.md)
- [Release procedure](docs/PUBLISHING.md)
- [Third-party notices](NOTICE)

## Validation

```bash
sudo apt-get install python3-cryptography
python3 -m unittest discover -s tests -v
```

Automated tests cover ticket
verification, permissions, quotas, Japanese mailbox operations, persistence,
concurrency, DNS, routing and log redaction. Local TLS tests isolate API
behavior and do not establish OFW compatibility.

Original project code and documentation: MIT. Third-party public certificate
and key provenance: [NOTICE](NOTICE). Independent project; no affiliation with
Sony or THQ Nordic. No PSNProfiles approval has been obtained.
