from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LineupTemplate:
    slots: tuple[str, ...]
    position_map: dict[str, tuple[str, ...]]
    fallback_salary_cap: int


@dataclass(frozen=True, slots=True)
class SportConfig:
    key: str
    label: str
    fanduel_page_url: str | None
    rotowire_slug: str
    source_labels: tuple[str, ...]
    lineup_templates: dict[str, LineupTemplate]


SPORT_CONFIGS: dict[str, SportConfig] = {
    "epl": SportConfig(
        key="epl",
        label="EPL",
        fanduel_page_url=None,
        rotowire_slug="soccer",
        source_labels=("RotoWire",),
        lineup_templates={
            "full_roster": LineupTemplate(
                slots=("F/M", "F/M", "F/M", "F/M", "D", "D", "GK"),
                position_map={"F/M": ("F", "M")},
                fallback_salary_cap=100,
            ),
        },
    ),
    "nfl": SportConfig(
        key="nfl",
        label="NFL",
        fanduel_page_url="https://www.fanduel.com/research/nfl/fantasy/fantasy-football-projections",
        rotowire_slug="nfl",
        source_labels=("FanDuel", "RotoWire"),
        lineup_templates={
            "full_roster": LineupTemplate(
                slots=("QB", "RB", "RB", "WR", "WR", "WR", "TE", "K", "D"),
                position_map={},
                fallback_salary_cap=60000,
            ),
        },
    ),
    "nba": SportConfig(
        key="nba",
        label="NBA",
        fanduel_page_url="https://www.fanduel.com/research/nba/fantasy/dfs-projections",
        rotowire_slug="nba",
        source_labels=("FanDuel", "RotoWire"),
        lineup_templates={
            "full_roster": LineupTemplate(
                slots=("PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C"),
                position_map={},
                fallback_salary_cap=60000,
            ),
        },
    ),
    "mlb": SportConfig(
        key="mlb",
        label="MLB",
        fanduel_page_url="https://www.fanduel.com/research/mlb/fantasy/dfs-projections",
        rotowire_slug="mlb",
        source_labels=("FanDuel", "RotoWire"),
        lineup_templates={
            "full_roster": LineupTemplate(
                slots=("P", "C/1B", "2B", "3B", "SS", "OF", "OF", "OF", "UTIL"),
                position_map={
                    "C/1B": ("C", "1B"),
                    "UTIL": ("C", "1B", "2B", "3B", "SS", "OF"),
                },
                fallback_salary_cap=35000,
            ),
        },
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


def normalize_contest_type(contest_type: str | None) -> str:
    text = (contest_type or "").strip().lower()
    if text == "full roster":
        return "full_roster"
    if text == "singlegame":
        return "single_game"
    return "full_roster"


def get_lineup_template(sport: str, contest_type: str | None) -> LineupTemplate | None:
    config = get_sport_config(sport)
    return config.lineup_templates.get(normalize_contest_type(contest_type))
