"""Install and configure SUMO's command-line tools for pyxodr3d.

The setup is explicit: importing pyxodr3d never installs software or changes
the user's environment. Run this script when SUMO and netconvert need to be
configured.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
from typing import Sequence


_MANAGED_BLOCK_START = "# >>> pyxodr3d SUMO setup >>>"
_MANAGED_BLOCK_END = "# <<< pyxodr3d SUMO setup <<<"


class SetupError(RuntimeError):
    """Report an actionable SUMO setup failure."""


@dataclass(frozen=True)
class SumoInstallation:
    """Paths discovered for one SUMO installation."""

    sumo_home: Path | None
    sumo_on_path: Path | None
    netconvert_on_path: Path | None

    @property
    def ready(self) -> bool:
        """Return whether both required executables are already on PATH."""

        return self.sumo_on_path is not None and self.netconvert_on_path is not None

    @property
    def can_configure(self) -> bool:
        """Return whether a complete installation can be added to PATH."""

        if self.sumo_home is None:
            return False
        return all(
            _tool_in_home(self.sumo_home, tool_name) is not None
            for tool_name in ("sumo", "netconvert")
        )


def _operating_system() -> str:
    """Return a supported operating-system identifier."""

    system_name = platform.system()
    if system_name not in {"Windows", "Linux", "Darwin"}:
        raise SetupError(
            f"Unsupported operating system: {system_name or 'unknown'}. "
            "This setup supports Windows, Linux, and macOS."
        )
    return system_name


def _display_system_name(system_name: str) -> str:
    return "macOS" if system_name == "Darwin" else system_name


def _tool_filename(tool_name: str, system_name: str | None = None) -> str:
    active_system = system_name or platform.system()
    suffix = ".exe" if active_system == "Windows" else ""
    return f"{tool_name}{suffix}"


def _tool_in_home(
    sumo_home: Path,
    tool_name: str,
    system_name: str | None = None,
) -> Path | None:
    candidate = sumo_home / "bin" / _tool_filename(tool_name, system_name)
    return candidate if candidate.is_file() else None


def _which(tool_name: str) -> Path | None:
    executable = shutil.which(tool_name)
    return Path(executable).resolve() if executable else None


def _imported_sumo_home() -> Path | None:
    """Read SUMO_HOME from an installed eclipse-sumo Python package."""

    try:
        sumo_module = importlib.import_module("sumo")
        module_home = getattr(sumo_module, "SUMO_HOME")
    except (ImportError, AttributeError, OSError):
        return None
    return Path(module_home).expanduser().resolve()


def _known_sumo_homes(system_name: str) -> list[Path]:
    """Return common installation locations for the active operating system."""

    candidates: list[Path] = []
    if system_name == "Windows":
        for variable_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base_value = os.environ.get(variable_name)
            if not base_value:
                continue
            base_path = Path(base_value)
            candidates.extend(
                [
                    base_path / "Eclipse" / "Sumo",
                    base_path / "Programs" / "Eclipse" / "Sumo",
                    *sorted(base_path.glob("sumo-*"), reverse=True),
                ]
            )
    elif system_name == "Linux":
        candidates.extend(
            [
                Path("/opt/sumo"),
                Path("/usr/local/share/sumo"),
                Path("/usr/share/sumo"),
            ]
        )
    else:
        candidates.extend(
            [
                Path("/Library/sumo"),
                Path("/opt/homebrew/opt/sumo/share/sumo"),
                Path("/usr/local/opt/sumo/share/sumo"),
                Path("/usr/local/share/sumo"),
            ]
        )
    candidates.append(_default_install_root(system_name) / "sumo")
    return candidates


def _discover_sumo_home(
    system_name: str,
    *,
    preferred_home: Path | None = None,
) -> Path | None:
    """Find a SUMO home that contains both required command-line tools."""

    candidates: list[Path] = []
    if preferred_home is not None:
        candidates.append(preferred_home)

    configured_home = os.environ.get("SUMO_HOME")
    if configured_home:
        candidates.append(Path(configured_home))

    imported_home = _imported_sumo_home()
    if imported_home is not None:
        candidates.append(imported_home)
    candidates.extend(_known_sumo_homes(system_name))

    for tool_name in ("sumo", "netconvert"):
        tool_path = _which(tool_name)
        if tool_path is not None and tool_path.parent.name.lower() == "bin":
            candidates.append(tool_path.parent.parent)

    seen: set[str] = set()
    for candidate in candidates:
        resolved_candidate = candidate.expanduser().resolve()
        candidate_key = os.path.normcase(str(resolved_candidate))
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        if all(
            _tool_in_home(resolved_candidate, tool_name, system_name) is not None
            for tool_name in ("sumo", "netconvert")
        ):
            return resolved_candidate
    return None


def inspect_installation(
    system_name: str,
    *,
    preferred_home: Path | None = None,
) -> SumoInstallation:
    """Inspect SUMO installation and effective PATH state."""

    return SumoInstallation(
        sumo_home=_discover_sumo_home(
            system_name,
            preferred_home=preferred_home,
        ),
        sumo_on_path=_which("sumo"),
        netconvert_on_path=_which("netconvert"),
    )


def _default_install_root(system_name: str) -> Path:
    if system_name == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base_path = Path(local_app_data) if local_app_data else Path.home()
        return base_path / "pyxodr3d" / "sumo-runtime"
    if system_name == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "pyxodr3d"
            / "sumo-runtime"
        )
    return Path.home() / ".local" / "share" / "pyxodr3d" / "sumo-runtime"


def install_sumo(install_root: Path, system_name: str) -> Path:
    """Install the official eclipse-sumo wheel into a stable user directory."""

    target_path = install_root.expanduser().resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        "--target",
        str(target_path),
        "eclipse-sumo",
    ]
    print(f"Installing SUMO for {_display_system_name(system_name)}...")
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        macos_note = (
            " On macOS, the SUMO wheel may require the dependencies described "
            "in the official SUMO installation guide."
            if system_name == "Darwin"
            else ""
        )
        raise SetupError(f"SUMO installation failed.{macos_note}") from exc

    sumo_home = target_path / "sumo"
    if not all(
        _tool_in_home(sumo_home, tool_name, system_name) is not None
        for tool_name in ("sumo", "netconvert")
    ):
        raise SetupError(
            "eclipse-sumo was installed, but its sumo and netconvert binaries "
            f"were not found under {sumo_home / 'bin'}."
        )
    return sumo_home


def _prepend_process_path(bin_directory: Path) -> None:
    bin_text = str(bin_directory)
    current_entries = [
        entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry
    ]
    normalized_bin = os.path.normcase(os.path.normpath(bin_text))
    if not any(
        os.path.normcase(os.path.normpath(entry)) == normalized_bin
        for entry in current_entries
    ):
        os.environ["PATH"] = os.pathsep.join([bin_text, *current_entries])


def _persist_windows_environment(sumo_home: Path) -> Path:
    """Persist SUMO variables in the current Windows user's environment."""

    import winreg

    bin_directory = sumo_home / "bin"
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
    ) as environment_key:
        try:
            user_path, _ = winreg.QueryValueEx(environment_key, "Path")
        except FileNotFoundError:
            user_path = ""

        path_entries = [entry for entry in user_path.split(";") if entry]
        normalized_bin = os.path.normcase(os.path.normpath(str(bin_directory)))
        if not any(
            os.path.normcase(os.path.normpath(os.path.expandvars(entry)))
            == normalized_bin
            for entry in path_entries
        ):
            path_entries.append(str(bin_directory))
        winreg.SetValueEx(
            environment_key,
            "Path",
            0,
            winreg.REG_EXPAND_SZ,
            ";".join(path_entries),
        )
        winreg.SetValueEx(
            environment_key,
            "SUMO_HOME",
            0,
            winreg.REG_SZ,
            str(sumo_home),
        )
    return Path(r"HKCU\Environment")


def _profile_path(system_name: str) -> Path:
    shell_name = Path(os.environ.get("SHELL", "")).name.lower()
    if shell_name == "zsh":
        return Path.home() / ".zshrc"
    if system_name == "Darwin":
        return Path.home() / ".bash_profile"
    if shell_name == "bash":
        return Path.home() / ".bashrc"
    return Path.home() / ".profile"


def _persist_posix_environment(sumo_home: Path, profile_path: Path) -> Path:
    """Persist SUMO variables in an idempotent managed shell-profile block."""

    quoted_home = shlex.quote(str(sumo_home))
    managed_block = "\n".join(
        [
            _MANAGED_BLOCK_START,
            f"export SUMO_HOME={quoted_home}",
            'case ":$PATH:" in',
            '    *":$SUMO_HOME/bin:"*) ;;',
            '    *) export PATH="$SUMO_HOME/bin:$PATH" ;;',
            "esac",
            _MANAGED_BLOCK_END,
        ]
    )

    existing_text = (
        profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    )
    if _MANAGED_BLOCK_START in existing_text and _MANAGED_BLOCK_END in existing_text:
        before, managed_and_after = existing_text.split(_MANAGED_BLOCK_START, 1)
        _, after = managed_and_after.split(_MANAGED_BLOCK_END, 1)
        prefix = f"{before.rstrip()}\n" if before.strip() else ""
        updated_text = f"{prefix}{managed_block}{after}"
    else:
        separator = "\n\n" if existing_text.strip() else ""
        updated_text = f"{existing_text.rstrip()}{separator}{managed_block}\n"

    if not updated_text.endswith("\n"):
        updated_text += "\n"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(updated_text, encoding="utf-8")
    return profile_path


def configure_environment(sumo_home: Path, system_name: str) -> Path:
    """Add SUMO to the current and future user environments."""

    os.environ["SUMO_HOME"] = str(sumo_home)
    _prepend_process_path(sumo_home / "bin")
    if system_name == "Windows":
        return _persist_windows_environment(sumo_home)
    return _persist_posix_environment(sumo_home, _profile_path(system_name))


def _verify_tool(tool_path: Path, tool_name: str) -> str:
    try:
        completed = subprocess.run(
            [str(tool_path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"Could not run {tool_name}: {tool_path}") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise SetupError(
            f"{tool_name} verification failed with code {completed.returncode}: "
            f"{details or 'no diagnostic output'}"
        )
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else "version check passed"


def verify_installation(installation: SumoInstallation) -> None:
    """Run both required executables and print their resolved versions."""

    if not installation.ready:
        raise SetupError(
            "SUMO setup completed, but its tools are still missing from PATH."
        )
    assert installation.sumo_on_path is not None
    assert installation.netconvert_on_path is not None
    for tool_name, tool_path in (
        ("sumo", installation.sumo_on_path),
        ("netconvert", installation.netconvert_on_path),
    ):
        version_text = _verify_tool(tool_path, tool_name)
        print(f"{tool_name}: {tool_path}")
        print(f"  {version_text}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check for SUMO and netconvert, install SUMO when needed, and "
            "configure the user PATH on Windows, Linux, or macOS."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check and verify only; do not install SUMO or change PATH.",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        help="Override the per-user eclipse-sumo installation directory.",
    )
    return parser


def setup_netconvert(
    *,
    check: bool = False,
    install_dir: str | Path | None = None,
) -> SumoInstallation:
    """Ensure SUMO and netconvert are installed, configured, and executable.

    Args:
        check: When true, verify the existing environment without installing
            SUMO or changing persistent environment settings.
        install_dir: Optional directory for a user-local eclipse-sumo
            installation. The platform-specific default is used when omitted.

    Returns:
        SumoInstallation: The verified SUMO installation and executable paths.

    Raises:
        SetupError: If the operating system is unsupported, check mode finds a
            missing executable, installation fails, or verification fails.
    """

    system_name = _operating_system()
    print(f"Operating system: {_display_system_name(system_name)}")
    installation = inspect_installation(system_name)

    if installation.ready:
        print("SUMO and netconvert are already available on PATH.")
        verify_installation(installation)
        return installation

    if check:
        missing_tools = [
            tool_name
            for tool_name, tool_path in (
                ("sumo", installation.sumo_on_path),
                ("netconvert", installation.netconvert_on_path),
            )
            if tool_path is None
        ]
        raise SetupError(f"Missing from PATH: {', '.join(missing_tools)}.")

    sumo_home = installation.sumo_home
    if installation.can_configure:
        assert sumo_home is not None
        print(f"Found an existing SUMO installation: {sumo_home}")
    else:
        install_root = (
            Path(install_dir)
            if install_dir is not None
            else _default_install_root(system_name)
        )
        sumo_home = install_sumo(install_root, system_name)

    environment_location = configure_environment(sumo_home, system_name)
    print(f"Configured SUMO_HOME: {sumo_home}")
    print(f"Added {sumo_home / 'bin'} to the persistent user PATH.")
    print(f"Environment settings: {environment_location}")

    configured_installation = inspect_installation(
        system_name,
        preferred_home=sumo_home,
    )
    verify_installation(configured_installation)
    print("Open a new terminal to use the persistent PATH settings.")
    return configured_installation


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line adapter for cross-platform SUMO setup."""

    args = _build_parser().parse_args(argv)
    try:
        setup_netconvert(check=args.check, install_dir=args.install_dir)
    except SetupError as exc:
        print(f"SUMO setup error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
