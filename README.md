# Darksiders II PS3 Mail Server

THQ Connect replacement for Darksiders II on PS3.
Restores online mail, gift delivery and community news.

## Connect

1. Set the PS3 primary DNS to **193.232.178.202**.
2. The secondary DNS can remain `1.1.1.1`. If connection fails, use **193.232.178.202** for both entries.
3. Sign in to PSN, restart the game and open the network inbox in the Tome.

Both players must use the same server. No game patch or console certificate
installation is required for the supported OFW configuration.

A public secondary DNS does not provide the game redirects. Router or VPN
DNS interception can override the console settings. Keep the gateway that
already provides a working PSN connection.

## Gifts

Choose a recipient, select an item and use **Add item to gift** before sending.
Message text is optional. Open received mail and use **Take All** to claim its
attachments. Save the game before exiting; downloaded letters are stored locally.

A successful gift send unlocks **Pay It Forward** and displays the standard
PS3 trophy notification.

The server preserves item data. Trophies and inventory changes are handled
by the game.

## Compatibility

| Edition | Status |
| --- | --- |
| Europe — BLES01597 | Verified on OFW: inbox, gift transfer and Pay It Forward |
| USA — BLUS30829 | Verified on OFW: inbox, gift transfer and Pay It Forward |
| Japan — BLJS10199 | Verified on OFW: inbox, gift transfer and Pay It Forward |

Japanese and international mailboxes are separate; cross-region delivery is unverified.

## Hosting

Use Linux Docker Engine and Docker Compose. Open UDP/TCP **53** and TCP
**443/8443** on the server and provider firewall.

Download the [Docker bundle](https://github.com/frrstgvmp/darksiders2-ps3-mail-server/releases/download/v0.5.0/darksiders2-ps3-mail-server-0.5.0-docker-amd64.tar.gz),
extract it and run:

```bash
./setup.sh YOUR_SERVER_IP
```

The Linux AMD64 bundle includes a prebuilt image. Setup also works from source,
building the image locally. Configuration and keys stay in `config/`; mail,
logs and daily backups stay in `data/`. Repeat setup preserves existing data.
See [Installation](docs/INSTALL.md) for updates, migration and native systemd setup.

The TLS chain is experimental and is not publicly trusted. A newly generated
chain requires a console compatibility check. Preserve working keys across
updates; operational private keys are not distributed.

## Documentation

- [Installation, updates and troubleshooting](docs/INSTALL.md)
- [Configuration and news](docs/CONFIGURATION.md)
- [Protocol and authentication](docs/PROTOCOL.md)

GDS and THQ account login/SSO are not implemented. PSN friendship and complete
item semantics are not validated.

MIT license. Third-party material: [NOTICE](NOTICE).
Independent project, not affiliated with Sony or THQ Nordic.
Not approved by PSNProfiles.com.
