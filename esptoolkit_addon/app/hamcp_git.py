"""
Git backup/rollback for /config — separate git dir under /data (writable).
Mirrors Vibecode-style versioning without putting .git inside user config.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("esphome_api.hamcp_git")

GIT_DIR = Path("/data/esptoolkit_ha_git")
WORK_TREE = Path("/config")


def _git(argv: list[str], timeout: float = 120.0) -> subprocess.CompletedProcess:
    cmd = ["git", f"--git-dir={GIT_DIR}", f"--work-tree={WORK_TREE}", *argv]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_repo() -> None:
    GIT_DIR.mkdir(parents=True, exist_ok=True)
    if not (GIT_DIR / "HEAD").exists():
        r = _git(["init"], timeout=30)
        if r.returncode != 0:
            raise RuntimeError(f"git init failed: {r.stderr or r.stdout}")
        _git(["config", "user.email", "esptoolkit@local"], timeout=10)
        _git(["config", "user.name", "EspToolkit MCP"], timeout=10)


def git_commit(message: str | None) -> dict:
    ensure_repo()
    _git(["add", "-A"], timeout=120)
    msg = (message or "EspToolkit checkpoint").strip() or "EspToolkit checkpoint"
    r = _git(["commit", "-m", msg], timeout=120)
    if r.returncode != 0 and "nothing to commit" in (r.stdout + r.stderr).lower():
        return {"success": True, "message": "No changes to commit", "commit_hash": None}
    if r.returncode != 0:
        return {"success": False, "error": r.stderr or r.stdout}
    # get HEAD hash
    h = _git(["rev-parse", "HEAD"], timeout=10)
    digest = (h.stdout or "").strip() if h.returncode == 0 else None
    return {"success": True, "commit_hash": digest, "message": msg}


def git_pending() -> dict:
    ensure_repo()
    r = _git(["status", "--porcelain"], timeout=30)
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    return {
        "success": True,
        "has_changes": bool(lines),
        "lines": lines,
        "summary": {"files": len(lines)},
    }


def git_history(limit: int = 20) -> dict:
    ensure_repo()
    lim = max(1, min(limit, 200))
    r = _git(["log", f"-{lim}", "--pretty=format:%H%x09%ad%x09%s", "--date=iso"], timeout=30)
    commits = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) >= 3:
            commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
    return {"success": True, "commits": commits}


def git_diff(commit1: str | None, commit2: str | None) -> dict:
    ensure_repo()
    if commit1 and commit2:
        r = _git(["diff", f"{commit1}..{commit2}"], timeout=60)
    elif commit1:
        r = _git(["diff", commit1], timeout=60)
    else:
        r = _git(["diff"], timeout=60)
    return {"success": r.returncode == 0, "diff": r.stdout or "", "stderr": r.stderr}


def git_rollback(commit_hash: str) -> dict:
    ensure_repo()
    ch = (commit_hash or "").strip()
    if not ch:
        return {"success": False, "error": "commit_hash required"}
    r = _git(["reset", "--hard", ch], timeout=120)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr or r.stdout}
    return {"success": True, "commit_hash": ch}


def create_checkpoint(user_request: str) -> dict:
    msg = f"checkpoint: {user_request[:200]}"
    c = git_commit(msg)
    if not c.get("success"):
        return {"success": False, **c}
    digest = c.get("commit_hash")
    tag = f"checkpoint-{digest[:8]}" if digest else "checkpoint"
    if digest:
        _git(["tag", "-f", tag, digest], timeout=30)
    return {
        "success": True,
        "commit_hash": digest,
        "tag": tag,
        "message": msg,
    }


def end_checkpoint() -> dict:
    return {"success": True, "message": "Checkpoint session ended (no-op; EspToolkit uses direct git commits)."}
