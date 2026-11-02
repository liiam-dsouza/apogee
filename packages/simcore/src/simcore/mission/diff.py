"""What differs between two missions: the answer to "why did this change?"."""

from typing import Any

from pydantic import BaseModel, Field

#: Lists longer than this (profile levels, polygons) are reported as one change.
_LONG_LIST = 8
#: Bookkeeping that changes without changing a flight.
_IGNORED = {"meta.created_utc", "meta.notes", "meta.authors"}


class Difference(BaseModel):
    path: str = Field(description="Where in the mission, e.g. 'rocket.drag.multiplier'.")
    a: Any = Field(description="Value in the first mission (None if absent).")
    b: Any = Field(description="Value in the second mission (None if absent).")


def _summary(v: Any) -> Any:
    return f"{len(v)} items" if isinstance(v, list) and len(v) > _LONG_LIST else v


def diff_missions(a: dict[str, Any], b: dict[str, Any]) -> list[Difference]:
    """Leaf-level differences between two mission dicts, in document order."""
    out: list[Difference] = []

    def walk(x: Any, y: Any, path: str) -> None:
        if path in _IGNORED or x == y:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for key in list(x) + [k for k in y if k not in x]:
                walk(x.get(key), y.get(key), f"{path}.{key}" if path else key)
        elif (
            isinstance(x, list)
            and isinstance(y, list)
            and len(x) == len(y)
            and len(x) <= _LONG_LIST
            and not all(isinstance(i, int | float) for i in x + y)
        ):
            for i, (xi, yi) in enumerate(zip(x, y, strict=True)):
                walk(xi, yi, f"{path}[{i}]")
        else:
            out.append(Difference(path=path, a=_summary(x), b=_summary(y)))

    walk(a, b, "")
    return out
