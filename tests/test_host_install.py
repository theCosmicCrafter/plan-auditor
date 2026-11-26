"""Host skill installation automation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from supervisor.cli import main
from supervisor.host_install import (
    HOST_PATHS,
    InstallSkillError,
    detect_hosts,
    host_target,
    install_skill,
)


def test_host_target_matrix_user_and_project(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    assert host_target("claude", "user", home=home) == home / ".claude" / "skills" / "plan-auditor"
    assert host_target("codex", "user", home=home) == home / ".codex" / "skills" / "plan-auditor"
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
    assert "gate_hook.py" in result["hook_command"]
    assert result["settings_modified"] is False


def test_install_skill_copies_assets_and_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    result = install_skill("codex", scope="project", directory=project)
    target = project / ".codex" / "skills" / "plan-auditor"
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
