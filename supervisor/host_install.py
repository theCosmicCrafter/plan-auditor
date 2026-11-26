"""Host skill asset installation."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Any

HOST_PATHS = {
    "claude": (".claude", "skills", "plan-auditor"),
    "codex": (".codex", "skills", "plan-auditor"),
    "opencode": (".config", "opencode", "skills", "plan-auditor"),
    "commandcode": (".commandcode", "skills", "plan-auditor"),
}

HOST_ROOT_MARKERS = {
    "claude": (".claude",),
    "codex": (".codex",),
    "opencode": (".config", "opencode"),
    "commandcode": (".commandcode",),
}


class InstallSkillError(ValueError):
    """Raised when a host or installation target is unsupported."""


def skill_asset_root() -> Path:
    packaged = Path(__file__).resolve().parent.parent / "plan_auditor_skill"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parent.parent


def host_target(
    host: str, scope: str, directory: str | Path = ".", home: str | Path | None = None
) -> Path:
    if host not in HOST_PATHS:
        raise InstallSkillError(f"unsupported host: {host}")
    if scope not in {"user", "project"}:
        raise InstallSkillError(f"unsupported scope: {scope}")
    parts = HOST_PATHS[host]
    if scope == "user":
        base = Path(home).expanduser() if home is not None else Path.home()
    else:
        base = Path(directory).expanduser().resolve()
    return base.joinpath(*parts)


def detect_hosts(home: str | Path | None = None) -> list[str]:
    base = Path(home).expanduser() if home is not None else Path.home()
    detected: list[str] = []
    for host, parts in HOST_PATHS.items():
        target = base.joinpath(*parts)
        host_root = base.joinpath(*HOST_ROOT_MARKERS[host])
        if target.exists() or host_root.exists():
            detected.append(host)
    return detected


def _iter_asset_files(root: Path) -> list[tuple[Path, Path]]:
    """Return ``(source, relative-target)`` pairs for the host skill."""
    pairs: list[tuple[Path, Path]] = []
    skill = root / "SKILL.md"
    if skill.is_file():
        pairs.append((skill, Path("SKILL.md")))
    for directory in ("hooks", "references"):
        source = root / directory
        if source.is_dir():
            for path in sorted(source.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    pairs.append((path, path.relative_to(root)))
    import scripts

    scripts_root = Path(scripts.__file__).resolve().parent
    for path in sorted(scripts_root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            pairs.append((path, Path("scripts") / path.relative_to(scripts_root)))
    return pairs


def _unique_backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d%H%M%S")
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{counter}")
        counter += 1
    return candidate


def _install_file(source: Path, target: Path, *, dry_run: bool) -> dict[str, Any]:
    operation: dict[str, Any] = {"source": str(source), "target": str(target)}
    if target.exists() and target.read_bytes() == source.read_bytes():
        operation["action"] = "unchanged"
        return operation
    backup = _unique_backup(target) if target.exists() else None
    if dry_run:
        operation["action"] = "planned-update" if backup else "planned-create"
    else:
        operation["action"] = "updated" if backup else "created"
    if backup:
        operation["backup"] = str(backup)
    if dry_run:
        return operation
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        shutil.copy2(target, backup)
    shutil.copy2(source, target)
    return operation


def install_skill(
    host: str,
    *,
    scope: str = "user",
    directory: str | Path = ".",
    dry_run: bool = False,
    home: str | Path | None = None,
) -> dict[str, Any]:
    target = host_target(host, scope, directory, home)
    root = skill_asset_root()
    assets = _iter_asset_files(root)
    if not assets:
        raise InstallSkillError(f"no skill assets found under {root}")
    operations = [
        _install_file(source, target / relative, dry_run=dry_run) for source, relative in assets
    ]
    changed = [item for item in operations if item["action"] != "unchanged"]
    return {
        "host": host,
        "scope": scope,
        "target": str(target),
        "asset_root": str(root),
        "dry_run": dry_run,
        "operations": operations,
        "changed": len(changed),
        "unchanged": len(operations) - len(changed),
        "hook_command": f'"{sys.executable}" "{target / "hooks" / "gate_hook.py"}" "<workspace>"',
        "settings_modified": False,
        "settings_note": "host settings are not modified automatically; configure the printed hook command in the host if desired",
    }
