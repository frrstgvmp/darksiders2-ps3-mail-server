Docker Compose deployment for the Darksiders II PS3 mailbox server.

- One-command setup: `./setup.sh PUBLIC_IPV4`.
- Prebuilt Linux AMD64 image included; no registry account required.
- Persistent configuration, TLS keys, news, mail and daily SQLite backups.
- Non-root containers, read-only application filesystem and bounded logs.
- Existing systemd installation remains supported.

Download and extract the `docker-amd64.tar.gz` bundle, then run `./setup.sh YOUR_SERVER_IP` from its directory. Docker Engine and Docker Compose are required. Open UDP/TCP 53 and TCP 443/8443.

Updates replace the application image while preserving `config/`, `data/` and `.env`. Keep backups of all three. New experimental certificate chains require a console compatibility check; operational keys and player data are not included.

See [Installation](https://github.com/frrstgvmp/darksiders2-ps3-mail-server/blob/v0.5.0/docs/INSTALL.md).
