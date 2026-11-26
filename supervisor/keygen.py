"""Workspace-external HMAC key generation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any

from scripts.integrity import ENV_KEY_FILE, MIN_KEY_BYTES


class KeygenError(ValueError):
    """Raised when a key cannot be created or accepted safely."""


def default_key_path() -> Path:
    return Path.home() / ".plan-auditor" / "plan-auditor-hmac.key"


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([str(root), str(candidate)]) == str(root)
    except ValueError:
        return False


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _key_id(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().strip()).hexdigest()[:16]


def _permissions(path: Path, platform: str) -> str:
    if platform.startswith("win"):
        return "windows-acl"
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _validate_existing(path: Path, *, strict: bool, platform: str) -> None:
    try:
        raw = path.read_bytes().strip()
    except OSError as exc:
        raise KeygenError(f"cannot read existing HMAC key file: {exc}") from exc
    if len(raw) < MIN_KEY_BYTES:
        raise KeygenError(f"existing HMAC key file contains fewer than {MIN_KEY_BYTES} bytes")
    if strict and not platform.startswith("win"):
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise KeygenError(
                f"existing HMAC key file permissions are too open: {format(mode, '04o')}; "
                "use chmod 600 or choose a new key path"
            )


def environment_instructions(path: Path) -> dict[str, str]:
    posix = str(path).replace("\\", "/")
    windows = str(path)
    return {
        "bash": f'export {ENV_KEY_FILE}="{posix}"',
        "powershell": f'$env:{ENV_KEY_FILE} = "{windows}"',
    }


def generate_key_file(
    out: str | Path | None = None,
    *,
    workspace: str | Path = ".",
    strict: bool = False,
    platform: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create or reuse an external HMAC key without exposing key material."""
    platform = platform or sys.platform
    workspace_path = _resolve(workspace)
    path = _resolve(out) if out is not None else default_key_path().resolve()
    if _inside(workspace_path, path):
        raise KeygenError("HMAC key output must be outside the workspace")

    created = False
    if path.exists():
        _validate_existing(path, strict=strict, platform=platform)
    elif dry_run:
        return {
            "path": str(path),
            "created": False,
            "dry_run": True,
            "key_id": None,
            "key_bytes": 0,
            "permissions": "not-created",
            "workspace": str(workspace_path),
            "environment": environment_instructions(path),
        }
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not platform.startswith("win") and path.parent.name == ".plan-auditor":
            os.chmod(path.parent, 0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            _validate_existing(path, strict=strict, platform=platform)
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_hex(32).encode("ascii") + b"\n")
            created = True
        if not created:
            _validate_existing(path, strict=strict, platform=platform)

    result = {
        "path": str(path),
        "created": created,
        "key_id": _key_id(path),
        "key_bytes": len(path.read_bytes().strip()),
        "permissions": _permissions(path, platform),
        "workspace": str(workspace_path),
        "environment": environment_instructions(path),
        "dry_run": dry_run,
    }
    json.dumps(result)
    return result
