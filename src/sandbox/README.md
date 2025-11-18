# Sandbox subsystem

This package provides a minimal, dependency‑light sandbox for executing `ast-grep` and test commands inside per‑task workspaces.

## Files

- `runner.py` – core sandbox implementation:
  - `SandboxConfig`: configuration for work root, logs directory, time/memory limits, allowed binaries, and optional jailer flags.
  - `prepare_workspace(task_id, files) -> Path`: creates a per‑task workspace under `.sandbox/<task_id>/` and writes the provided files (relative paths only).
  - `apply_action(workspace, action_dict) -> SandboxResult`: runs an allow‑listed command inside the workspace, with rlimits and a best‑effort network‑restricted environment. Captures stdout, stderr, exit code, duration, and a unified diff of file changes.
  - `run_tests(workspace, test_spec) -> TestResult`: thin wrapper around `apply_action` for running pytest or similar.
  - `cleanup(workspace)`: removes the workspace directory and appends a `cleanup` event to the sandbox log.

## Architecture

- **Configuration**: `SandboxConfig` is populated from `configs/sandbox.yaml`, with sane defaults if the file or `yaml` package is missing. It controls:
  - `work_root` (default: `.sandbox`) and `logs_dir` (default: `logs/sandbox`).
  - Execution limits: `default_timeout_sec`, `cpu_time_sec`, `mem_limit_mb`.
  - `allowed_binaries`: the small allowlist of binaries that can be launched.
  - Optional jailer flags (`enable_jail`, `jailer`) that are currently parsed but not enforced beyond configuration.

- **Workspace lifecycle**:
  - `prepare_workspace` is the only entrypoint for creating a workspace. It enforces safe, relative paths (no absolute paths or `..` components) and writes files under `<work_root>/<task_id>/...`.
  - `cleanup` removes the workspace and logs the operation, ensuring tests and actors do not leave behind temporary trees.

- **Execution and isolation**:
  - `apply_action` validates the first element of `command` against the allowlist and resolves it with `shutil.which`.
  - On POSIX systems, `_preexec_limits` sets CPU time and address‑space limits, and disables core dumps via `resource.setrlimit`.
  - `_env_for_subprocess` strips HTTP proxy variables and sets `NO_PROXY="*"` as a best‑effort network restriction.
  - All subprocesses run with `cwd` set to the per‑task workspace.

- **Diff and logging**:
  - Before executing a command, `_snapshot_workspace` records the contents of small, UTF‑8 text files under the workspace. After execution, a second snapshot is taken and `_compute_diff` produces a unified diff and list of changed files.
  - `SandboxResult` includes `diff` and `changed_files` alongside stdout/stderr and exit code.
  - `_log_event` writes JSONL records to `logs/sandbox/<task_id>.jsonl`, automatically inserting a `timestamp` and `task_id`. Events include high‑level metadata such as `cmd`, `exit_code`, `duration_sec`, `error`, `changed_files`, and `diff_len`, but not full stdout/stderr to keep logs compact.

This subsystem intentionally avoids heavy external dependencies to stay easy to run in local development and CI, while still providing deterministic workspaces, basic resource limits, and enough logging for trajectory analysis.

