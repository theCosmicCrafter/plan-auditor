"""Host skill installation automation."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts
from supervisor import host_install
from supervisor.cli import main
from supervisor.host_install import (
    HOST_PATHS,
    InstallSkillError,
    _iter_asset_files,
    _unique_backup,
    detect_hosts,
    host_target,
    install_skill,
    skill_asset_root,
)


def test_host_target_matrix_user_and_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    assert host_target("claude", "user", home=home) == home / ".claude" / "skills" / "plan-auditor"
    assert host_target("codex", "user", home=home) == home / ".agents" / "skills" / "plan-auditor"
    assert (
        host_target("opencode", "user", home=home)
        == home / ".config" / "opencode" / "skills" / "plan-auditor"
    )
    assert (
        host_target("commandcode", "user", home=home)
        == home / ".commandcode" / "skills" / "plan-auditor"
    )
    assert (
        host_target("claude", "project", directory=project, home=home)
        == project.resolve() / ".claude" / "skills" / "plan-auditor"
    )
    assert (
        host_target("codex", "project", directory=project, home=home)
        == project.resolve() / ".agents" / "skills" / "plan-auditor"
    )
    assert (
        host_target("opencode", "project", directory=project, home=home)
        == project.resolve() / ".opencode" / "skills" / "plan-auditor"
    )
    for host in HOST_PATHS:
        assert host_target(host, "user", home=home).name == "plan-auditor"


def test_host_target_rejects_unknown_host_and_scope(tmp_path: Path) -> None:
    with pytest.raises(InstallSkillError, match="unsupported host"):
        host_target("unknown", "user", home=tmp_path)
    with pytest.raises(InstallSkillError, match="unsupported scope"):
        host_target("claude", "system", home=tmp_path)


def test_detect_hosts_uses_host_markers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert detect_hosts(home) == []
    (home / ".claude").mkdir()
    assert detect_hosts(home) == ["claude"]
    (home / ".config" / "opencode").mkdir(parents=True)
    assert detect_hosts(home) == ["claude", "opencode"]


def test_install_skill_dry_run_writes_nothing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    result = install_skill("claude", scope="project", directory=project, dry_run=True)
    assert result["dry_run"] is True
    assert result["changed"] > 0
    assert all(item["action"].startswith("planned-") for item in result["operations"])
    assert not (project / ".claude").exists()
    assert result["hook_commands"]["posix"] == shlex.join(result["hook_commands"]["argv"])
    expected_key = "cmd" if os.name == "nt" else "posix"
    assert result["hook_command"] == result["hook_commands"][expected_key]
    assert "gate_hook.py" in result["hook_command"]
    assert result["settings_modified"] is False


def test_install_skill_copies_assets_and_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    result = install_skill("codex", scope="project", directory=project)
    target = project / ".agents" / "skills" / "plan-auditor"
    assert result["changed"] == len(result["operations"])
    assert (target / "SKILL.md").is_file()
    assert (target / "hooks" / "gate_hook.py").is_file()
    assert (target / "references" / "plan-format.md").is_file()
    assert (target / "scripts" / "audit_check.py").is_file()

    second = install_skill("codex", scope="project", directory=project)
    assert second["changed"] == 0
    assert second["unchanged"] == len(second["operations"])


def test_install_skill_backs_up_changed_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    install_skill("claude", scope="project", directory=project)
    target = project / ".claude" / "skills" / "plan-auditor" / "SKILL.md"
    target.write_text("operator customization\n", encoding="utf-8")
    result = install_skill("claude", scope="project", directory=project)
    operation = next(item for item in result["operations"] if item["target"] == str(target))
    backup = Path(operation["backup"])
    assert operation["action"] == "updated"
    assert backup.read_text(encoding="utf-8") == "operator customization\n"
    assert "operator customization" not in target.read_text(encoding="utf-8")


def test_install_skill_user_scope_uses_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = install_skill("opencode", scope="user", home=home)
    assert Path(result["target"]) == home / ".config" / "opencode" / "skills" / "plan-auditor"
    assert (home / ".config" / "opencode" / "skills" / "plan-auditor" / "SKILL.md").is_file()


def test_install_skill_cli_success(tmp_path: Path, capfd) -> None:
    project = tmp_path / "project"
    project.mkdir()
    assert (
        main(
            [
                "install-skill",
                "--host",
                "claude",
                "--scope",
                "project",
                "--dir",
                str(project),
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capfd.readouterr().out)
    assert payload["host"] == "claude"
    assert payload["dry_run"] is True


def test_skill_asset_root_falls_back_when_not_packaged(monkeypatch) -> None:
    real_is_dir = Path.is_dir

    def hide_packaged_assets(path):
        if path.name == "plan_auditor_skill":
            return False
        return real_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", hide_packaged_assets)
    assert skill_asset_root() == Path(host_install.__file__).resolve().parent.parent


def test_iter_asset_files_handles_sparse_assets_and_pycache(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    scripts_root = tmp_path / "fake-scripts"
    (scripts_root / "__pycache__").mkdir(parents=True)
    (scripts_root / "__pycache__" / "ignored.py").write_text("ignored = True\\n", encoding="utf-8")
    monkeypatch.setattr(scripts, "__file__", str(scripts_root / "__init__.py"))
    assert _iter_asset_files(root) == []


def test_unique_backup_avoids_timestamp_collisions(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "SKILL.md"
    target.write_text("new\\n", encoding="utf-8")
    monkeypatch.setattr(host_install.time, "strftime", lambda _fmt: "fixed")
    first = tmp_path / "SKILL.md.bak-fixed"
    first.write_text("old\\n", encoding="utf-8")
    assert _unique_backup(target) == tmp_path / "SKILL.md.bak-fixed-1"


def test_install_skill_refuses_empty_asset_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(host_install, "_iter_asset_files", lambda _root: [])
    with pytest.raises(InstallSkillError, match="no skill assets"):
        install_skill("claude", scope="project", directory=tmp_path)


def test_install_skill_cli_error_is_fail_closed(tmp_path: Path, monkeypatch, capfd) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def fail_install(*_args, **_kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(host_install, "install_skill", fail_install)
    assert (
        main(
            [
                "install-skill",
                "--host",
                "claude",
                "--scope",
                "project",
                "--dir",
                str(project),
            ]
        )
        == 2
    )
    payload = json.loads(capfd.readouterr().out)
    assert payload["installed"] is False
    assert "copy failed" in payload["error"]


def test_commandcode_hook_uses_blocking_stop_adapter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    result = install_skill("commandcode", scope="project", directory=project, dry_run=True)
    argv = result["hook_commands"]["argv"]
    assert argv[1].endswith(str(Path("scripts") / "stop_gate.py"))
    assert "<workspace>" not in argv


def test_install_skill_refuses_symlinked_project_components(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    try:
        (project / ".claude").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(InstallSkillError, match="refusing to follow installation symlink"):
        install_skill("claude", scope="project", directory=project, dry_run=True)
    assert not (outside / "SKILL.md").exists()


def test_reject_symlinked_install_path_refuses_boundary_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    boundary = tmp_path / "boundary"
    try:
        boundary.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(InstallSkillError, match="refusing to follow installation symlink"):
        host_install._reject_symlinked_install_path(boundary, boundary / "SKILL.md")


def test_hook_commands_use_powershell_call_operator_and_quote_cmd_metacharacters(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project&hooks"
    project.mkdir()
    result = install_skill("claude", scope="project", directory=project, dry_run=True)
    commands = result["hook_commands"]
    assert commands["powershell"].startswith("& '")
    assert "&" in str(result["target"])
    quoted_target = host_install._cmd_quote(str(Path(result["target"]) / "hooks" / "gate_hook.py"))
    assert quoted_target.startswith('"') and quoted_target.endswith('"')
    assert quoted_target in commands["cmd"]


def _write_argv_printer(tmp_path: Path) -> Path:
    directory = tmp_path / "shell & args"
    directory.mkdir()
    script = directory / "print_args.py"
    script.write_text(
        "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return script


def _run_shell_command(command: list[str]) -> list[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_posix_hook_quoting_preserves_arguments(tmp_path: Path) -> None:
    if os.name == "nt" or shutil.which("sh") is None:
        pytest.skip("POSIX shell unavailable")
    script = _write_argv_printer(tmp_path)
    sentinel = "<workspace> & uncut"
    argv = [sys.executable, str(script), sentinel]
    assert _run_shell_command(["sh", "-c", shlex.join(argv)]) == [sentinel]


def test_powershell_hook_quoting_preserves_arguments(tmp_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable")
    script = _write_argv_printer(tmp_path)
    sentinel = "<workspace> & uncut 'quoted'"
    argv = [sys.executable, str(script), sentinel]
    command = "& " + " ".join(host_install._powershell_quote(item) for item in argv)
    assert _run_shell_command([shell, "-NoProfile", "-Command", command]) == [sentinel]


def test_cmd_hook_quoting_preserves_arguments(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("Command Prompt unavailable")
    script = _write_argv_printer(tmp_path)
    sentinel = "<workspace> & uncut"
    argv = [sys.executable, str(script), sentinel]
    command = " ".join(host_install._cmd_quote(item) for item in argv)
    batch = tmp_path / "run-hook.bat"
    batch.write_text("@echo off\n" + command + "\n", encoding="utf-8")
    assert _run_shell_command(["cmd.exe", "/c", str(batch)]) == [sentinel]
