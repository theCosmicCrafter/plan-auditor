"""Safe workspace bootstrap behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from supervisor.bootstrap import BootstrapError, init_workspace, template_documents
from supervisor.cli import main


def test_init_workspace_scaffolds_without_activation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = tmp_path / "hmac.key"
    result = init_workspace(workspace, host="none", create_key=True, key_out=key)
    assert result["created"] == 4
    assert result["request_activated"] is False
    assert result["key"]["created"] is True
    assert key.is_file()
    assert not key.resolve().is_relative_to(workspace.resolve())
    plan = json.loads((workspace / ".plan-auditor" / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((workspace / "request-source.json").read_text(encoding="utf-8"))
    assert plan["steps"][0]["status"] == "pending"
    assert request["requirements"][0]["acceptance_checks"]
    assert not (workspace / ".plan-auditor" / "request.json").exists()


def test_init_workspace_is_idempotent_and_non_destructive(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = init_workspace(workspace, host="none")
    plan_path = workspace / ".plan-auditor" / "plan.json"
    plan_path.write_text('{"custom": true}\n', encoding="utf-8")
    second = init_workspace(workspace, host="none")
    assert first["created"] == 4
    assert second["created"] == 0
    assert second["existing"] == 4
    assert json.loads(plan_path.read_text(encoding="utf-8")) == {"custom": True}


def test_init_workspace_dry_run_writes_nothing(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = tmp_path / "hmac.key"
    result = init_workspace(workspace, host="none", create_key=True, key_out=key, dry_run=True)
    assert result["planned"] == 4
    assert result["key"]["dry_run"] is True
    assert not (workspace / ".plan-auditor").exists()
    assert not (workspace / "request-source.json").exists()
    assert not key.exists()


def test_init_workspace_rejects_missing_workspace_and_bad_key_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(BootstrapError, match="directory not found"):
        init_workspace(missing, host="none")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ValueError, match="outside the workspace"):
        init_workspace(workspace, host="none", create_key=True, key_out=workspace / "hmac.key")


def test_init_workspace_validates_profile_mode_and_template(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(BootstrapError, match="unsupported profile"):
        init_workspace(workspace, host="none", profile="invalid")
    with pytest.raises(BootstrapError, match="unsupported mode"):
        init_workspace(workspace, host="none", mode="invalid")
    with pytest.raises(BootstrapError, match="unsupported template"):
        template_documents("unknown")
    with pytest.raises(BootstrapError, match="unsupported host"):
        init_workspace(workspace, host="unknown")


def test_generic_template_is_behavioral() -> None:
    plan, request = template_documents("generic")
    assert plan["steps"][0]["verify"][0]["type"] == "run"
    assert request["requirements"][0]["acceptance_checks"][0]["type"] == "run"


def test_init_workspace_auto_detects_host_and_can_install_hooks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    (home / ".claude").mkdir(parents=True)
    result = init_workspace(
        workspace,
        host="auto",
        install_hooks=True,
        hook_scope="project",
        home=home,
    )
    assert result["host"]["selected"] == "claude"
    assert result["hooks"]["target"].endswith(str(Path(".claude") / "skills" / "plan-auditor"))
    assert (workspace / ".claude" / "skills" / "plan-auditor" / "SKILL.md").is_file()


def test_init_workspace_warns_when_auto_detects_no_host(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    result = init_workspace(workspace, install_hooks=True, home=home)
    assert result["host"]["selected"] == "none"
    assert result["hooks"] is None
    assert "no supported host" in result["hook_warning"]


def test_generic_bootstrap_template_can_activate_seal_and_run(tmp_path: Path, capfd) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert main(["init", str(workspace), "--host", "none", "--template", "generic", "--json"]) == 0
    capfd.readouterr()
    assert (
        main(["request", "init", str(workspace), "--file", str(workspace / "request-source.json")])
        == 0
    )
    capfd.readouterr()
    assert main(["plan", "verify", str(workspace)]) == 0
    capfd.readouterr()
    assert main(["run", str(workspace), "1"]) == 0
    output = capfd.readouterr().out
    assert "Bootstrap smoke check passes" in output


def test_init_cli_json_human_and_error(tmp_path: Path, capfd) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert main(["init", str(workspace), "--host", "none", "--json"]) == 0
    payload = json.loads(capfd.readouterr().out)
    assert payload["workspace"] == str(workspace.resolve())

    other = tmp_path / "other"
    other.mkdir()
    assert main(["init", str(other), "--host", "none"]) == 0
    human = capfd.readouterr().out
    assert "Request contract not activated" in human

    assert main(["init", str(tmp_path / "missing"), "--json"]) == 2
    error = capfd.readouterr().out
    assert "directory not found" in error


def test_init_cli_human_reports_key_hooks_and_warnings(tmp_path: Path, capfd) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = tmp_path / "hmac.key"
    assert (
        main(
            [
                "init",
                str(workspace),
                "--host",
                "claude",
                "--create-key",
                "--key-out",
                str(key),
                "--install-hooks",
                "--hook-scope",
                "project",
            ]
        )
        == 0
    )
    human = capfd.readouterr().out
    assert "HMAC key:" in human
    assert "Bash: export PLAN_AUDITOR_HMAC_KEY_FILE=" in human
    assert "PowerShell: $env:PLAN_AUDITOR_HMAC_KEY_FILE" in human
    assert "Skill assets:" in human
    assert "Hook command:" in human
    assert "Request contract not activated" in human

    other = tmp_path / "other"
    other.mkdir()
    assert main(["init", str(other), "--host", "none", "--install-hooks"]) == 0
    warning = capfd.readouterr().out
    assert "WARNING: no supported host directory detected" in warning


def test_python_template_can_activate_and_seal(tmp_path: Path, capfd) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert main(["init", str(workspace), "--host", "none", "--json"]) == 0
    capfd.readouterr()
    assert (
        main(["request", "init", str(workspace), "--file", str(workspace / "request-source.json")])
        == 0
    )
    capfd.readouterr()
    assert main(["plan", "verify", str(workspace)]) == 0
    capfd.readouterr()
    plan = json.loads((workspace / ".plan-auditor" / "plan.json").read_text(encoding="utf-8"))
    assert plan["steps"][0]["verify"][0]["argv"][1:] == ["-m", "pytest"]
    assert len(plan["steps"][0]["verify"][0]["argv"]) == 3


def test_init_workspace_does_not_add_default_plan_beside_named_plans(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    named = workspace / ".plan-auditor" / "plans"
    named.mkdir(parents=True)
    (named / "release.json").write_text("{}\n", encoding="utf-8")
    result = init_workspace(workspace, host="none")
    assert result["request_activated"] is False
    assert not (workspace / ".plan-auditor" / "plan.json").exists()


def test_init_workspace_refuses_symlinked_scaffold_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    try:
        (workspace / ".plan-auditor").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(BootstrapError, match="refusing to follow scaffold symlink"):
        init_workspace(workspace, host="none")


def test_init_workspace_refuses_dangling_destination_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        (workspace / "request-source.json").symlink_to(tmp_path / "outside.json")
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(BootstrapError, match="refusing to follow scaffold symlink"):
        init_workspace(workspace, host="none")


def test_init_workspace_refuses_non_directory_scaffold_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".plan-auditor").write_text("not a directory", encoding="utf-8")
    with pytest.raises(BootstrapError, match="not a directory"):
        init_workspace(workspace, host="none")
