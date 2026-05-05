from __future__ import annotations

from difflib import SequenceMatcher
import re
from collections import defaultdict
from typing import Any, Iterable

from dfs_merge.models import AggregatedProjection, PlayerProjection
from dfs_merge.utils import clean_name


_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
_SUFFIX_PATTERN = re.compile(r"\b(?:jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)
_REMOVED_CHAR_TABLE = str.maketrans({"'": "", "\u2019": "", ".": ""})
_SALARY_FUZZY_THRESHOLD = 0.66
_TEAM_ALIASES = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "PHO": "PHX",
    "SA": "SAS",
    "WSH": "WAS",
}


def aggregate_player_projections(
    fanduel_records: list[PlayerProjection],
    rotowire_records: list[PlayerProjection],
) -> tuple[list[AggregatedProjection], dict[str, Any]]:
    fanduel_by_name = {record.name: record for record in fanduel_records}
    rotowire_by_name = {record.name: record for record in rotowire_records}

    pairings: list[tuple[PlayerProjection | None, PlayerProjection | None, str]] = []
    exact_names = sorted(set(fanduel_by_name) & set(rotowire_by_name), key=str.casefold)
    matched_fanduel_names = set(exact_names)
    matched_rotowire_names = set(exact_names)

    for name in exact_names:
        pairings.append((fanduel_by_name[name], rotowire_by_name[name], "exact"))

    fanduel_unmatched = {
        name: record
        for name, record in fanduel_by_name.items()
        if name not in matched_fanduel_names
    }
    rotowire_unmatched = {
        name: record
        for name, record in rotowire_by_name.items()
        if name not in matched_rotowire_names
    }

    fanduel_by_normalized_key = _group_by_normalized_name(fanduel_unmatched.values())
    rotowire_by_normalized_key = _group_by_normalized_name(rotowire_unmatched.values())

    normalized_matches: list[dict[str, Any]] = []
    ambiguous_normalized_keys: list[dict[str, Any]] = []
    for normalized_key in sorted(
        set(fanduel_by_normalized_key) & set(rotowire_by_normalized_key),
        key=str.casefold,
    ):
        fanduel_group = sorted(fanduel_by_normalized_key[normalized_key], key=lambda record: record.name.casefold())
        rotowire_group = sorted(
            rotowire_by_normalized_key[normalized_key],
            key=lambda record: record.name.casefold(),
        )

        if len(fanduel_group) == 1 and len(rotowire_group) == 1:
            fanduel_record = fanduel_group[0]
            rotowire_record = rotowire_group[0]
            matched_fanduel_names.add(fanduel_record.name)
            matched_rotowire_names.add(rotowire_record.name)
            pairings.append((fanduel_record, rotowire_record, "normalized_regex"))
            normalized_matches.append(
                {
                    "normalized_key": normalized_key,
                    "fanduel_name": fanduel_record.name,
                    "rotowire_name": rotowire_record.name,
                }
            )
            continue

        ambiguous_normalized_keys.append(
            {
                "normalized_key": normalized_key,
                "fanduel_names": [record.name for record in fanduel_group],
                "rotowire_names": [record.name for record in rotowire_group],
            }
        )

    fuzzy_matches = _match_by_salary_and_fuzzy_name(
        [
            record
            for name, record in fanduel_by_name.items()
            if name not in matched_fanduel_names
        ],
        [
            record
            for name, record in rotowire_by_name.items()
            if name not in matched_rotowire_names
        ],
    )
    for match in fuzzy_matches:
        matched_fanduel_names.add(match["fanduel_name"])
        matched_rotowire_names.add(match["rotowire_name"])
        pairings.append((match["fanduel_record"], match["rotowire_record"], "salary_fuzzy"))

    remaining_fanduel = sorted(
        (
            record
            for name, record in fanduel_by_name.items()
            if name not in matched_fanduel_names
        ),
        key=lambda record: record.name.casefold(),
    )
    remaining_rotowire = sorted(
        (
            record
            for name, record in rotowire_by_name.items()
            if name not in matched_rotowire_names
        ),
        key=lambda record: record.name.casefold(),
    )

    for record in remaining_fanduel:
        pairings.append((record, None, "fanduel_only"))
    for record in remaining_rotowire:
        pairings.append((None, record, "rotowire_only"))

    pairings.sort(key=lambda item: _preferred_name(item[0], item[1]).casefold())

    aggregated_records = [
        AggregatedProjection(
            name=_preferred_name(fanduel_record, rotowire_record),
            fd_position=fanduel_record.position if fanduel_record else None,
            rw_position=rotowire_record.position if rotowire_record else None,
            team=_preferred_team(fanduel_record, rotowire_record),
            salary=_preferred_salary(fanduel_record, rotowire_record),
            fd_projection=fanduel_record.projection if fanduel_record else None,
            fd_value=fanduel_record.value if fanduel_record else None,
            rw_projection=rotowire_record.projection if rotowire_record else None,
            rw_value=rotowire_record.value if rotowire_record else None,
            avg_projection=_average_values(
                fanduel_record.projection if fanduel_record else None,
                rotowire_record.projection if rotowire_record else None,
            ),
            avg_value=_average_values(
                fanduel_record.value if fanduel_record else None,
                rotowire_record.value if rotowire_record else None,
            ),
            grade=None,
        )
        for fanduel_record, rotowire_record, _ in pairings
    ]
    _apply_grades(aggregated_records)

    report = {
        "normalization_rules": [
            "lowercase the full name",
            "remove apostrophes and periods",
            "strip common suffixes: jr, sr, ii, iii, iv, v",
            "remove remaining non-alphanumeric characters before comparing",
            "for unresolved names, compare only players with the same salary and then apply fuzzy matching",
        ],
        "counts": {
            "fanduel_unique_names": len(fanduel_by_name),
            "rotowire_unique_names": len(rotowire_by_name),
            "exact_matches": len(exact_names),
            "normalized_matches": len(normalized_matches),
            "salary_fuzzy_matches": len(fuzzy_matches),
            "ambiguous_normalized_keys": len(ambiguous_normalized_keys),
            "fanduel_unmatched_after_matching": len(remaining_fanduel),
            "rotowire_unmatched_after_matching": len(remaining_rotowire),
            "aggregated_records": len(aggregated_records),
        },
        "exact_matches": exact_names,
        "normalized_matches": normalized_matches,
        "salary_fuzzy_matches": [
            {
                key: value
                for key, value in match.items()
                if key not in {"fanduel_record", "rotowire_record"}
            }
            for match in fuzzy_matches
        ],
        "ambiguous_normalized_keys": ambiguous_normalized_keys,
        "remaining_unmatched": {
            "fanduel": [record.name for record in remaining_fanduel],
            "rotowire": [record.name for record in remaining_rotowire],
        },
    }
    return aggregated_records, report


def render_name_match_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "Name Match Report",
        "=================",
        "",
        f"FanDuel unique names: {counts['fanduel_unique_names']}",
        f"RotoWire unique names: {counts['rotowire_unique_names']}",
        f"Exact matches: {counts['exact_matches']}",
        f"Normalized regex matches: {counts['normalized_matches']}",
        f"Salary-gated fuzzy matches: {counts['salary_fuzzy_matches']}",
        f"Remaining FanDuel-only names: {counts['fanduel_unmatched_after_matching']}",
        f"Remaining RotoWire-only names: {counts['rotowire_unmatched_after_matching']}",
        "",
        "Matching rules:",
    ]
    for rule in report["normalization_rules"]:
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            f"Normalized regex matches ({len(report['normalized_matches'])}):",
        ]
    )
    if report["normalized_matches"]:
        for item in report["normalized_matches"]:
            lines.append(
                f"- {item['fanduel_name']} <-> {item['rotowire_name']} "
                f"[key={item['normalized_key']}]"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            f"Salary-gated fuzzy matches ({len(report['salary_fuzzy_matches'])}):",
        ]
    )
    if report["salary_fuzzy_matches"]:
        for item in report["salary_fuzzy_matches"]:
            lines.append(
                f"- {item['fanduel_name']} <-> {item['rotowire_name']} "
                f"(salary={item['salary']:.0f}; team={item['team']}; score={item['score']:.3f})"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            f"Remaining FanDuel-only names ({len(report['remaining_unmatched']['fanduel'])}):",
        ]
    )
    if report["remaining_unmatched"]["fanduel"]:
        for name in report["remaining_unmatched"]["fanduel"]:
            lines.append(f"- {name}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            f"Remaining RotoWire-only names ({len(report['remaining_unmatched']['rotowire'])}):",
        ]
    )
    if report["remaining_unmatched"]["rotowire"]:
        for name in report["remaining_unmatched"]["rotowire"]:
            lines.append(f"- {name}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def normalize_name_for_matching(name: str) -> str:
    text = clean_name(name).casefold().translate(_REMOVED_CHAR_TABLE)
    text = _SUFFIX_PATTERN.sub(" ", text)
    return _NON_ALNUM_PATTERN.sub("", text)


def _group_by_normalized_name(records: Iterable[PlayerProjection]) -> dict[str, list[PlayerProjection]]:
    grouped: dict[str, list[PlayerProjection]] = defaultdict(list)
    for record in records:
        normalized_key = normalize_name_for_matching(record.name)
        if normalized_key:
            grouped[normalized_key].append(record)
    return grouped


def _match_by_salary_and_fuzzy_name(
    fanduel_records: list[PlayerProjection],
    rotowire_records: list[PlayerProjection],
) -> list[dict[str, Any]]:
    fanduel_by_salary: dict[float, list[PlayerProjection]] = defaultdict(list)
    rotowire_by_salary: dict[float, list[PlayerProjection]] = defaultdict(list)
    for record in fanduel_records:
        if record.salary is not None:
            fanduel_by_salary[_salary_key(record.salary)].append(record)
    for record in rotowire_records:
        if record.salary is not None:
            rotowire_by_salary[_salary_key(record.salary)].append(record)

    candidates: list[dict[str, Any]] = []
    for salary in sorted(set(fanduel_by_salary) & set(rotowire_by_salary)):
        for fanduel_record in fanduel_by_salary[salary]:
            for rotowire_record in rotowire_by_salary[salary]:
                candidate = _build_salary_fuzzy_candidate(fanduel_record, rotowire_record)
                if candidate:
                    candidates.append(candidate)

    if not candidates:
        return []

    best_rotowire_for_fanduel: dict[str, tuple[str, float]] = {}
    best_fanduel_for_rotowire: dict[str, tuple[str, float]] = {}
    for candidate in candidates:
        fanduel_name = candidate["fanduel_name"]
        rotowire_name = candidate["rotowire_name"]
        score = candidate["score"]

        current_fanduel_choice = best_rotowire_for_fanduel.get(fanduel_name)
        if current_fanduel_choice is None or score > current_fanduel_choice[1]:
            best_rotowire_for_fanduel[fanduel_name] = (rotowire_name, score)

        current_rotowire_choice = best_fanduel_for_rotowire.get(rotowire_name)
        if current_rotowire_choice is None or score > current_rotowire_choice[1]:
            best_fanduel_for_rotowire[rotowire_name] = (fanduel_name, score)

    matches: list[dict[str, Any]] = []
    used_fanduel_names: set[str] = set()
    used_rotowire_names: set[str] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (-item["score"], item["fanduel_name"].casefold(), item["rotowire_name"].casefold()),
    ):
        fanduel_name = candidate["fanduel_name"]
        rotowire_name = candidate["rotowire_name"]
        if fanduel_name in used_fanduel_names or rotowire_name in used_rotowire_names:
            continue

        best_rotowire = best_rotowire_for_fanduel.get(fanduel_name)
        best_fanduel = best_fanduel_for_rotowire.get(rotowire_name)
        if best_rotowire is None or best_fanduel is None:
            continue
        if best_rotowire[0] != rotowire_name or best_fanduel[0] != fanduel_name:
            continue

        used_fanduel_names.add(fanduel_name)
        used_rotowire_names.add(rotowire_name)
        matches.append(candidate)

    matches.sort(key=lambda item: (item["fanduel_name"].casefold(), item["rotowire_name"].casefold()))
    return matches


def _build_salary_fuzzy_candidate(
    fanduel_record: PlayerProjection,
    rotowire_record: PlayerProjection,
) -> dict[str, Any] | None:
    if not _same_salary(fanduel_record, rotowire_record):
        return None

    fanduel_team = _team_abbreviation(fanduel_record)
    rotowire_team = _team_abbreviation(rotowire_record)
    if fanduel_team != rotowire_team:
        return None

    if _last_name_key(fanduel_record.name) != _last_name_key(rotowire_record.name):
        return None

    score = SequenceMatcher(
        None,
        normalize_name_for_matching(fanduel_record.name),
        normalize_name_for_matching(rotowire_record.name),
    ).ratio()
    if score < _SALARY_FUZZY_THRESHOLD:
        return None

    return {
        "fanduel_name": fanduel_record.name,
        "rotowire_name": rotowire_record.name,
        "salary": float(fanduel_record.salary or rotowire_record.salary or 0.0),
        "team": fanduel_team,
        "score": score,
        "match_type": "same salary + same team + same last name + fuzzy full-name score",
        "fanduel_record": fanduel_record,
        "rotowire_record": rotowire_record,
    }


def _same_salary(left: PlayerProjection, right: PlayerProjection) -> bool:
    if left.salary is None or right.salary is None:
        return False
    return abs(left.salary - right.salary) < 0.01


def _salary_key(value: float) -> float:
    return round(float(value), 2)


def _team_abbreviation(record: PlayerProjection) -> str | None:
    if record.source == "fanduel":
        team = (record.raw.get("team") or {}).get("abbreviation")
    else:
        team = (record.raw.get("team") or {}).get("abbr")

    if not team:
        return None

    normalized = str(team).strip().upper()
    return _TEAM_ALIASES.get(normalized, normalized)


def _last_name_key(name: str) -> str:
    parts = clean_name(name).split()
    if not parts:
        return ""
    return normalize_name_for_matching(parts[-1])


def _preferred_name(
    fanduel_record: PlayerProjection | None,
    rotowire_record: PlayerProjection | None,
) -> str:
    if fanduel_record:
        return fanduel_record.name
    if rotowire_record:
        return rotowire_record.name
    return ""


def _preferred_salary(
    fanduel_record: PlayerProjection | None,
    rotowire_record: PlayerProjection | None,
) -> float | None:
    if fanduel_record and fanduel_record.salary is not None:
        return fanduel_record.salary
    if rotowire_record:
        return rotowire_record.salary
    return None


def _preferred_team(
    fanduel_record: PlayerProjection | None,
    rotowire_record: PlayerProjection | None,
) -> str | None:
    if fanduel_record:
        team = _team_abbreviation(fanduel_record)
        if team:
            return team
    if rotowire_record:
        return _team_abbreviation(rotowire_record)
    return None


def _average_values(*values: float | None) -> float | None:
    present_values = [float(value) for value in values if value is not None]
    if not present_values:
        return None
    return round(sum(present_values) / len(present_values), 2)


def _apply_grades(records: list[AggregatedProjection]) -> None:
    avg_projection_percentiles = _build_percentile_map(record.avg_projection for record in records)
    avg_value_percentiles = _build_percentile_map(record.avg_value for record in records)

    for record in records:
        raw_avg_projection = record.avg_projection
        raw_avg_value = record.avg_value
        projection_percentile = avg_projection_percentiles.get(raw_avg_projection)
        value_percentile = avg_value_percentiles.get(raw_avg_value)
        record.avg_projection = projection_percentile
        record.avg_value = value_percentile
        record.grade = _calculate_grade(projection_percentile, value_percentile)


def _build_percentile_map(values: Iterable[float | None]) -> dict[float, float]:
    numeric_values = sorted(float(value) for value in values if value is not None)
    if not numeric_values:
        return {}
    if len(numeric_values) == 1:
        return {numeric_values[0]: 100.0}

    percentile_map: dict[float, float] = {}
    index = 0
    last_index = len(numeric_values) - 1
    while index < len(numeric_values):
        value = numeric_values[index]
        end_index = index
        while end_index + 1 < len(numeric_values) and numeric_values[end_index + 1] == value:
            end_index += 1

        average_rank = (index + end_index) / 2
        percentile_map[value] = round((average_rank / last_index) * 100, 2)
        index = end_index + 1

    return percentile_map


def _calculate_grade(
    projection_percentile: float | None,
    value_percentile: float | None,
) -> float | None:
    if projection_percentile is None or value_percentile is None:
        return None
    return round(((projection_percentile * 2) + (value_percentile * 3)) / 5, 2)
