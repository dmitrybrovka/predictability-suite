"""Packaging invariants for the installed distribution."""

from importlib.metadata import version
from importlib.resources import files

import predictability


def test_installed_metadata_matches_module_version() -> None:
    """`hatch.version` reads __init__, so a stale install fails here."""
    assert version("predictability") == predictability.__version__


def test_version_is_semver_like() -> None:
    parts = predictability.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_py_typed_marker_is_packaged() -> None:
    assert files("predictability").joinpath("py.typed").is_file()
