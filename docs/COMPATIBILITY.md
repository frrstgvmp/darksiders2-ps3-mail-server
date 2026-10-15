# OFW compatibility

**English** · [Русский](COMPATIBILITY.ru.md)

Updated: 2026-10-15. Results are player-reported unless specified otherwise.

| Edition | Disc / TITLE_ID | Mailbox | Sending / inventory receipt | Pay It Forward |
| --- | --- | --- | --- | --- |
| Europe | **BLES01597** | Confirmed | Both reported | Reported, October 14 |
| Japan | **BLJS10199** | Not verified on OFW | Not verified on OFW | Not verified on OFW |
| Asia | Not recorded | Pending | Pending | Pending |
| USA | Not recorded | Pending | Pending | Pending |

The European player described the firmware as the latest official version;
its exact number and game update were not recorded. [Evidence](STATUS.md).

`TomeGiftJP` is implemented for the Japanese mailbox separately from
`TomeGift`. Its implementation does not establish Japanese OFW compatibility
or cross-region delivery. No automatic transfer between these documents occurs.

Record the disc code or `TITLE_ID` from `PS3_GAME/PARAM.SFO`, and `APP_VER`
from the applied game update. A folder name is not authoritative. Disc IDs
are distinct from PSN service IDs: the observed European client uses
`UP1005-BLUS30829_00`, which does not establish a BLUS30829 disc test.

## Report format

```text
Date/time and timezone:
Disc code / TITLE_ID:
Game update / APP_VER:
Exact OFW version:
Original client and stock certificate store confirmed:
Server address / release:
PSN sign-in / inbox opening:
Sending confirmation / item removed:
Attachment claimed / item added to inventory:
Save and restart result:
Pay It Forward absent before test / unlocked / already owned:
Other participant's edition:
Error text and time, if applicable:
```

Do not include tickets, credentials, console identifiers or player databases.
