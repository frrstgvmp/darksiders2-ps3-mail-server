# Security and privacy

**English** · [Русский](SECURITY.ru.md)

Public mode is an experimental authenticated mailbox service. Its controls reduce abuse; they do not constitute an independent security audit or unlimited capacity.

* `public_mode:true` accepts all IPv4 peers and always requires cryptographic PSN ticket verification for mailbox operations. Health/DNS do not require a ticket. Private mode enforces `allowed_clients`; enable `verify_psn_tickets:true` there to retain authentication.
* The pinned public key is loaded from operator-controlled files. Incoming requests cannot supply or replace it. Ticket signature, service/key identity, profile/account identity, issue time and expiry are checked. Tickets are bearer credentials: a stolen valid ticket can be replayed until expiry. Only ticket hashes/principals are cached, within fixed bounds; raw tickets are not stored.
* Signed users may read/change their own profiles and append new gifts to another recipient. Other-profile reads/deletes, gift overwrites and conflicting account/profile ownership are denied. Friendship and the historical world/friend permission bits are not checked. Gift envelope checks do not establish full item semantics. Do not describe this as preventing all cheating or spam.
* Public DNS accepts only IN A/AAAA for `playstation.net`, `playstation.com`, `ndmdhs.com`, `thqconnect.com`. Other zones/types are refused. Only exact configured game hosts are redirected. DNS/HTTPS rates, pending TLS workers and storage are bounded; see [limits](docs/PUBLIC-SERVER.md). Network-level denial of service still requires provider/operator handling.
* The experimental TLS chain is invalid under normal validation. Do not reuse it elsewhere. Acceptance is scoped to the recorded OFW/game configuration; other deployments require verification.
* Public mode prohibits raw captures. Auth/email/profile/key/value query fields are redacted. Metadata logs contain source IPs and endpoint names; file rotation and systemd journal retention are separate.
* SQLite/backups contain player profile/account associations and opaque gift/statistics data. Keep them private, choose retention, restrict access and delete data on request as an operator procedure. There is no player web account or automated deletion portal.
* Keep passwords, operational configs, private keys and captures out of Git. The explicit source exporter is the release boundary; `.gitignore` alone is insufficient.

Report issues privately using the repository's private security reporting facility if enabled, otherwise contact its operator privately. Do not attach PSN tickets, keys, player databases or executable game files.

Replace an exposed server private key with newly generated material, test its client acceptance, and restart with the replacement. Rotate shared VPS login credentials interactively; never commit them. Rotating the server TLS key does not change the pinned Sony public verification key.
