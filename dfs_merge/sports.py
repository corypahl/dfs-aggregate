from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SportConfig:
    key: str
    label: str
    fanduel_page_url: str | None
    rotowire_slug: str
    source_labels: tuple[str, ...]


SPORT_CONFIGS: dict[str, SportConfig] = {
    "epl": SportConfig(
        key="epl",
        label="EPL",
        fanduel_page_url=None,
        rotowire_slug="soccer",
        source_labels=("RotoWire",),
    ),
    "nfl": SportConfig(
        key="nfl",
        label="NFL",
        fanduel_page_url="https://www.fanduel.com/research/nfl/fantasy/fantasy-football-projections",
        rotowire_slug="nfl",
        source_labels=("FanDuel", "RotoWire"),
    ),
    "nba": SportConfig(
        key="nba",
        label="NBA",
        fanduel_page_url="https://www.fanduel.com/research/nba/fantasy/dfs-projections",
        rotowire_slug="nba",
        source_labels=("FanDuel", "RotoWire"),
    ),
    "mlb": SportConfig(
        key="mlb",
        label="MLB",
        fanduel_page_url="https://www.fanduel.com/research/mlb/fantasy/dfs-projections",
        rotowire_slug="mlb",
        source_labels=("FanDuel", "RotoWire"),
    ),
}

SPORT_ORDER = ["nfl", "nba", "mlb", "epl"]


def format_sources(config: SportConfig) -> str:
    return " + ".join(config.source_labels)


def get_sport_config(sport: str) -> SportConfig:
    normalized = sport.strip().lower()
    try:
        return SPORT_CONFIGS[normalized]
    except KeyError as exc:
        supported = ", ".join(SPORT_ORDER)
        raise ValueError(f"Unsupported sport '{sport}'. Expected one of: {supported}.") from exc
