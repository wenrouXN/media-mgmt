import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_declares_runtime_and_test_dependencies():
    requirements = ROOT / "requirements.txt"
    assert requirements.exists()
    packages = {
        line.strip().lower()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert {"telethon", "python-dotenv", "websockets", "pytest"} <= packages


def test_gitignore_excludes_local_virtualenv():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".venv/" in {line.strip() for line in gitignore}


def test_config_json_is_owner_only_readable_and_writable():
    mode = stat.S_IMODE((ROOT / "config.json").stat().st_mode)
    assert mode == 0o600
