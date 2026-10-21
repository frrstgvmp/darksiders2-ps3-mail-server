# Configuration

Docker uses `.env` for host networking/UID settings and `config/config.json`
for the service. `setup.sh` initializes defaults once and preserves existing
files. `BIND_IP` must belong to the Docker host; use a local interface address
for provider NAT. `PUBLIC_IP` must match `public_ip` in the service config.
Container `listen` is `0.0.0.0`, `state_dir` is `/data`, and TLS/news paths are
relative to `/config`. DNS and HTTPS port publishing is defined in `compose.yaml`.

Examples: [public](../deployment/config.public.example.json) and
[restricted](../deployment/config.example.json).
Paths are resolved relative to the configuration file unless absolute.

## Service

| Setting | Purpose |
| --- | --- |
| `listen` | Local interface IPv4 |
| `public_ip` | IPv4 returned for redirected game hosts |
| `dns_upstream` | Resolver for ordinary DNS queries |
| `dns_ports` | DNS listeners; default `[53]`, UDP and TCP |
| `https_ports` | HTTPS listeners; default `[443, 8443]` |
| `redirect_hosts` | Exact THQ hostnames to redirect |
| `cloud_cert`, `cloud_key` | TLS chain and matching private key |
| `gds_cert`, `gds_key` | Optional separate TLS material for GDS |
| `state_dir` | SQLite and application logs directory |
| `public_mode` | Accept all client IPv4 addresses with mandatory PSN authentication |
| `allowed_clients` | IPv4/CIDR allowlist for restricted mode; `/32` recommended |
| `verify_psn_tickets` | Enable signed-ticket verification; always enforced in public mode |
| `capture_raw` | Raw request capture; must be `false` in public mode |
| `psn_key` | Optional verification-key file; defaults to the bundled public key |
| `news_file` | Optional community-news JSON file |

Public mode ignores `allowed_clients`. Restricted mode requires a nonempty
allowlist. Keep ticket verification enabled on Internet-facing deployments.
The service needs an accurate system clock for ticket lifetime validation.

## DNS

Configured game hosts return the server IPv4 for A and an empty successful
AAAA response. Other ordinary IN-class queries are forwarded to `dns_upstream`.
UDP replies are limited to 512 bytes; larger answers require TCP retry.
Public mode refuses non-IN classes, ANY, zone transfers and reserved/meta
query types 0, 41 and 249–255.

## News

The main-menu ticker renders `prefix` as a red label and `title` as the scrolling
message. Put the visible announcement in `title`; `body` is not shown by this
ticker. Color and layout are controlled by the game.

```json
{
  "items": [
    {
      "prefix": "COMMUNITY SERVER",
      "title": "Network mail and gifts are available.",
      "body": "Network mail and gifts are available.",
      "datePosted": 0,
      "translations": {
        "Russian": {
          "title": "Сетевая почта и подарки доступны.",
          "body": "Сетевая почта и подарки доступны."
        }
      }
    }
  ]
}
```

Translations match the request's `language` value case-insensitively and may
override `prefix`, `title` and `body`. Unmatched languages use the base text.
Posts are sorted by `datePosted` descending. Use Unix seconds between 0 and
2147483647; zero is valid for a static announcement.

The file is read on every request. Replace it atomically after editing.
The game caches news; restart it for a fresh check. Missing `news_file` returns
an empty successful feed. A missing or invalid configured file returns HTTP 503
for news without disabling the mailbox. `--check` validates the file.

Limits: 32 posts, 128 KiB file, 64 UTF-8 bytes for prefix, 256 for title and 4096
for body. Use plain text. Control characters are rejected except newline/tab
in body. No remote news-editing endpoint is exposed.

## Resource limits

| Resource | Default |
| --- | --- |
| HTTPS connections | Per IP 5/s, burst 20; global 40/s, burst 80 |
| HTTPS workers | 32 total, 8 per IP; 10-second timeout |
| Public request body | 64 KiB; no chunked encoding |
| DNS requests | Per IP 20/s, burst 60; global 300/s, burst 600 |
| DNS TCP clients | 32 per listener, 4 per IP |
| Signed mutations | Per account 1/s, burst 10; global 20/s, burst 40 |
| Operations per batch | 64 |
| Decoded gift payload | 32 bytes–32 KiB |
| Encoded value / document | 64 KiB / 512 KiB |
| Gifts per mailbox | 128 |
| Document payloads / documents / profile owners | 64 MiB / 20,000 / 20,000 |

Limits are code defaults. Quota failures roll back the batch. Payload limits
exclude SQLite journals, backups and filesystem overhead. Shared public IPs
share connection/DNS limits.

Logs redact authentication tickets, profile names and payloads but retain IPs
and endpoint metadata. File logs rotate at 5 MiB with three backups; systemd
journal retention is separate. The database and its backups contain player data.
