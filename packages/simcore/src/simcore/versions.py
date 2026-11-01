"""Version strings recorded in every result's provenance."""

from importlib.metadata import PackageNotFoundError, version


def simcore_version() -> str:
    """Installed version of this package."""
    try:
        return version("simcore")
    except PackageNotFoundError:
        return "0+unknown"


def rocketpy_version() -> str:
    """Installed RocketPy version, read from package metadata without importing it."""
    try:
        return version("rocketpy")
    except PackageNotFoundError:
        return "not installed"
