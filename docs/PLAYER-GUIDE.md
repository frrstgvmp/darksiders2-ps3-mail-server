# Player setup

Server IPv4: **193.232.178.202**. Updated: 2026-10-18.
[OFW compatibility](COMPATIBILITY.md).

1. Keep the existing IP, subnet and working gateway.
2. Set primary DNS to `193.232.178.202`. The existing secondary DNS can remain; `1.1.1.1` has been reported working. For troubleshooting, set both entries to `193.232.178.202`.
3. No proxy is required. Sign in to PSN and restart the game.
4. Open the network inbox in the Tome.

Both players must use this server. Only configured game hosts are redirected;
ordinary lookups for other domains are forwarded to the upstream resolver.
A public secondary DNS does not know the redirects. If the console uses that
secondary, it may reach the original game addresses instead. DNS interception
by a router or VPN can override even manually entered DNS addresses.

For sending, select a recipient, select an item and execute **Add item to gift**.
Verify the attachment before sending. Message text is optional. Check that the
item leaves the sender's inventory after successful sending.

For receiving, check network mail, select the letter and use **Take All** or
the individual attachment action. Check inventory. A letter without an attachment
may offer only Delete. The text may remain after the item is taken.

Save the game and wait for the write to complete before exiting. Downloaded
letters are also stored locally; deleting them without saving can restore the
previous local state on the next load. Automatic saving after every mailbox
action has not been established.

For a fresh Pay It Forward check, use a profile without the trophy. Record the
exact firmware, disc ID and game update. The game handles the trophy; the
server provides mailbox responses.

If connection fails, report the error text and time to the operator. Do not
post PSN tickets or credentials. Keep an existing VPN route if PSN depends on it.

## Windows connection checks

On a computer on the same network as the PS3, open Command Prompt or PowerShell:

```text
nslookup -type=A thqc-darksiders2-ps3-na.thqconnect.com 193.232.178.202
nslookup -type=A www.playstation.com 193.232.178.202
```

The answer for the game hostname must contain `193.232.178.202`. The PlayStation
website should return its ordinary addresses, not the game server address.
`Server: Unknown` by itself only means that the DNS server's reverse name was
not found; check the hostname answer below it.

In PowerShell, also check the mailbox port:

```powershell
Test-NetConnection 193.232.178.202 -Port 8443
```

`TcpTestSucceeded: True` confirms TCP reachability, not game TLS acceptance or
PSN authentication. Send the operator the results, disc code, error text and
attempt time with time zone. A PC test describes that PC's route; the PS3 may
use a different router/VPN policy.
