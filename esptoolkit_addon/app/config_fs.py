"""
Safe read/write/list/delete under Home Assistant /config (add-on map: config:rw).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("esphome_api.config_fs")

CONFIG_ROOT = Path("/config")


class ConfigFsError(Exception):
    pass


def _resolve_rel(rel: str) -> Path:
    p = (CONFIG_ROOT / rel.lstrip("/")).resolve()
    try:
        p.relative_to(CONFIG_ROOT.resolve())
    except ValueError as e:
        raise ConfigFsError(f"Path escapes /config: {rel}") from e
    return p


def read_config_file(rel: str) -> str:
    path = _resolve_rel(rel)
    if not path.is_file():
        raise ConfigFsError(f"Not a file: {rel}")
    return path.read_text(encoding="utf-8", errors="replace")


def write_config_file(rel: str, content: str, validate_yaml_if_applicable: bool = True) -> None:
    path = _resolve_rel(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    if validate_yaml_if_applicable and path.suffix.lower() in (".yaml", ".yml"):
        try:
            yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ConfigFsError(f"Invalid YAML: {e}") from e
    path.write_text(content, encoding="utf-8")


def delete_config_file(rel: str) -> None:
    path = _resolve_rel(rel)
    if not path.is_file():
        raise ConfigFsError(f"Not a file: {rel}")
    path.unlink()


def list_config_dir(rel: str = "", pattern: str = "*") -> list[str]:
    base = _resolve_rel(rel) if rel else CONFIG_ROOT.resolve()
    if not base.is_dir():
        raise ConfigFsError(f"Not a directory: {rel or '.'}")
    out: list[str] = []
    for p in sorted(base.glob(pattern)):
        if p.is_file():
            try:
                out.append(str(p.relative_to(CONFIG_ROOT.resolve())))
            except ValueError:
                continue
    return out


def path_exists(rel: str) -> bool:
    return _resolve_rel(rel).exists()
