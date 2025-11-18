"""Minimal sandbox runner.

Design goals:
- Keep it simple and dependency-light (no jailer by default).
- Provide per-task workspaces under a configurable root.
- Execute only allowlisted binaries with time/memory limits.
- Capture stdout/stderr/exit code and append minimal JSONL logs.

This module intentionally avoids heavy isolation to reduce complexity.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore

try:  # POSIX resource limits
    import resource  # type: ignore
except Exception:  # pragma: no cover - non-POSIX
    resource = None  # type: ignore

from src.data.schemas import repo_root


@dataclass
class SandboxConfig:
    work_root: Path
    logs_dir: Path
    default_timeout_sec: int = 30
    cpu_time_sec: int = 20
    mem_limit_mb: int = 4096
    allowed_binaries: List[str] = None  # type: ignore[assignment]
    enable_jail: bool = False
    jailer: str = "none"

    @classmethod
    def defaults(cls) -> "SandboxConfig":
        root = repo_root()
        return cls(
            work_root=root / ".sandbox",
            logs_dir=root / "logs" / "sandbox",
            default_timeout_sec=30,
            cpu_time_sec=20,
            mem_limit_mb=4096,
            allowed_binaries=["ast-grep", "sg", "python", "pytest"],
            enable_jail=False,
            jailer="none",
        )


def _safe_relpath(path: Path) -> Path:
    if path.is_absolute():
        raise ValueError(f"Absolute paths not allowed: {path}")
    if ".." in path.parts:
        raise ValueError(f"Path traversal not allowed: {path}")
    return path


def _load_config() -> SandboxConfig:
    cfg = SandboxConfig.defaults()
    cfg_path = repo_root() / "configs" / "sandbox.yaml"
    if not cfg_path.exists():
        return cfg
    if yaml is None:
        return cfg
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return cfg
    cfg.work_root = Path(data.get("work_root", cfg.work_root))
    cfg.logs_dir = Path(data.get("logs_dir", cfg.logs_dir))
    cfg.default_timeout_sec = int(data.get("default_timeout_sec", cfg.default_timeout_sec))
    cfg.cpu_time_sec = int(data.get("cpu_time_sec", cfg.cpu_time_sec))
    cfg.mem_limit_mb = int(data.get("mem_limit_mb", cfg.mem_limit_mb))
    allowed = data.get("allowed_binaries") or cfg.allowed_binaries
    if isinstance(allowed, list):
        cfg.allowed_binaries = [str(x) for x in allowed]
    cfg.enable_jail = bool(data.get("enable_jail", cfg.enable_jail))
    cfg.jailer = str(data.get("jailer", cfg.jailer))
    return cfg


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_event(cfg: SandboxConfig, task_id: str, event: Mapping[str, object]) -> None:
    _ensure_dir(cfg.logs_dir)
    payload = dict(event)
    payload.setdefault("timestamp", time.time())
    payload.setdefault("task_id", task_id)
    log_path = cfg.logs_dir / f"{task_id}.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def prepare_workspace(task_id: str, files: Mapping[str, bytes | str]) -> Path:
    """Create a per-task workspace and materialize files.

    files: mapping of relative path -> content (str or bytes).
    Returns workspace path.
    """
    cfg = _load_config()
    ws = _ensure_dir(cfg.work_root / task_id)
    for rel, content in files.items():
        rel_path = _safe_relpath(Path(rel))
        abs_path = ws / rel_path
        _ensure_dir(abs_path.parent)
        if isinstance(content, bytes):
            abs_path.write_bytes(content)
        else:
            abs_path.write_text(content)
    _log_event(cfg, task_id, {"event": "prepare_workspace", "workspace": str(ws)})
    return ws


@dataclass
class SandboxResult:
    cmd: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    error: Optional[str] = None
    diff: Optional[str] = None
    changed_files: Optional[List[str]] = None


def _preexec_limits(cfg: SandboxConfig):  # pragma: no cover - platform dependent
    if resource is None:
        return None

    def apply_limits():
        # Limit CPU seconds
        if cfg.cpu_time_sec:
            resource.setrlimit(resource.RLIMIT_CPU, (cfg.cpu_time_sec, cfg.cpu_time_sec))
        # Limit address space (approx memory)
        if cfg.mem_limit_mb:
            bytes_limit = cfg.mem_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
        # Disallow core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply_limits


def _which_allowed(binary: str, allowed: Iterable[str]) -> Optional[str]:
    # Allow either exact name match or resolved path when first element is in allowlist
    base = Path(binary).name
    if base not in allowed:
        return None
    return shutil.which(binary) or shutil.which(base)


_MAX_DIFF_FILE_SIZE = 2 * 1024 * 1024  # 2 MiB


def _snapshot_workspace(workspace: Path) -> Dict[str, str]:
    """Capture a lightweight snapshot of text files in the workspace.

    Large or binary files are skipped to avoid excessive memory usage.
    """
    snapshot: Dict[str, str] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(workspace))
        except ValueError:
            # Should not happen, but guard against it.
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        if st.st_size > _MAX_DIFF_FILE_SIZE:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        snapshot[rel] = content
    return snapshot


def _compute_diff(before: Dict[str, str], after: Dict[str, str]) -> tuple[Optional[str], Optional[List[str]]]:
    """Compute a unified diff between two workspace snapshots."""
    changed_files: List[str] = []
    chunks: List[str] = []
    all_paths = sorted(set(before) | set(after))
    for rel in all_paths:
        prev = before.get(rel)
        curr = after.get(rel)
        if prev == curr:
            continue
        changed_files.append(rel)
        prev_lines = prev.splitlines(keepends=True) if prev is not None else []
        curr_lines = curr.splitlines(keepends=True) if curr is not None else []
        diff_iter = difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        chunks.append("".join(diff_iter))
    if not changed_files:
        return None, None
    return "".join(chunks), changed_files


def apply_action(workspace: Path, action: Mapping[str, object], *, timeout_sec: Optional[int] = None) -> SandboxResult:
    """Execute an allowlisted command inside the workspace.

    Minimal action format: {"command": ["ast-grep", "..."], ...}
    Only the first element is validated against the allowlist.
    """
    cfg = _load_config()
    cmd = action.get("command")
    if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
        return SandboxResult(cmd=[], exit_code=127, stdout="", stderr="invalid command", duration_sec=0.0, error="invalid_command")

    bin_path = _which_allowed(cmd[0], cfg.allowed_binaries or [])
    if not bin_path:
        return SandboxResult(cmd=cmd, exit_code=126, stdout="", stderr=f"binary '{cmd[0]}' not allowed", duration_sec=0.0, error="not_allowed")

    full_cmd = [bin_path] + cmd[1:]
    before = _snapshot_workspace(workspace)
    start = time.time()
    try:
        proc = subprocess.run(
            full_cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec or cfg.default_timeout_sec,
            preexec_fn=_preexec_limits(cfg),  # type: ignore[arg-type]
            env=_env_for_subprocess(),
        )
        duration = time.time() - start
        after = _snapshot_workspace(workspace)
        diff, changed_files = _compute_diff(before, after)
        result = SandboxResult(
            cmd=full_cmd,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_sec=duration,
            diff=diff,
            changed_files=changed_files,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start
        after = _snapshot_workspace(workspace)
        diff, changed_files = _compute_diff(before, after)
        result = SandboxResult(
            cmd=full_cmd,
            exit_code=124,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, (bytes, bytearray)) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, (bytes, bytearray)) else (exc.stderr or "timeout"),
            duration_sec=duration,
            error="timeout",
            diff=diff,
            changed_files=changed_files,
        )
    _log_event(cfg, workspace.name, {
        "event": "apply_action",
        "cmd": full_cmd,
        "exit_code": result.exit_code,
        "duration_sec": result.duration_sec,
        "error": result.error,
        "changed_files": result.changed_files or [],
        "diff_len": len(result.diff) if result.diff is not None else 0,
    })
    return result


@dataclass
class TestResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    error: Optional[str] = None


def run_tests(workspace: Path, test_spec: Mapping[str, object], *, timeout_sec: Optional[int] = None) -> TestResult:
    """Run tests as an allowlisted command (e.g., pytest).

    Minimal format: {"command": ["pytest", "-q"]}
    """
    res = apply_action(workspace, test_spec, timeout_sec=timeout_sec)
    return TestResult(
        exit_code=res.exit_code,
        stdout=res.stdout,
        stderr=res.stderr,
        duration_sec=res.duration_sec,
        error=res.error,
    )


def cleanup(workspace: Path) -> None:
    cfg = _load_config()
    try:
        if workspace.exists():
            shutil.rmtree(workspace)
    finally:
        _log_event(cfg, workspace.name, {"event": "cleanup", "workspace": str(workspace)})


def _env_for_subprocess() -> Dict[str, str]:
    env = dict(os.environ)
    # Best-effort: discourage network via proxy vars (cannot fully disable without a jailer)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    env["NO_PROXY"] = "*"
    return env


__all__ = [
    "SandboxConfig",
    "prepare_workspace",
    "apply_action",
    "run_tests",
    "cleanup",
]
