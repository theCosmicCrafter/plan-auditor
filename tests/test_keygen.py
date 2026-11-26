"""Workspace-external HMAC key generation."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from supervisor import keygen
from supervisor.cli import main
from supervisor.keygen import KeygenError, generate_key_file


def test_generate_key_file_creates_a_private_external_key(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "keys" / "hmac.key"
    result = generate_key_file(out, workspace=workspace, strict=True)
    assert result["created"] is True
    assert result["path"] == str(out.resolve())
    assert result["key_bytes"] == 64
    assert len(result["key_id"]) == 16
    raw = out.read_bytes().strip()
    assert len(raw) == 64
    assert raw.decode("ascii") not in json.dumps(result)
    if os.name != "nt":
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        assert result["permissions"] == "0600"


def test_generate_key_file_reuses_an_existing_valid_key(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "hmac.key"
    first = generate_key_file(out, workspace=workspace)
    before = out.read_bytes()
    second = generate_key_file(out, workspace=workspace)
    assert first["created"] is True
    assert second["created"] is False
    assert second["key_id"] == first["key_id"]
    assert out.read_bytes() == before


def test_generate_key_file_refuses_workspace_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(KeygenError, match="outside the workspace"):
        generate_key_file(workspace / "hmac.key", workspace=workspace)


def test_generate_key_file_refuses_short_existing_key(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "hmac.key"
    out.write_bytes(b"short")
    with pytest.raises(KeygenError, match="fewer than 32 bytes"):
        generate_key_file(out, workspace=workspace)


def test_generate_key_file_strict_refuses_open_posix_permissions(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "hmac.key"
    generate_key_file(out, workspace=workspace)
    monkeypatch.setattr(keygen.stat, "S_IMODE", lambda _mode: 0o644)
    with pytest.raises(KeygenError, match="permissions are too open"):
        generate_key_file(out, workspace=workspace, strict=True, platform="linux")
    result = generate_key_file(out, workspace=workspace, strict=False, platform="linux")
    assert result["permissions"] == "0644"


def test_generate_key_file_handles_a_creation_race(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "hmac.key"
    real_open = keygen.os.open

    def race_open(*args, **kwargs):
        fd = real_open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(b"a" * 64)
        raise FileExistsError(out)

    monkeypatch.setattr(keygen.os, "open", race_open)
    result = generate_key_file(out, workspace=workspace)
    assert result["created"] is False
    assert result["key_bytes"] == 64


def test_generate_key_file_default_path_can_be_redirected(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    redirected = tmp_path / "profile" / ".plan-auditor" / "plan-auditor-hmac.key"
    monkeypatch.setattr(keygen, "default_key_path", lambda: redirected)
    result = generate_key_file(workspace=workspace)
    assert result["path"] == str(redirected.resolve())
    assert redirected.is_file()


def test_generate_key_file_dry_run_writes_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / ".plan-auditor" / "hmac.key"
    result = generate_key_file(out, workspace=workspace, dry_run=True, platform="linux")
    assert result["dry_run"] is True
    assert result["key_id"] is None
    assert not out.exists()
    assert not out.parent.exists()


def test_generate_key_file_secures_default_parent_on_posix(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / ".plan-auditor" / "hmac.key"
    generate_key_file(out, workspace=workspace, platform="linux")
    if os.name != "nt":
        assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700


def test_environment_instructions_are_shell_specific(tmp_path: Path) -> None:
    path = tmp_path / "hmac.key"
    instructions = keygen.environment_instructions(path)
    assert instructions["bash"].startswith("export PLAN_AUDITOR_HMAC_KEY_FILE=")
    assert instructions["powershell"].startswith("$env:PLAN_AUDITOR_HMAC_KEY_FILE =")


def test_keygen_cli_success_and_error_do_not_print_key(tmp_path: Path, capfd) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out = tmp_path / "hmac.key"
    assert main(["integrity", "keygen", str(workspace), "--out", str(out), "--strict"]) == 0
    success = capfd.readouterr().out
    payload = json.loads(success)
    assert payload["created"] is True
    assert out.read_bytes().strip().decode("ascii") not in success

    assert main(["integrity", "keygen", str(workspace), "--out", str(workspace / "bad.key")]) == 2
    failure = capfd.readouterr().out
    assert "outside the workspace" in failure
    assert out.read_bytes().strip().decode("ascii") not in failure
