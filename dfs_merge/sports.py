from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SportConfig:
    key: str
    label: str
    fanduel_page_url: str
    rotowire_slug: str


SPORT_CONFIGS: dict[str, SportConfig] = {
    "nfl": SportConfig(
        key="nfl",
        label="NFL",
        fanduel_page_url="https://www.fanduel.com/research/nfl/fantasy/fantasy-football-projections",
        rotowire_slug="nfl",
    ),
    "nba": SportConfig(
        key="nba",
        label="NBA",
        fanduel_page_url="https://www.fanduel.com/research/nba/fantasy/dfs-projections",
        rotowire_slug="nba",
    ),
    "mlb": SportConfig(
        key="mlb",
        label="MLB",
        fanduel_page_url="https://www.fanduel.com/research/mlb/fantasy/dfs-projections",
        rotowire_slug="mlb",
    ),
}

SPORT_ORDER = ["nfl", "nba", "mlb"]


def get_sport_config(sport: str) -> SportConfig:
    normalized = sport.strip().lower()
    try:
        return SPORT_CONFIGS[normalized]
    except KeyError as exc:
        supported = ", ".join(SPORT_ORDER)
        raise ValueError(f"Unsupported sport '{sport}'. Expected one of: {supported}.") from exc
