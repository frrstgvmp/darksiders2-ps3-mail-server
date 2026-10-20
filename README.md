# Darksiders II PS3 Mail Server

THQ Connect replacement for the Darksiders II network inbox on PS3.
Supports gift delivery, community news and the original Pay It Forward flow.

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

The server preserves item data. Trophies and inventory changes are handled
by the game.

## Compatibility

| Edition | Status |
| --- | --- |
| Europe — BLES01597 | OFW inbox, item transfer and Pay It Forward supported |
| USA — BLUS30829 | Connection and inbox checked; stock OFW verification pending |
| Japan — BLJS10199 | Separate mailbox implemented; OFW verification pending |

Other firmware and game-update combinations require verification.
Japanese and international mailboxes are separate; cross-region delivery is unverified.

## Hosting

Requirements: Debian 13, Python 3.10+, `python3-cryptography`, systemd and a
public IPv4 address. Open UDP/TCP **53** and TCP **443/8443**.

Follow [Installation](docs/INSTALL.md) to generate TLS material and install the
service. DNS, HTTPS and SQLite storage run in one process.

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
