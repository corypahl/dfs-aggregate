from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PlayerProjection:
    source: str
    name: str
    position: str | None
    salary: float | None
    projection: float | None
    value: float | None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AggregatedProjection:
    name: str
    fd_position: str | None
    rw_position: str | None
    team: str | None
    salary: float | None
    fd_projection: float | None
    fd_value: float | None
    rw_projection: float | None
    rw_value: float | None
    avg_projection: float | None
    avg_value: float | None
    grade: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
