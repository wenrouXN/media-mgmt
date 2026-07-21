# media-mgmt

**Status:** production OpenClaw skill · self-hosted  
Chinese default → [README.md](README.md)

Agent orchestration: identify / missing episodes / **NextFind** netdisk / PT / short-links / playlists.  
**Policy source of truth: `SKILL.md`.** CLI: `python3 scripts/media_ctl.py`.

Not a turnkey media appliance. Netdisk + library existence authority = **NextFind OpenAPI only**.

## Quick start

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run nextfind --param tmdbid=ID --param media_type=movie --param dry_run=true
python3 -m pytest -q
```

Full install, backend matrix, credentials: **[INSTALL.md](INSTALL.md)** (Chinese).

| Need | Read |
|------|------|
| Install / backends | `INSTALL.md` |
| Routing / hard rules | `SKILL.md` |
| Workflows | `references/workflows.md` |
| NextFind / 115 share | `references/nextfind-115.md` |
| Credentials | `references/credentials.md` |
| Short-links | `references/link-intents.md` |

Transfer success = `result.transfer.success` + slug. Secrets only in workspace `.credentials/`.

MIT · `LICENSE`
