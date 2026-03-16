"""Single-job runner for ESPHome CLI with log capture and WebSocket broadcast."""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

from app.config import get_esphome_config_dir

log = logging.getLogger("esphome_api.job_runner")

# Max lines to keep in memory for status/logs API
LOG_TAIL_LINES = 2000


class JobRunner:
    def __init__(self) -> None:
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._current_command: Optional[str] = None
        self._current_config_path: Optional[str] = None
        self._started_at: Optional[float] = None
        self._log_lines: list[str] = []
        self._log_subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def _run_esphome(
        self,
        command: str,
        config_path: str,
        device: Optional[str] = None,
        on_stdout: Optional[Callable[[str], None]] = None,
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> tuple[int, str, str]:
        """Run esphome CLI; return (returncode, stdout, stderr). device = optional hostname/IP for --device."""
        env = os.environ.copy()
        # Run from config dir so relative paths in YAML work
        cwd = str(Path(config_path).parent)
        argv = ["esphome", command, config_path]
        if device and str(device).strip():
            argv.extend(["--device", str(device).strip()])
        # run = validate + compile + upload; --no-logs so we exit after upload instead of staying connected
        if command == "run":
            argv.append("--no-logs")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        self._current_process = proc
        self._current_command = " ".join(argv)
        self._current_config_path = config_path
        self._started_at = asyncio.get_running_loop().time()
        log.info("Job started: %s", self._current_command)
        out_buf: list[str] = []
        err_buf: list[str] = []

        async def read_stream(stream: asyncio.StreamReader, buf: list, line_cb: Optional[Callable[[str], None]]) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    return
                try:
                    s = line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    s = line.decode("utf-8", errors="replace").rstrip()
                buf.append(s)
                if line_cb:
                    line_cb(s)
                await self._broadcast_log(s)

        await asyncio.gather(
            read_stream(proc.stdout, out_buf, on_stdout),
            read_stream(proc.stderr, err_buf, on_stderr),
        )
        await proc.wait()
        code = proc.returncode or 0
        log.info("Job finished: %s -> exit_code=%d", self._current_command, code)
        self._current_process = None
        self._current_command = None
        self._current_config_path = None
        stdout_str = "\n".join(out_buf)
        stderr_str = "\n".join(err_buf)
        return code, stdout_str, stderr_str

    async def _broadcast_log(self, line: str) -> None:
        self._log_lines.append(line)
        if len(self._log_lines) > LOG_TAIL_LINES:
            self._log_lines = self._log_lines[-LOG_TAIL_LINES:]
        for q in self._log_subscribers:
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                pass

    def resolve_config(self, config_source: str, filename: Optional[str] = None, yaml_content: Optional[str] = None) -> tuple[Path, bool]:
        """
        Resolve config to a path. Returns (path, should_delete).
        If from snippet, writes to temp file and returns (path, True).
        """
        log.debug("resolve_config: config_source=%s filename=%r yaml_len=%s", config_source, filename, len(yaml_content) if yaml_content else 0)
        config_dir = get_esphome_config_dir()
        if config_source == "file" and filename:
            path = (config_dir / filename).resolve()
            if not path.is_relative_to(config_dir):
                log.warning("resolve_config rejected: filename %r outside config_dir %s", filename, config_dir)
                raise ValueError("Filename must be under the ESPHome config directory")
            if not path.exists():
                log.warning("resolve_config rejected: file not found filename=%r resolved=%s", filename, path)
                raise FileNotFoundError(f"Config file not found: {filename}")
            return path, False
        if config_source == "yaml" and yaml_content:
            fd, path_str = tempfile.mkstemp(suffix=".yaml", prefix="esphome_", dir=config_dir)
            os.close(fd)
            Path(path_str).write_text(yaml_content, encoding="utf-8")
            return Path(path_str), True
        raise ValueError("Provide config_source 'file' with filename or 'yaml' with yaml content")

    async def run(
        self,
        command: str,
        config_source: str,
        filename: Optional[str] = None,
        yaml_content: Optional[str] = None,
        device: Optional[str] = None,
    ) -> dict:
        """Run an esphome command. Returns dict with success, stdout, stderr, exit_code, error. device = optional hostname/IP for --device."""
        log.info("run entry: command=%s config_source=%s filename=%r device=%r", command, config_source, filename, device)
        async with self._lock:
            pass  # wait for lock
        try:
            path, delete_after = self.resolve_config(config_source, filename, yaml_content)
        except (ValueError, FileNotFoundError) as e:
            log.warning("Job rejected: %s", e)
            return {"success": False, "error": str(e), "stdout": "", "stderr": "", "exit_code": -1}

        async with self._lock:
            if self._current_process is not None:
                log.warning("Job rejected: another job already running")
                return {
                    "success": False,
                    "error": "Another job is already running",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                }
            try:
                code, stdout, stderr = await self._run_esphome(command, str(path), device=device)
                success = code == 0
                err_msg = None if success else (stderr.strip() or stdout.strip() or f"Exit code {code}")
                if success:
                    log.info("Job succeeded: %s %s", command, path.name)
                else:
                    log.warning("Job failed: %s %s exit_code=%d error=%s", command, path.name, code, (err_msg or "")[:200])
                    # Log full stderr so add-on log shows real failure (e.g. penv/pip traceback)
                    if stderr.strip():
                        for line in stderr.strip().splitlines():
                            log.warning("stderr: %s", line)
                    if stdout.strip() and not stderr.strip():
                        for line in stdout.strip().splitlines()[-100:]:
                            log.warning("stdout: %s", line)
                return {
                    "success": success,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": code,
                    "error": err_msg,
                }
            finally:
                if delete_after and path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def get_status(self) -> dict:
        """Current job status for API."""
        if self._current_process is not None and self._current_command:
            return {
                "state": "running",
                "command": self._current_command,
                "config_path": self._current_config_path,
                "started_at": self._started_at,
                "log_tail": self._log_lines[-500:] if self._log_lines else [],
            }
        return {
            "state": "idle",
            "command": None,
            "config_path": None,
            "started_at": None,
            "log_tail": self._log_lines[-500:] if self._log_lines else [],
        }

    def get_log_tail(self, n: int = 500) -> list[str]:
        return self._log_lines[-n:]

    def subscribe_logs(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._log_subscribers.add(q)
        return q

    def unsubscribe_logs(self, q: asyncio.Queue) -> None:
        self._log_subscribers.discard(q)


# Singleton used by API and MCP
runner = JobRunner()
