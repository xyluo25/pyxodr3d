from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .__xodr_reader import (
    OpenDriveMap,
    readXodr,
)

from . import __xodr_reader as xodr


from .__xodr_sumo import (
    xodr_to_net_xml,
    xodr_from_net_xml,
)

if TYPE_CHECKING:
    from .__netconvert import SumoInstallation

# from .web import web_viewer, run_server
from .web import xodr_web_viewer


def setup_netconvert(
    *,
    check: bool = False,
    install_dir: str | Path | None = None,
) -> SumoInstallation:
    """Install or verify SUMO and expose netconvert on the user PATH.

    Args:
        check: When true, verify only without installing or changing the
            persistent environment.
        install_dir: Optional directory for a user-local SUMO installation.

    Returns:
        SumoInstallation: The verified SUMO installation and executable paths.
    """

    from .__netconvert import setup_netconvert as run_setup

    return run_setup(check=check, install_dir=install_dir)


__all__ = [
    "OpenDriveMap",
    "readXodr",
    "xodr",  # include opendrive components for direct access

    # xodr and sumo conversion
    "xodr_to_net_xml",
    "xodr_from_net_xml",
    "setup_netconvert",

    # Web viewer
    "xodr_web_viewer",
]
