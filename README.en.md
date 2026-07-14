# media-mgmt

[中文文档](README.md)

Cross-service media orchestration skill: MoviePilot + HDHive/115 + short video + music + playlist parse + doctor.  
Agent entrypoint is **`SKILL.md` + `scripts/media_ctl.py`**.

> Automation glue only. No credentials, cookies, sessions, or media files ship in this repo.

## When to use

| User intent | Workflow |
|-------------|----------|
| Watch / episode N | `run watch` |
| Missing episode / any updates? | `run updates` |
| In library? | `run library` |
| Cloud transfer / 115 / HDHive | `run hdhive` |
| Douyin/Bilibili/TikTok/Hongguo link | `run link` |
| Listen/download song | `run listen` |
| Public playlist URL | `run playlist` |
| Health check | `run doctor` |

Boundary vs `moviepilot-cli` / `moviepilot-api`: natural-language orchestration → this skill; raw MoviePilot-only API work → those skills.

## Control plane

```bash
python3 scripts/media_ctl.py list
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run watch --param title=TITLE --param episode=5 --param dry_run=true
python3 scripts/media_ctl.py run updates --param title=TITLE
python3 scripts/media_ctl.py run hdhive --param tmdbid=ID --param media_type=movie --param transfer=true
```

- Fixed scenarios → `run <workflow>`
- Free composition → `call <service> <op>`
- Strategy → `references/workflows.md`
- Exact commands → `references/commands.md`

## Layout

```text
SKILL.md                 agent entry (kept lean)
config.example.json      config template
references/              load-on-demand docs
scripts/media_ctl.py     control plane
media_mgmt_lib/          catalog + ops + workflows + providers
services/*.json          service catalog (no secrets)
tests/
```

## Config

```bash
cp config.example.json config.json
```

Sections: `pansou`, `moviepilot`, `hdhive`, `telegram_music`, `douyin`, `bilibili`, `playlist`, `hongguo`.  
`config.json` is gitignored.

## Dependencies

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
```

Optional backends: MoviePilot (+P115StrmHelper), CloakBrowser, 7899 short-video API, Telegram session, pan search.

## Install

```bash
git clone https://github.com/wenrouXN/media-mgmt.git media-mgmt
cd media-mgmt && cp config.example.json config.json
```

Smoke: `python3 scripts/media_ctl.py workflows` · `pytest -q`.

## License

MIT. See [LICENSE](LICENSE).
