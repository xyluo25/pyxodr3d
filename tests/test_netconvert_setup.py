from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import pyxodr3d as odr
from pyxodr3d import __netconvert as netconvert_setup


def test_github_actions_installs_and_exports_sumo() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "python-ci.yml"
    )
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert workflow_text.index("- name: Install SUMO") < workflow_text.index(
        "- name: Run tests"
    )
    assert "sudo apt-get install --yes sumo sumo-tools" in workflow_text
    assert 'echo "SUMO_HOME=/usr/share/sumo" >> "$GITHUB_ENV"' in workflow_text
    assert "sumo --version" in workflow_text
    assert "netconvert --version" in workflow_text
    assert "test -f /usr/share/sumo/tools/randomTrips.py" in workflow_text


def test_setup_netconvert_is_exported_from_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected_installation = object()
    received_arguments: list[tuple[bool, str | Path | None]] = []
    monkeypatch.setattr(
        netconvert_setup,
        "setup_netconvert",
        lambda *, check, install_dir: received_arguments.append(
            (check, install_dir)
        )
        or expected_installation,
    )

    returned_installation = odr.setup_netconvert(
        check=True,
        install_dir=tmp_path,
    )

    assert returned_installation is expected_installation
    assert received_arguments == [(True, tmp_path)]
    assert "setup_netconvert" in odr.__all__


@pytest.mark.parametrize(
    ("platform_name", "display_name"),
    [("Windows", "Windows"), ("Linux", "Linux"), ("Darwin", "macOS")],
)
def test_operating_system_supports_expected_platforms(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    display_name: str,
) -> None:
    monkeypatch.setattr(netconvert_setup.platform, "system", lambda: platform_name)

    detected_name = netconvert_setup._operating_system()

    assert detected_name == platform_name
    assert netconvert_setup._display_system_name(detected_name) == display_name
    expected_suffix = ".exe" if platform_name == "Windows" else ""
    assert (
        netconvert_setup._tool_filename("netconvert")
        == f"netconvert{expected_suffix}"
    )


def test_operating_system_rejects_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(netconvert_setup.platform, "system", lambda: "FreeBSD")

    with pytest.raises(netconvert_setup.SetupError, match="Windows, Linux, and macOS"):
        netconvert_setup._operating_system()


def test_posix_environment_block_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sumo_home = tmp_path / "SUMO Runtime"
    profile_path = tmp_path / ".profile"
    profile_path.write_text("export KEEP_ME=1\n", encoding="utf-8")
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))

    netconvert_setup._persist_posix_environment(sumo_home, profile_path)
    netconvert_setup._persist_posix_environment(sumo_home, profile_path)
    profile_text = profile_path.read_text(encoding="utf-8")

    assert "export KEEP_ME=1" in profile_text
    assert profile_text.count(netconvert_setup._MANAGED_BLOCK_START) == 1
    assert (
        f"export SUMO_HOME={netconvert_setup.shlex.quote(str(sumo_home))}"
        in profile_text
    )
    assert 'export PATH="$SUMO_HOME/bin:$PATH"' in profile_text


def test_windows_environment_update_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {"Path": r"C:\Existing"}

    class FakeKey:
        def __enter__(self) -> FakeKey:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def query_value(_key: FakeKey, name: str) -> tuple[str, int]:
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 0

    def set_value(
        _key: FakeKey,
        name: str,
        _reserved: int,
        _value_type: int,
        value: str,
    ) -> None:
        values[name] = value

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_QUERY_VALUE=1,
        KEY_SET_VALUE=2,
        REG_EXPAND_SZ=3,
        REG_SZ=4,
        CreateKeyEx=lambda *_args: FakeKey(),
        QueryValueEx=query_value,
        SetValueEx=set_value,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    sumo_home = tmp_path / "sumo"

    netconvert_setup._persist_windows_environment(sumo_home)
    netconvert_setup._persist_windows_environment(sumo_home)

    assert values["SUMO_HOME"] == str(sumo_home)
    assert values["Path"].split(";").count(str(sumo_home / "bin")) == 1


def test_install_sumo_uses_official_wheel_and_validates_binaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        target_index = command.index("--target") + 1
        bin_directory = Path(command[target_index]) / "sumo" / "bin"
        bin_directory.mkdir(parents=True)
        for tool_name in ("sumo", "netconvert"):
            (bin_directory / tool_name).write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(netconvert_setup.subprocess, "run", fake_run)

    sumo_home = netconvert_setup.install_sumo(tmp_path / "runtime", "Linux")

    assert sumo_home == (tmp_path / "runtime" / "sumo").resolve()
    assert commands == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--upgrade",
            "--target",
            str((tmp_path / "runtime").resolve()),
            "eclipse-sumo",
        ]
    ]


def test_main_reuses_existing_tools_without_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ready_installation = netconvert_setup.SumoInstallation(
        sumo_home=tmp_path,
        sumo_on_path=tmp_path / "sumo",
        netconvert_on_path=tmp_path / "netconvert",
    )
    monkeypatch.setattr(netconvert_setup, "_operating_system", lambda: "Linux")
    monkeypatch.setattr(
        netconvert_setup,
        "inspect_installation",
        lambda *_args, **_kwargs: ready_installation,
    )
    monkeypatch.setattr(
        netconvert_setup,
        "verify_installation",
        lambda _installation: None,
    )
    monkeypatch.setattr(
        netconvert_setup,
        "install_sumo",
        lambda *_args, **_kwargs: pytest.fail("SUMO should not be reinstalled"),
    )

    exit_code = netconvert_setup.main([])

    assert exit_code == 0
    assert "Operating system: Linux" in capsys.readouterr().out


def test_setup_netconvert_installs_configures_and_verifies_missing_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_installation = netconvert_setup.SumoInstallation(None, None, None)
    sumo_home = tmp_path / "runtime" / "sumo"
    ready_installation = netconvert_setup.SumoInstallation(
        sumo_home,
        sumo_home / "bin" / "sumo",
        sumo_home / "bin" / "netconvert",
    )
    inspections = iter([missing_installation, ready_installation])
    configured: list[tuple[Path, str]] = []
    verified: list[netconvert_setup.SumoInstallation] = []

    monkeypatch.setattr(netconvert_setup, "_operating_system", lambda: "Linux")
    monkeypatch.setattr(
        netconvert_setup,
        "inspect_installation",
        lambda *_args, **_kwargs: next(inspections),
    )
    monkeypatch.setattr(
        netconvert_setup,
        "install_sumo",
        lambda install_root, system_name: (
            sumo_home
            if install_root == tmp_path / "runtime" and system_name == "Linux"
            else pytest.fail("Unexpected installation arguments")
        ),
    )
    monkeypatch.setattr(
        netconvert_setup,
        "configure_environment",
        lambda home, system_name: configured.append((home, system_name))
        or tmp_path / ".profile",
    )
    monkeypatch.setattr(
        netconvert_setup,
        "verify_installation",
        lambda installation: verified.append(installation),
    )

    returned_installation = netconvert_setup.setup_netconvert(
        install_dir=tmp_path / "runtime"
    )

    assert returned_installation == ready_installation
    assert configured == [(sumo_home, "Linux")]
    assert verified == [ready_installation]


def test_check_mode_reports_missing_tools_without_changes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(netconvert_setup, "_operating_system", lambda: "Darwin")
    monkeypatch.setattr(
        netconvert_setup,
        "inspect_installation",
        lambda *_args, **_kwargs: netconvert_setup.SumoInstallation(None, None, None),
    )
    monkeypatch.setattr(
        netconvert_setup,
        "install_sumo",
        lambda *_args, **_kwargs: pytest.fail("Check mode must not install SUMO"),
    )
    monkeypatch.setattr(
        netconvert_setup,
        "configure_environment",
        lambda *_args, **_kwargs: pytest.fail("Check mode must not change PATH"),
    )

    exit_code = netconvert_setup.main(["--check"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Operating system: macOS" in captured.out
    assert "Missing from PATH: sumo, netconvert" in captured.err
