# media-mgmt

[中文文档](README.md)

Skill for private media workflows: 115 resource search, MoviePilot transfer, HDHive unlock, MoviePilot subscription helpers, and Telegram music downloads.

> Automation glue only. This repository does not include credentials, cookies, Telegram sessions, media files, or access to third-party services.

## Features

- Search 115 resources through a configurable search service.
- Transfer 115 share links through MoviePilot `P115StrmHelper`.
- Search HDHive, list 115 resources, unlock share links, and transfer the best resource.
- Download music from a Telegram music bot via inline callback buttons.
- Provider-style layout under `media_mgmt_lib/providers/` with thin CLI wrappers under `scripts/`.

## Requirements

- Python 3.11+
- Python packages: `websockets`, `telethon`, `python-dotenv`
- Optional but recommended: `mcporter` + a configured `moviepilot` MCP server for MoviePilot search/subscription helpers
- Service accounts/access for whichever providers you enable:
  - Search service exposing `POST /api/search`
  - MoviePilot with `P115StrmHelper`
  - CloakManager profile logged into HDHive
  - Telegram user session for Telethon


## Dependencies and acknowledgements

This skill is glue code that orchestrates several backends and open-source tools. Prepare the required accounts, services, and permissions before enabling each provider.

| Dependency / project | Purpose | Prerequisite | Config |
|---|---|---|---|
| Skill-capable agent/runtime | Skill execution, tool orchestration, optional file delivery | Install this repository as a loadable skill | `SKILL.md` |
| Python / uv | Run provider scripts; `uv run` can reuse a prepared dependency environment | Python 3.11+; uv recommended | none |
| Search backend | Search 115 share resources | HTTP API exposing `POST /api/search` | `pansou.url` |
| 115 cloud drive | Share-link source and transfer target | Valid 115 share links; account/plugin capability configured on the MoviePilot side | via MoviePilot |
| MoviePilot | Media recognition, subscription, plugin host | Reachable MoviePilot service with API key | `moviepilot.base_url`, `moviepilot.api_key` |
| MoviePilot P115StrmHelper | Transfer 115 shares | Plugin installed/enabled; 115 account configured inside the plugin | `moviepilot.*` |
| mcporter / MCP | MoviePilot search/recognition/subscription helper commands | mcporter configured with a `moviepilot` MCP server | `moviepilot.mcporter_server` |
| CloakManager / CloakBrowser | CDP-controllable browser profile manager | Reachable CloakManager service; launchable profile; proxy configured if needed | `hdhive.cloak_url`, `hdhive.profile_name`, `hdhive.profile_id` |
| HDHive account | Search/view/unlock HDHive resources | Browser profile logged into HDHive; account has required permissions/points | stored in CloakManager profile |
| Telegram API / Telethon | Automate Telegram music bot interaction | Telegram API ID/hash and a user session with bot access | `telegram_music.api_id`, `api_hash`, `session_string`/`session_name` |
| Telegram music bot | Return search results and audio files | Bot is available and its inline-button protocol is unchanged | `telegram_music.bot` |

Thanks to these projects and services for the underlying capabilities. This repository only packages them into reusable Skill/provider workflows.

## Configuration

```bash
cp config.example.json config.json
```

`config.json` is ignored by git. Put all local endpoints and credentials there:

```json
{
  "pansou": { "url": "http://127.0.0.1:805" },
  "moviepilot": {
    "base_url": "http://127.0.0.1:3002",
    "api_key": "replace-with-your-moviepilot-api-key",
    "mcporter_server": "moviepilot"
  },
  "hdhive": {
    "cloak_url": "http://127.0.0.1:8080",
    "profile_name": "mdmgmt",
    "profile_id": ""
  },
  "telegram_music": {
    "api_id": 123456,
    "api_hash": "replace-with-your-telegram-api-hash",
    "session_string": "replace-with-your-telegram-session-string",
    "session_name": "",
    "bot": "@music_v1bot",
    "download_dir": "./downloads/music",
    "button_index": 1,
    "search_timeout": 20,
    "download_timeout": 30,
    "poll_interval": 1
  }
}
```

If `hdhive.profile_id` is empty, the provider auto-discovers a CloakManager profile by `hdhive.profile_name`; if only one profile exists, it uses that one. It also launches the profile before CDP access when possible.


## Install for an agent

Install or copy this repository into your agent's loadable skill directory, then create `config.json`. The agent should load this skill when the user asks to search media, transfer 115 shares, unlock HDHive resources, manage MoviePilot subscriptions, or download music.

### Prompt for an Agent AI installer

If your agent can install/sync skills from GitHub, send it this prompt:

```text
Please install this Skill:
https://github.com/wenrouXN/media-mgmt

Installation requirements:
1. Put the repository in your loadable skills directory and keep the skill name media-mgmt.
2. Read SKILL.md as the trigger entrypoint.
3. Copy config.example.json to config.json.
4. Ask me to fill the pansou, moviepilot, hdhive, and telegram_music sections in config.json.
5. Do not commit or send config.json, Telegram sessions, cookies, API keys, or downloaded media files.
6. After installation, run a minimal check: SKILL.md is readable, scripts/telegram_music_bot.py --help works, and scripts/hdhive.py prints usage.
```

### Manual install

```bash
# Enter your agent skills directory, for example:
cd /path/to/agent/skills

git clone https://github.com/wenrouXN/media-mgmt.git media-mgmt
cd media-mgmt
cp config.example.json config.json
```

Then fill `config.json` according to the Configuration section.

### Update

```bash
cd /path/to/agent/skills/media-mgmt
git pull
```

## Usage

```bash
python3 scripts/hdhive.py search "稻草人"
python3 scripts/hdhive.py resources "https://hdhive.com/tmdb/tv/292121"
python3 scripts/hdhive.py unlock "https://hdhive.com/resource/115/..."
python3 scripts/hdhive_grab.py "稻草人" --select 1
python3 scripts/telegram_music_bot.py --query "梁静茹 勇气"
```

The Telegram provider sends `/search <query>`, waits for inline buttons, then clicks the selected button using callback data. Sending text `1` is wrong for inline-keyboard results.

## License

MIT. See [LICENSE](LICENSE).
