"""Safe first-run workspace bootstrap."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import CONFIG_FILENAME
from .host_install import detect_hosts, install_skill
from .keygen import generate_key_file


class BootstrapError(ValueError):
    """Raised when bootstrap cannot proceed safely."""


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def python_pytest_template() -> tuple[dict[str, Any], dict[str, Any]]:
    # Resolve the interpreter by name at verification time rather than baking
    # in a bootstrap-time path; an activated project virtualenv can then win.
    # The ``-m pytest`` form also places the workspace on ``sys.path``.
    python = (
        "python" if sys.platform.startswith("win") or not shutil.which("python3") else "python3"
    )
    check = {"type": "exec", "argv": [python, "-m", "pytest"], "expect_exit": 0}
    plan = {
        "task": "Prove the Python test suite passes",
        "created": _timestamp(),
        "requirements": [
            {
                "id": "REQ-001",
                "description": "The Python test suite must pass.",
                "priority": "must",
            }
        ],
        "steps": [
            {
                "id": 1,
                "title": "Python test suite passes",
                "covers": ["REQ-001"],
                "status": "pending",
                "verify": [dict(check)],
            }
        ],
    }
    request = {
        "format_version": 1,
        "task": "Prove the Python test suite passes",
        "requirements": [
            {
                "id": "REQ-001",
                "description": "The Python test suite must pass.",
                "priority": "must",
                "acceptance_checks": [dict(check)],
            }
        ],
    }
    return plan, request


def generic_template() -> tuple[dict[str, Any], dict[str, Any]]:
    check = {
        "type": "run",
        "cmd": "python -c \"print('plan-auditor bootstrap check')\"",
        "expect_exit": 0,
    }
    plan = {
        "task": "Prove the bootstrap smoke check passes",
        "created": _timestamp(),
        "requirements": [
            {
                "id": "REQ-001",
                "description": "The bootstrap smoke check must pass.",
                "priority": "must",
            }
        ],
        "steps": [
            {
                "id": 1,
                "title": "Bootstrap smoke check passes",
                "covers": ["REQ-001"],
                "status": "pending",
                "verify": [dict(check)],
            }
        ],
    }
    request = {
        "format_version": 1,
        "task": "Prove the bootstrap smoke check passes",
        "requirements": [
            {
                "id": "REQ-001",
                "description": "The bootstrap smoke check must pass.",
                "priority": "must",
                "acceptance_checks": [dict(check)],
            }
        ],
    }
    return plan, request


def template_documents(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if name == "python-pytest":
        return python_pytest_template()
    if name == "generic":
        return generic_template()
    raise BootstrapError(f"unsupported template: {name}")


def _write_json_once(
    path: Path, payload: dict[str, Any], *, dry_run: bool, operations: list[dict[str, Any]]
) -> None:
    if path.is_symlink():
        raise BootstrapError(f"refusing to follow scaffold symlink: {path}")
    if path.exists():
        operations.append({"path": str(path), "action": "existing"})
        return
    if dry_run:
        operations.append({"path": str(path), "action": "planned-create"})
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    operations.append({"path": str(path), "action": "created"})


def init_workspace(
    directory: str | Path = ".",
    *,
    host: str = "auto",
    profile: str = "standard",
    mode: str = "serial",
    template: str = "python-pytest",
    create_key: bool = False,
    key_out: str | Path | None = None,
    install_hooks: bool = False,
    hook_scope: str = "user",
    dry_run: bool = False,
    home: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise BootstrapError(f"workspace directory not found: {root}")
    if profile not in {"light", "standard", "strict"}:
        raise BootstrapError(f"unsupported profile: {profile}")
    if mode not in {"serial", "parallel-warn", "parallel-strict"}:
        raise BootstrapError(f"unsupported mode: {mode}")

    operations: list[dict[str, Any]] = []
    pg = root / ".plan-auditor"
    if pg.is_symlink():
        raise BootstrapError(f"refusing to follow scaffold symlink: {pg}")
    if pg.exists() and not pg.is_dir():
        raise BootstrapError(f"scaffold state path is not a directory: {pg}")
    if pg.exists():
        operations.append({"path": str(pg), "action": "existing"})
    elif dry_run:
        operations.append({"path": str(pg), "action": "planned-create"})
    else:
        pg.mkdir(parents=True)
        operations.append({"path": str(pg), "action": "created"})

    plan, request = template_documents(template)
    default_plan = pg / "plan.json"
    named_plan_dir = pg / "plans"
    has_named_plans = named_plan_dir.is_dir() and any(
        child.is_file() and not child.is_symlink() and child.suffix.lower() == ".json"
        for child in named_plan_dir.iterdir()
    )
    if not default_plan.exists() and not default_plan.is_symlink() and has_named_plans:
        operations.append({"path": str(named_plan_dir), "action": "existing"})
    else:
        _write_json_once(default_plan, plan, dry_run=dry_run, operations=operations)
    _write_json_once(root / "request-source.json", request, dry_run=dry_run, operations=operations)
    config = {"profile": profile, "mode": mode, "tier": 1}
    _write_json_once(pg / CONFIG_FILENAME, config, dry_run=dry_run, operations=operations)

    detected = detect_hosts(home)
    selected_host = host
    if host == "auto":
        selected_host = detected[0] if detected else "none"
    elif host not in {"none", "claude", "codex", "opencode", "commandcode"}:
        raise BootstrapError(f"unsupported host: {host}")

    key = None
    if create_key:
        key = generate_key_file(key_out, workspace=root, strict=True, dry_run=dry_run)

    hooks = None
    hook_warning = None
    if install_hooks:
        if selected_host == "none":
            hook_warning = "no supported host directory detected; skill installation skipped"
        else:
            hooks = install_skill(
                selected_host,
                scope=hook_scope,
                directory=root,
                dry_run=dry_run,
                home=home,
            )

    return {
        "workspace": str(root),
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "dry_run": dry_run,
        "operations": operations,
        "created": sum(1 for item in operations if item["action"] == "created"),
        "existing": sum(1 for item in operations if item["action"] == "existing"),
        "planned": sum(1 for item in operations if item["action"] == "planned-create"),
        "template": template,
        "profile": profile,
        "mode": mode,
        "host": {"requested": host, "detected": detected, "selected": selected_host},
        "key": key,
        "hooks": hooks,
        "hook_warning": hook_warning,
        "request_activated": False,
        "next_steps": [
            "edit request-source.json so it states the actual host-approved request",
            "run plan-auditor request init . --file request-source.json",
            "run plan-auditor plan verify .",
            "run the plan steps, then run plan-auditor integrity init . and plan-auditor audit .",
        ],
    }
