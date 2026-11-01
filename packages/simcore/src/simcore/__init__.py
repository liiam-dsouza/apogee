"""Apogee simulation library.

The only package in the project that imports RocketPy (and only inside
``simcore.engine``). It never imports FastAPI or touches HTTP.
"""

from simcore.versions import simcore_version

__version__ = simcore_version()
