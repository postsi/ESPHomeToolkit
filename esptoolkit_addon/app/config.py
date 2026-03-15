"""Load add-on configuration from Supervisor options."""
import json
import os
import secrets
from pathlib import Path

OPTIONS_PATH = Path("/data/options.json")
TOKEN_FILE = Path("/data/esphome_api_token")
SETUP_COMPLETE_PATH = Path("/data/esphome_api_setup_complete")
CONFIG_ESPHOME = Path("/config/esphome")
DATA_DIR = Path("/data")


def load_options() -> dict:
    """Single source for api_token: Configuration (options) wins when set; else saved file; else auto-generate once."""
    opts = {}
    if OPTIONS_PATH.exists():
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            opts = json.load(f)
    else:
        opts = {
            "api_token": os.environ.get("ESPHOME_API_TOKEN", ""),
            "port": int(os.environ.get("ESPHOME_API_PORT", "8098")),
        }
    token_from_options = (opts.get("api_token") or "").strip()
    if token_from_options:
        opts["api_token"] = token_from_options
        if not TOKEN_FILE.exists() or TOKEN_FILE.read_text().strip() != token_from_options:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(token_from_options)
        return opts
    if TOKEN_FILE.exists():
        opts["api_token"] = TOKEN_FILE.read_text().strip()
        return opts
    token = secrets.token_urlsafe(32)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    opts["api_token"] = token
    return opts


def regenerate_token_and_save() -> str:
    """Generate a new token and overwrite TOKEN_FILE. Caller must restart add-on and warn user to update Cursor."""
    token = secrets.token_urlsafe(32)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    return token


def get_setup_complete() -> bool:
    """Whether user has marked setup as complete (stored in /data, not options)."""
    return SETUP_COMPLETE_PATH.exists() and SETUP_COMPLETE_PATH.read_text().strip() == "1"


def set_setup_complete(complete: bool) -> None:
    """Persist setup-complete flag in /data."""
    if complete:
        SETUP_COMPLETE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETUP_COMPLETE_PATH.write_text("1")
    elif SETUP_COMPLETE_PATH.exists():
        SETUP_COMPLETE_PATH.unlink()


def get_esphome_config_dir() -> Path:
    """Directory where ESPHome YAML configs live (same as native HA add-on)."""
    CONFIG_ESPHOME.mkdir(parents=True, exist_ok=True)
    return CONFIG_ESPHOME


def get_options_path() -> Path:
    """Path to options file for reading/writing setup_complete."""
    return OPTIONS_PATH
