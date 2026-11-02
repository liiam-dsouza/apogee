"""Ballast: adding it to a rocket (here) and solving for it (``simcore.ballast.solve``).

The solver imports the engine, which imports this package, so it is not
re-exported here.
"""

from simcore.ballast.mass import as_flown, with_ballast

__all__ = ["as_flown", "with_ballast"]
