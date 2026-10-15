# GitHub release procedure

- Account: `frrstgvmp`
- Repository: `darksiders2-ps3-mail-server`
- Candidate tag: `v0.4.6`
- Release title: `v0.4.6 — PS3 OFW mailbox server`
- License: MIT, with third-party material described in NOTICE.

Repository description:

> Darksiders II PS3 mailbox server for OFW: DNS redirection, PSN ticket verification and persistent gift storage.

Topics: `darksiders-ii`, `ps3`, `ofw`, `game-preservation`, `private-server`, `python`, `sqlite`.

## Source

```bash
python3 -m unittest discover -s tests -v
python3 deployment/export_public_source.py --out dist/darksiders2-ps3-mail-server-v0.4.6
cd dist/darksiders2-ps3-mail-server-v0.4.6
git init -b main
git add .
git diff --cached --stat
```

Only the explicit source allowlist is exported. Publish this directory,
not the research workspace or private VPS bundle. Preserve LICENSE and NOTICE.
Set your Git author identity before committing; use your GitHub-provided
noreply address if you do not want to publish a personal address.

## Repository

Create an empty public repository named `darksiders2-ps3-mail-server` under
`frrstgvmp`. Do not initialize another README or license. After review:

```bash
git commit -m "Prepare v0.4.6 source release"
git remote add origin https://github.com/frrstgvmp/darksiders2-ps3-mail-server.git
git push -u origin main
```

Authenticate through GitHub's browser/SSH/credential workflow. Do not embed
credentials in remote URLs or files. See [GitHub's source import guide](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## Release

Create a draft release targeting the reviewed commit on `main`, tag `v0.4.6`.
Use the [release notes](RELEASE-v0.4.6.md).
Mark the initial release as a pre-release while independent installation and
additional OFW editions remain pending. Attach:

- `darksiders2-ps3-mail-server-v0.4.6.tar.gz`
- `darksiders2-ps3-mail-server-v0.4.6.manifest.json`
- `SHA256SUMS-v0.4.6.txt`

The manifest contains file hashes and portable artifact names. Operational
keys, tickets, player data, captures and game binaries are excluded.
Review the draft and artifacts before publication.
[GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

## Compatibility statements

Publish only recorded OFW results. Exact firmware/update values remain
unknown where indicated. Japanese document support is not a Japanese OFW
result. Keep README, compatibility and status synchronized.
PSNProfiles approval is pending; source publication is not moderator approval.
