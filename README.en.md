# media-mgmt

Chinese default → [README.md](README.md)

OpenClaw skill for **media orchestration**: identify titles, missing-episode checks, NextFind netdisk transfer, PT download, short-link parse, playlists / listen.

- Policy: `SKILL.md`
- **Install & upstream services**: `INSTALL.md`
- CLI: `python3 scripts/media_ctl.py`

Not a turnkey media appliance. Library existence and netdisk transfer use **NextFind** ([intro](https://wiki.nextemby.com/#/nextfind_intro)).

## Quick start

Follow [`INSTALL.md`](INSTALL.md) for MoviePilot, NextFind, credentials, then:

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 scripts/media_ctl.py run doctor
```

| Topic | Doc |
|-------|-----|
| Install | `INSTALL.md` |
| Routing | `SKILL.md` |
| Workflows | `references/workflows.md` |
| Netdisk / 115 | `references/nextfind-115.md` |
| Credentials | `references/credentials.md` |

Secrets only under workspace `.credentials/`. MIT · `LICENSE`
