# media-mgmt

中文默认 → [README.md](README.md)

**Entry for agents: `SKILL.md`** (decision table + result-reading rules).  
Control plane: `python3 scripts/media_ctl.py run|call|workflows|list`.

Do not treat this README as the policy source of truth.

```bash
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run updates --param title=Title
python3 scripts/media_ctl.py run nextfind --param tmdbid=ID --param media_type=movie --param dry_run=true
```

| Need | Read |
|------|------|
| Routing / hard rules | `SKILL.md` |
| Workflow catalog | `references/workflows.md` |
| CLI details | `references/commands.md` |
| Netdisk / 115 | `references/hdhive-115.md` |
| Credentials | `references/credentials.md` |

Boundary: natural-language orchestration → this skill; raw MoviePilot API → `moviepilot-api` / `moviepilot-cli`.

> No secrets or media in-repo. Template: `config.example.json`.
