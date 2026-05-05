from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

from dfs_merge.fanduel import FanDuelCollector
from dfs_merge.frontend import FrontendAssets, copy_frontend_assets, load_frontend_assets
from dfs_merge.models import AggregatedProjection
from dfs_merge.name_matching import aggregate_player_projections, render_name_match_report
from dfs_merge.rotowire import RotoWireCollector
from dfs_merge.sports import SPORT_ORDER, format_sources, get_lineup_template, get_sport_config
from dfs_merge.utils import ensure_directory, utc_now_iso, write_json, write_text

POSITION_SORT_ORDERS = {
    "epl": {"GK": 0, "D": 1, "M": 2, "F": 3},
    "nba": {"PG": 0, "SG": 1, "SF": 2, "PF": 3, "C": 4},
    "nfl": {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "D/ST": 5, "DST": 5},
    "mlb": {"P": 0, "C": 1, "1B": 2, "2B": 3, "3B": 4, "SS": 5, "OF": 6},
}
GENERIC_POSITION_BUCKETS = {"UTIL", "FLEX", "SUPERFLEX", "SUPER FLEX"}


def run_pipeline(
    output_dir: Path,
    browser: str = "auto",
    headless: bool = True,
    sport: str = "nba",
    report_mode: str = "local",
    sport_page_links: dict[str, str] | None = None,
    asset_path_prefix: str = "./",
) -> dict:
    sport_config = get_sport_config(sport)
    ensure_directory(output_dir)
    raw_dir = ensure_directory(output_dir / "raw")
    fanduel_raw_dir = ensure_directory(raw_dir / "fanduel")
    rotowire_raw_dir = ensure_directory(raw_dir / "rotowire")
    generated_at = utc_now_iso()

    fanduel_records, fanduel_metadata = FanDuelCollector(
        browser=browser,
        headless=headless,
        sport=sport_config.key,
    ).collect(fanduel_raw_dir)
    rotowire_slate_collections, rotowire_metadata = RotoWireCollector(sport=sport_config.key).collect_all_slates(
        rotowire_raw_dir
    )
    slate_aggregates = build_slate_aggregates(fanduel_records, rotowire_slate_collections)
    selected_slate_key = select_default_slate_key(
        slate_aggregates=slate_aggregates,
        rotowire_metadata=rotowire_metadata,
        sport=sport_config.key,
    )
    selected_slate_aggregate = next(
        (
            slate_aggregate
            for slate_aggregate in slate_aggregates
            if slate_aggregate["key"] == selected_slate_key
        ),
        slate_aggregates[0],
    )
    aggregated_records = selected_slate_aggregate["records"]
    match_report = selected_slate_aggregate["match_report"]

    aggregate_csv_path = output_dir / "aggregate.csv"
    aggregate_html_path = output_dir / "aggregate.html"
    aggregate_data_json_path = output_dir / "aggregate-data.json"
    name_match_report_json_path = output_dir / "name_match_report.json"
    name_match_report_txt_path = output_dir / "name_match_report.txt"

    write_aggregate_csv(aggregated_records, aggregate_csv_path)

    aggregate_payload = build_aggregate_payload(
        slate_aggregates=slate_aggregates,
        generated_at=generated_at,
        sport=sport_config.key,
        selected_slate_key=selected_slate_key,
        report_mode=report_mode,
    )
    bootstrap_payload = build_bootstrap_payload(
        page_mode=report_mode,
        sport=sport_config.key,
        sport_page_links=sport_page_links,
        initial_data=aggregate_payload,
    )
    frontend_assets = load_frontend_assets()
    copy_frontend_assets(output_dir)
    write_json(aggregate_data_json_path, aggregate_payload)
    write_aggregate_html_report(
        aggregate_html_path,
        title=f"{sport_config.label} DFS Aggregate",
        bootstrap_payload=bootstrap_payload,
        frontend_assets=frontend_assets,
        asset_path_prefix=asset_path_prefix,
    )

    write_json(name_match_report_json_path, match_report)
    write_text(name_match_report_txt_path, render_name_match_report(match_report))

    summary = {
        "generated_at": generated_at,
        "output_dir": str(output_dir.resolve()),
        "sport": sport_config.key,
        "sport_label": sport_config.label,
        "fanduel": fanduel_metadata,
        "rotowire": rotowire_metadata,
        "selected_slate_key": selected_slate_key,
        "selected_slate_label": selected_slate_aggregate["label"],
        "available_slates": [
            {
                "key": slate_aggregate["key"],
                "label": slate_aggregate["label"],
                "slate": slate_aggregate["slate"],
                "record_count": len(slate_aggregate["records"]),
            }
            for slate_aggregate in slate_aggregates
        ],
        "aggregate_record_count": len(aggregated_records),
        "aggregate_csv": str(aggregate_csv_path.resolve()),
        "aggregate_html": str(aggregate_html_path.resolve()),
        "aggregate_data_json": str(aggregate_data_json_path.resolve()),
        "run_summary": str((output_dir / "run_summary.json").resolve()),
        "name_match_report_json": str(name_match_report_json_path.resolve()),
        "name_match_report_txt": str(name_match_report_txt_path.resolve()),
        "name_matching": match_report["counts"],
    }
    write_json(output_dir / "run_summary.json", summary)
    return summary


def aggregate_sources(
    fanduel_records,
    rotowire_records,
) -> tuple[list[AggregatedProjection], dict]:
    return aggregate_player_projections(fanduel_records, rotowire_records)


def build_slate_aggregates(
    fanduel_records: list,
    rotowire_slate_collections: list[dict],
) -> list[dict]:
    if not rotowire_slate_collections:
        records, match_report = aggregate_sources(fanduel_records, [])
        return [
            {
                "key": "no-slate",
                "label": "No available slate",
                "slate": None,
                "records": records,
                "match_report": match_report,
            }
        ]

    slate_aggregates: list[dict] = []
    for slate_collection in rotowire_slate_collections:
        records, match_report = aggregate_sources(fanduel_records, slate_collection["records"])
        slate = slate_collection.get("slate")
        slate_aggregates.append(
            {
                "key": build_slate_key(slate),
                "label": format_slate_label(slate),
                "slate": slate,
                "records": records,
                "match_report": match_report,
            }
        )
    return slate_aggregates


def select_default_slate_key(
    *,
    slate_aggregates: list[dict],
    rotowire_metadata: dict,
    sport: str,
) -> str:
    default_builder_slate = next(
        (
            slate_aggregate
            for slate_aggregate in slate_aggregates
            if (slate_aggregate.get("slate") or {}).get("defaultSlate")
            and get_lineup_template(sport, (slate_aggregate.get("slate") or {}).get("contestType")) is not None
        ),
        None,
    )
    if default_builder_slate is not None:
        return default_builder_slate["key"]

    first_builder_slate = next(
        (
            slate_aggregate
            for slate_aggregate in slate_aggregates
            if get_lineup_template(sport, (slate_aggregate.get("slate") or {}).get("contestType")) is not None
        ),
        None,
    )
    if first_builder_slate is not None:
        return first_builder_slate["key"]

    selected_slate = rotowire_metadata.get("selected_slate") or {}
    selected_slate_id = selected_slate.get("slateID")
    if selected_slate_id is not None:
        candidate_key = f"slate-{selected_slate_id}"
        if any(slate_aggregate["key"] == candidate_key for slate_aggregate in slate_aggregates):
            return candidate_key
    return slate_aggregates[0]["key"]


def build_slate_key(slate: dict | None) -> str:
    if not slate:
        return "no-slate"
    slate_id = slate.get("slateID")
    if slate_id is None:
        return "no-slate"
    return f"slate-{slate_id}"


def format_slate_label(slate: dict | None) -> str:
    if not slate:
        return "No available slate"

    primary_label = slate.get("slateName") or f"Slate {slate.get('slateID', '')}".strip()
    contest_type = slate.get("contestType")
    start_date = slate.get("startDateOnly")
    time_label = slate.get("timeOnly")
    time_display = " ".join(part for part in [start_date, time_label] if part)

    parts = [primary_label, contest_type, time_display]
    return " | ".join(part for part in parts if part)


def write_aggregate_csv(records: list[AggregatedProjection], path: Path) -> None:
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "rw_position",
                "salary",
                "fd_projection",
                "fd_value",
                "rw_projection",
                "rw_value",
                "avg_projection",
                "avg_value",
                "grade",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "name": record.name,
                    "rw_position": record.rw_position,
                    "salary": record.salary,
                    "fd_projection": record.fd_projection,
                    "fd_value": record.fd_value,
                    "rw_projection": record.rw_projection,
                    "rw_value": record.rw_value,
                    "avg_projection": record.avg_projection,
                    "avg_value": record.avg_value,
                    "grade": record.grade,
                }
            )


def build_aggregate_payload(
    *,
    slate_aggregates: list[dict],
    generated_at: str,
    sport: str,
    selected_slate_key: str,
    report_mode: str,
) -> dict[str, Any]:
    sport_config = get_sport_config(sport)
    return {
        "generated_at": generated_at,
        "sport": sport_config.key,
        "sport_label": sport_config.label,
        "sources": list(sport_config.source_labels),
        "sources_label": format_sources(sport_config),
        "hero_text": build_hero_text(sport_config.key, report_mode),
        "selected_slate_key": selected_slate_key,
        "slates": [
            serialize_slate_payload(sport_config.key, slate_aggregate)
            for slate_aggregate in slate_aggregates
        ],
    }


def build_bootstrap_payload(
    *,
    page_mode: str,
    sport: str,
    sport_page_links: dict[str, str] | None,
    initial_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pageMode": page_mode,
        "initialSport": sport,
        "sportOptions": [
            {
                "key": config.key,
                "label": config.label,
                "href": build_sport_option_href(config.key, page_mode, sport_page_links),
            }
            for config in (get_sport_config(key) for key in SPORT_ORDER)
        ],
        "initialData": initial_data,
    }


def build_sport_option_href(
    sport: str,
    page_mode: str,
    sport_page_links: dict[str, str] | None,
) -> str | None:
    if page_mode != "static":
        return None
    if sport_page_links and sport in sport_page_links:
        return sport_page_links[sport]
    return f"../{sport}/"


def write_aggregate_html_report(
    path: Path,
    *,
    title: str,
    bootstrap_payload: dict[str, Any],
    frontend_assets: FrontendAssets,
    asset_path_prefix: str,
) -> None:
    css_links = "\n".join(
        f'  <link rel="stylesheet" href="{escape_attr(resolve_asset_url(asset_path_prefix, css_path))}">'
        for css_path in frontend_assets.css_files
    )
    entry_script_url = escape_attr(resolve_asset_url(asset_path_prefix, frontend_assets.entry_js))
    bootstrap_json = json.dumps(bootstrap_payload, ensure_ascii=True).replace("</", "<\\/")

    html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape_html(title)}</title>
{css_links}
</head>
<body>
  <div id="root"></div>
  <script>
    window.__DFS_AGGREGATE_BOOTSTRAP__ = {bootstrap_json};
  </script>
  <script type="module" src="{entry_script_url}"></script>
</body>
</html>
"""
    write_text(path, html_report)


def resolve_asset_url(asset_path_prefix: str, asset_path: str) -> str:
    cleaned_prefix = asset_path_prefix if asset_path_prefix.endswith("/") else f"{asset_path_prefix}/"
    return f"{cleaned_prefix}{asset_path.lstrip('./')}"


def build_hero_text(sport: str, report_mode: str) -> str:
    sport_config = get_sport_config(sport)
    if report_mode == "static":
        return (
            f"A GitHub Pages-ready static snapshot of aggregated {format_sources(sport_config)} public data, "
            "now rendered through a React frontend so the board can grow toward the fuller dfs-ui builder experience."
        )
    return (
        f"Aggregated {format_sources(sport_config)} public data rendered through a React frontend, with "
        "safe name normalization, salary-aware matching, slate switching, and streamlined position and salary filters."
    )


def serialize_aggregated_record(record: AggregatedProjection) -> dict[str, Any]:
    builder_position = record.fd_position or record.rw_position
    return {
        "name": record.name,
        "fd_position": record.fd_position,
        "rw_position": record.rw_position,
        "team": record.team,
        "salary": record.salary,
        "fd_projection": record.fd_projection,
        "fd_value": record.fd_value,
        "rw_projection": record.rw_projection,
        "rw_value": record.rw_value,
        "avg_projection": record.avg_projection,
        "avg_value": record.avg_value,
        "grade": record.grade,
        "position_filter_values": split_position_filter_values(record.rw_position),
        "builder_position": builder_position,
        "builder_position_values": split_builder_position_values(builder_position),
    }


def serialize_slate_payload(sport: str, slate_aggregate: dict[str, Any]) -> dict[str, Any]:
    slate = slate_aggregate.get("slate") or {}
    lineup_template = get_lineup_template(sport, slate.get("contestType"))
    salary_cap = slate.get("salaryCap")
    fallback_salary_cap = lineup_template.fallback_salary_cap if lineup_template else None
    builder_enabled = lineup_template is not None

    return {
        "key": slate_aggregate["key"],
        "label": slate_aggregate["label"],
        "contest_type": slate.get("contestType"),
        "player_count": len(slate_aggregate["records"]),
        "position_options": build_position_options(slate_aggregate["records"], sport),
        "salary_cap": salary_cap if salary_cap is not None else fallback_salary_cap,
        "builder_enabled": builder_enabled,
        "builder_message": None
        if builder_enabled
        else "Lineup builder is currently available for full-roster slates only.",
        "lineup_template": None
        if not lineup_template
        else {
            "slots": list(lineup_template.slots),
            "position_map": {key: list(values) for key, values in lineup_template.position_map.items()},
        },
        "records": [serialize_aggregated_record(record) for record in slate_aggregate["records"]],
    }


def build_position_options(records: list[AggregatedProjection], sport: str) -> list[str]:
    positions = {
        token
        for record in records
        if record.rw_position
        for token in split_position_filter_values(record.rw_position)
    }
    return sorted(positions, key=lambda value: position_sort_key(value, sport))


def position_sort_key(value: str, sport: str) -> tuple[tuple[int, ...], str]:
    normalized = value.strip().upper()
    preferred_order = POSITION_SORT_ORDERS.get(sport, {})
    if normalized in preferred_order:
        return ((preferred_order[normalized],), normalized)
    return ((99,), normalized)


def split_position_filter_values(value: str | None) -> list[str]:
    if not value:
        return []

    text = value.strip().upper()
    protected_text = text.replace("D/ST", "DST_PLACEHOLDER")
    tokens = [
        token.strip().replace("DST_PLACEHOLDER", "D/ST")
        for token in protected_text.split("/")
        if token.strip()
    ]

    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in GENERIC_POSITION_BUCKETS:
            continue
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def split_builder_position_values(value: str | None) -> list[str]:
    if not value:
        return []

    text = value.strip().upper()
    protected_text = text.replace("D/ST", "DST_PLACEHOLDER")
    tokens = [
        token.strip().replace("DST_PLACEHOLDER", "D/ST")
        for token in protected_text.split("/")
        if token.strip()
    ]

    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def escape_html(value: str) -> str:
    return html.escape(value, quote=True)


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)
