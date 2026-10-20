# Community news

`GET /thqconnect/news/getNews` serves operator-authored announcements using the
original client's version-1 reader. This is a public, read-only endpoint;
it does not require a PSN ticket. Cloud/mailbox operations retain signed-ticket
authentication and their existing permissions.

## Operator configuration

Set `"news_file": "news.json"` in the runtime configuration. Relative paths are
resolved against the configuration directory. The installer creates
`/etc/darksiders2-server/news.json` from [the example](../assets/news.example.json)
only if that file does not already exist. Existing operator posts are preserved.
An upgrade retains the old config; add `news_file` to it to enable announcements.
If the setting is absent or null, the endpoint returns a successful empty feed.

```json
{
  "items": [
    {
      "prefix": "Community",
      "title": "Mail server news test",
      "body": "A test announcement from the community server.",
      "datePosted": 1792357200,
      "translations": {
        "Russian": {
          "title": "Тест новостей",
          "body": "Тестовая новость сервера сообщества."
        }
      }
    }
  ]
}
```

The base strings are the fallback for unmatched languages. Translation names
match the client's `language` parameter case-insensitively. A translation can
override prefix, title or body independently. Items are sorted newest first.
Use plain text for announcements. These are community posts, not restored
historical THQ news.

The observed main-menu ticker displays `prefix` as the red label and `title`
as the scrolling message. Put the announcement message in `title` if it should
appear there; a message stored only in `body` is not visible in that ticker.
For example, use `prefix: "COMMUNITY SERVER"` and put the announcement in
`title`, with translated `title` values for localized messages. The `body`
field is still part of the protocol, but no separate body view has been
confirmed. An empty prefix removes the label; it does not promote `body` to
the visible message. Colors are controlled by the game's UI.

Limits: 32 posts, 128 KiB JSON file; UTF-8 byte limits of 64 for prefix, 256 for
title and 4096 for body. NUL/control characters are refused, with newline/tab
allowed in body. `datePosted` is a nonnegative Unix-seconds timestamp bounded
by `2147483647`; the examined reader sign-extends a 32-bit decimal conversion.

The file is read for each request. Replace it atomically after editing to avoid
a client reading a partial write. A missing/invalid configured file returns
HTTP 503 for news and logs `news_feed_failed`; mailbox service remains available,
including after a restart. `--check` validates the configured feed before an
operator deployment.

## Protocol and checks

Required query values: `version=1`, `platform=PS3_PSN`, `title=Darksiders2`.
Optional: `limit=0..32` (default 32), `language` (default English).
Duplicate/invalid required parameters return HTTP 400. Wrong paths retain their
normal routing; the news handler cannot perform mailbox mutations.

```text
https://SERVER_IP:8443/thqconnect/news/getNews?limit=32&version=1&platform=PS3_PSN&title=Darksiders2&language=English
```

The JSON response is positional, not a set of labelled objects:

```json
[0, [["Community", "Mail server news test", "Test announcement.", 1792357200]]]
```

The outer fields are result code and entry array. Each entry contains prefix,
title, body and datePosted, in that order. The empty response is `[0,[]]`.
Reader references in the examined original client: result `0x67dd8c`, entry
`0x67db24`, entry vector `0x122180c`; `version=1` is explicitly requested.

## In-game verification

On October 19, 2026 (operator local date), a player screenshot confirmed the
announcement in the bottom news ticker of the main menu: the red prefix
`Community` and the title `Mail server news test` were visible. The player
reported using OFW. The exact firmware, game update and disc code were not
recorded for this news check.

The screenshot confirms prefix and title display. Body text, date display,
Cyrillic rendering, multiple-post rotation and behavior across game editions
remain unverified. The client contains a news cache and a `News_getNews` script
binding. Restart the game for a controlled first check because cached results
may delay a fresh request. Record both the request time and visible text;
HTTP 200 alone does not prove successful rendering.
