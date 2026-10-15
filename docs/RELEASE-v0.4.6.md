# v0.4.6 — PS3 OFW mailbox server

Source pre-release for the Darksiders II PS3 THQ Connect mailbox service.

- DNS redirection for configured THQ hosts, UDP/TCP DNS.
- Primary DNS `193.232.178.202`; secondary `1.1.1.1` is a reported working configuration.
- HTTPS Cloud API with PSN ticket signature and lifetime verification.
- Persistent SQLite gift maps, per-entry sender metadata and atomic batches.
- Owner-only reads/deletes; signed cross-profile append; quotas and rate limits.
- Separate `TomeGiftJP` support; Japanese OFW verification pending.
- Debian/systemd installer, daily backups, English documentation.

OFW/BLES01597: players reported mailbox access, sending, inventory receipt
and Pay It Forward. Exact firmware/update values were not recorded.
Other editions and cross-region delivery are unverified.

The TLS chain is experimental and not publicly trusted. Generated material
requires an OFW client check. Operational keys and player data are not included.
GDS, THQ login/SSO, news, PSN friendship checks and full item validation are
not implemented. No PSNProfiles approval has been obtained.

Validation: 33 automated tests. They do not establish firmware compatibility.
