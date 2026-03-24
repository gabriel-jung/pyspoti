"""pyspoti -- Python library and CLI for Spotify data."""

from importlib.metadata import version

from . import app, core

__version__ = version("pyspoti")

__all__ = ["__version__", "app", "core"]
