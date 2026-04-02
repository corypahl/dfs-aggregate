from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from dfs_merge.fanduel import FanDuelCollector
from dfs_merge.models import AggregatedProjection
from dfs_merge.name_matching import aggregate_player_projections, render_name_match_report
from dfs_merge.rotowire import RotoWireCollector
from dfs_merge.sports import SPORT_ORDER, format_sources, get_sport_config
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
    ).collect(
        fanduel_raw_dir
    )
    rotowire_records, rotowire_metadata = RotoWireCollector(sport=sport_config.key).collect(rotowire_raw_dir)
    aggregated_records, match_report = aggregate_sources(fanduel_records, rotowire_records)

    aggregate_csv_path = output_dir / "aggregate.csv"
    aggregate_html_path = output_dir / "aggregate.html"
    name_match_report_json_path = output_dir / "name_match_report.json"
    name_match_report_txt_path = output_dir / "name_match_report.txt"

    write_aggregate_csv(aggregated_records, aggregate_csv_path)
    write_aggregate_html_report(
        aggregated_records,
        aggregate_html_path,
        generated_at=generated_at,
        sport=sport_config.key,
        report_mode=report_mode,
        sport_page_links=sport_page_links,
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
        "aggregate_record_count": len(aggregated_records),
        "aggregate_csv": str(aggregate_csv_path.resolve()),
        "aggregate_html": str(aggregate_html_path.resolve()),
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
            writer.writerow(record.to_dict())


def write_aggregate_html_report(
    records: list[AggregatedProjection],
    path: Path,
    *,
    generated_at: str,
    sport: str,
    report_mode: str = "local",
    sport_page_links: dict[str, str] | None = None,
) -> None:
    sport_config = get_sport_config(sport)
    is_static_site = report_mode == "static"
    columns = [
        {"key": "name", "label": "Name", "type": "text"},
        {"key": "rw_position", "label": "RW Position", "type": "text", "filter": "multiselect"},
        {"key": "salary", "label": "Salary", "type": "number", "currency": True, "filter": "max-number"},
        {"key": "fd_projection", "label": "FD Proj", "type": "number", "bar": True},
        {"key": "fd_value", "label": "FD Value", "type": "number", "bar": True},
        {"key": "rw_projection", "label": "RW Proj", "type": "number", "bar": True},
        {"key": "rw_value", "label": "RW Value", "type": "number", "bar": True},
        {"key": "avg_projection", "label": "Avg Proj", "type": "number", "bar": True, "percent": True},
        {"key": "avg_value", "label": "Avg Value", "type": "number", "bar": True, "percent": True},
        {"key": "grade", "label": "Grade", "type": "number", "bar": True},
    ]
    position_options = build_position_options(records, sport)
    metric_stats = build_metric_stats(records, [column["key"] for column in columns if column.get("bar")])

    rows = []
    for record in records:
        cells = []
        for column in columns:
            value = getattr(record, column["key"])
            if column["type"] == "text":
                display = value or ""
                sort_value = (value or "").lower()
                filter_value = value or ""
                filter_values_attr = ""
                if column.get("filter") == "multiselect":
                    filter_values_attr = (
                        f' data-filter-values="{escape_attr(join_position_filter_values(value))}"'
                    )
                if column["key"] == "name":
                    display_markup = render_name_cell(record)
                else:
                    display_markup = escape_html(display)
            else:
                display = format_number(
                    value,
                    is_currency=column.get("currency", False),
                    is_percent=column.get("percent", False),
                )
                sort_value = "" if value is None else f"{float(value):.10f}"
                filter_value = "" if value is None else str(value)
                filter_values_attr = ""
                display_markup = escape_html(display)
                if column.get("bar"):
                    display_markup = render_metric_cell(
                        display=display,
                        value=value,
                        stats=metric_stats[column["key"]],
                    )

            class_attr = ' class="metric-cell"' if column.get("bar") else ""
            cells.append(
                "<td "
                f'data-sort="{escape_attr(sort_value)}" '
                f'data-filter="{escape_attr(filter_value)}"'
                f"{class_attr}"
                f"{filter_values_attr}>"
                f"{display_markup}"
                "</td>"
            )

        rows.append("<tr>" f"{''.join(cells)}" "</tr>")

    header_cells = []
    position_column_index = next(
        index for index, column in enumerate(columns) if column["key"] == "rw_position"
    )
    salary_column_index = next(
        index for index, column in enumerate(columns) if column["key"] == "salary"
    )
    position_pills_html = render_position_pills(position_options, position_column_index)
    def build_sport_option_value(config_key: str) -> str:
        if not is_static_site:
            return config_key
        if sport_page_links and config_key in sport_page_links:
            return sport_page_links[config_key]
        return f"../{config_key}/"

    sport_options_html = "".join(
        (
            f'<option value="{escape_attr(build_sport_option_value(config.key))}"'
            f'{" selected" if config.key == sport_config.key else ""}>'
            f"{escape_html(config.label)}"
            "</option>"
        )
        for config in (get_sport_config(key) for key in SPORT_ORDER)
    )
    hero_text = (
        f"A GitHub Pages-ready static snapshot of aggregated {format_sources(sport_config)} "
        "public data, with streamlined filters, percentile-based grading, and sport "
        "navigation baked into the page."
        if is_static_site
        else f"Aggregated {format_sources(sport_config)} public data with safe name "
        "normalization, salary-aware matching, sortable research-style columns, and "
        "streamlined position and salary filters."
    )
    toolbar_section_label = "GitHub Pages" if is_static_site else "Research View"
    toolbar_title = "Static sport pages" if is_static_site else "Filters and table actions"
    refresh_button_html = (
        ""
        if is_static_site
        else '<button id="refresh-data" class="action-button primary" type="button">Refresh Data</button>'
    )
    status_label = "Published" if is_static_site else "Last updated"
    status_note_html = (
        '<span class="status-note">Static snapshot. Rebuild via GitHub Actions or a local Pages build.</span>'
        if is_static_site
        else ""
    )
    filter_controls = [
        (
            '<label class="filter-control filter-control-select">'
            '<span class="filter-label">Position</span>'
            f"{position_pills_html}"
            '</label>'
        ),
        (
            '<label class="filter-control filter-control-compact">'
            '<span class="filter-label">Max Salary</span>'
            '<input '
            'class="filter-input" '
            f'data-column-index="{salary_column_index}" '
            'type="text" placeholder="e.g. 6500" '
            'aria-label="Filter Max Salary">'
            "</label>"
        ),
    ]
    for index, column in enumerate(columns):
        header_cells.append(
            "<th "
            f'data-type="{column["type"]}" '
            f'data-filter-mode="{column.get("filter", "text")}" '
            f'data-column-index="{index}">'
            '<button class="sort-button" type="button">'
            f"{escape_html(column['label'])}"
            '<span class="sort-indicator" aria-hidden="true">&#8597;</span>'
            "</button>"
            "</th>"
        )

    html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{sport_config.label} DFS Aggregate</title>
  <style>
    :root {{
      color-scheme: light;
      --page-bg: #e9eff7;
      --hero-bg: linear-gradient(135deg, #07172d 0%, #0d2440 48%, #153a60 100%);
      --panel: #ffffff;
      --panel-soft: #f4f7fb;
      --text: #10233d;
      --muted: #60758f;
      --line: #d7e0eb;
      --line-strong: #bcc9d8;
      --header: #0f223d;
      --header-accent: #8fc4ff;
      --accent: #1d68ff;
      --accent-strong: #128000;
      --pill: #142845;
      --pill-label: #8ea7c6;
    }}
    body {{
      margin: 0;
      font-family: "Proxima Nova", "Avenir Next", "Segoe UI", sans-serif;
      background: var(--page-bg);
      color: var(--text);
    }}
    .page-shell {{
      min-height: 100vh;
    }}
    .hero {{
      background: var(--hero-bg);
      color: #ffffff;
    }}
    .hero-inner {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 32px 24px 118px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-end;
      gap: 24px;
    }}
    .hero-copy {{
      max-width: 760px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
      color: #a9bfd8;
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    .eyebrow::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: #1d68ff;
      box-shadow: 0 0 0 4px rgba(29, 104, 255, 0.16);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2.2rem, 4vw, 3.2rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }}
    .hero-text {{
      margin: 14px 0 0;
      max-width: 660px;
      color: #d7e3f4;
      font-size: 1rem;
      line-height: 1.55;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(150px, 1fr));
      gap: 12px;
      min-width: min(100%, 360px);
    }}
    .meta-card {{
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(10px);
    }}
    .meta-label {{
      display: block;
      margin-bottom: 6px;
      color: #9cb2cf;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .meta-value {{
      display: block;
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .page-content {{
      max-width: 1380px;
      margin: -74px auto 0;
      padding: 0 24px 40px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 18px;
      padding: 18px 20px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 18px 50px rgba(10, 24, 44, 0.12);
    }}
    .toolbar-copy {{
      display: grid;
      gap: 4px;
    }}
    .section-label {{
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    .toolbar-title {{
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .filter-panel {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .filter-control {{
      display: grid;
      gap: 8px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.94);
      box-shadow: 0 12px 30px rgba(10, 24, 44, 0.08);
    }}
    .filter-control-select {{
      grid-column: span 2;
    }}
    .filter-control-compact {{
      max-width: 220px;
    }}
    .filter-label {{
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 24px 60px rgba(10, 24, 44, 0.12);
    }}
    .table-shell {{
      overflow: auto;
    }}
    table {{
      width: 100%;
      min-width: 1180px;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 0.92rem;
    }}
    th,
    td {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      vertical-align: bottom;
    }}
    .header-row th {{
      padding: 0;
      background: var(--header);
      color: #ffffff;
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .header-row th:first-child {{
      border-top-left-radius: 20px;
    }}
    .header-row th:last-child {{
      border-top-right-radius: 20px;
    }}
    .sort-button {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      width: 100%;
      padding: 14px 16px;
      border: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      text-transform: inherit;
      letter-spacing: inherit;
      cursor: pointer;
    }}
    .sort-button:hover {{
      background: rgba(255, 255, 255, 0.04);
    }}
    .sort-indicator {{
      color: var(--header-accent);
      font-size: 0.95rem;
      line-height: 1;
    }}
    .filter-input {{
      width: 100%;
      min-width: 108px;
      box-sizing: border-box;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      padding: 10px 12px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      font-size: 0.84rem;
      text-transform: none;
      letter-spacing: normal;
      box-shadow: inset 0 1px 2px rgba(10, 24, 44, 0.04);
    }}
    .position-pill-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .position-pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 54px;
      padding: 9px 12px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      font-size: 0.84rem;
      font-weight: 700;
      cursor: pointer;
      transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease, box-shadow 120ms ease;
    }}
    .position-pill:hover {{
      border-color: #99b3d8;
      background: #f4f8ff;
    }}
    .position-pill.is-active {{
      background: #113260;
      border-color: #113260;
      color: #ffffff;
      box-shadow: 0 10px 20px rgba(17, 50, 96, 0.2);
    }}
    .position-pill-empty {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .toolbar-select {{
      width: auto;
      min-width: 110px;
      box-sizing: border-box;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      padding: 8px 10px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
      font-size: 0.84rem;
      text-transform: none;
      letter-spacing: normal;
      box-shadow: inset 0 1px 2px rgba(10, 24, 44, 0.04);
    }}
    .filter-input:focus,
    .toolbar-select:focus {{
      outline: 2px solid rgba(29, 104, 255, 0.16);
      border-color: var(--accent);
    }}
    .metric-cell {{
      position: relative;
    }}
    .name-cell {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      min-height: 1.8rem;
    }}
    .name-text {{
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .name-badges {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .name-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.55rem;
      height: 1.55rem;
      padding: 0 6px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 0.82rem;
      font-weight: 800;
      line-height: 1;
    }}
    .name-badge-star {{
      background: #fff3d2;
      border-color: #f3d07a;
      color: #9b6a00;
    }}
    .name-badge-value {{
      background: #e9f8ec;
      border-color: #98d4a9;
      color: #0f7a39;
    }}
    .name-badge-projection {{
      background: #e9f1ff;
      border-color: #a9c2fb;
      color: #1657d8;
      font-size: 0.9rem;
    }}
    .metric-wrap {{
      position: relative;
      overflow: hidden;
      border-radius: 999px;
      background: #edf2f8;
      min-height: 1.8rem;
      display: flex;
      align-items: center;
      padding: 4px 10px;
    }}
    .metric-fill {{
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      border-radius: 999px;
      opacity: 0.28;
      pointer-events: none;
    }}
    .metric-text {{
      position: relative;
      z-index: 1;
      font-variant-numeric: tabular-nums;
    }}
    tbody td {{
      background: #ffffff;
    }}
    tbody tr:nth-child(even) td {{
      background: #fbfcfe;
    }}
    tbody tr:hover td {{
      background: #eef5ff;
    }}
    .actions {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-start;
      gap: 10px;
    }}
    .status {{
      font-size: 0.84rem;
      color: var(--muted);
    }}
    .status-note {{
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .action-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      background: #ffffff;
      color: var(--header);
      padding: 9px 14px;
      cursor: pointer;
      font: inherit;
      font-size: 0.84rem;
      font-weight: 700;
      transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
    }}
    .action-button.primary {{
      background: var(--accent-strong);
      color: #ffffff;
      border-color: var(--accent-strong);
    }}
    .action-button.primary:hover {{
      background: #0f6d00;
      border-color: #0f6d00;
    }}
    .action-button.secondary:hover {{
      background: #f1f5fb;
      border-color: #9bb0c8;
    }}
    .action-button:disabled {{
      opacity: 0.6;
      cursor: progress;
    }}
    @media (max-width: 800px) {{
      .hero-inner {{
        padding-bottom: 104px;
      }}
      .hero-grid {{
        width: 100%;
        grid-template-columns: repeat(2, minmax(130px, 1fr));
      }}
      .page-content {{
        margin-top: -62px;
        padding-inline: 16px;
      }}
      .toolbar {{
        padding: 16px;
      }}
      .filter-panel {{
        grid-template-columns: 1fr;
      }}
      .filter-control-select {{
        grid-column: span 1;
      }}
      table {{
        min-width: 1040px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page-shell">
    <section class="hero">
      <div class="hero-inner">
        <div class="hero-copy">
          <span class="eyebrow">FanDuel Research Inspired</span>
          <h1>{sport_config.label} DFS Aggregate</h1>
          <p class="hero-text">{escape_html(hero_text)}</p>
        </div>
        <div class="hero-grid">
          <div class="meta-card">
            <span class="meta-label">Sport</span>
            <span class="meta-value">{sport_config.label}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">Slate</span>
            <span class="meta-value">Main</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">Sources</span>
            <span class="meta-value">{escape_html(format_sources(sport_config))}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">Players</span>
            <span class="meta-value">{len(records)}</span>
          </div>
        </div>
      </div>
    </section>
    <main class="page-content">
      <div class="toolbar">
        <div class="toolbar-copy">
          <span class="section-label">{escape_html(toolbar_section_label)}</span>
          <div class="toolbar-title">{escape_html(toolbar_title)}</div>
        </div>
        <div class="actions">
          <span class="status" id="refresh-status">{escape_html(status_label)}: {escape_html(generated_at)}</span>
          {status_note_html}
          <select id="sport-select" class="toolbar-select" aria-label="Select sport">
            {sport_options_html}
          </select>
          {refresh_button_html}
          <button id="clear-filters" class="action-button secondary" type="button">Clear Filters</button>
        </div>
      </div>
      <div class="filter-panel">
        {''.join(filter_controls)}
      </div>
      <div class="card">
        <div class="table-shell">
          <table id="aggregate-table">
            <thead>
              <tr class="header-row">
                {''.join(header_cells)}
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
  <script>
    (() => {{
      const pageMode = {json.dumps(report_mode)};
      const table = document.getElementById("aggregate-table");
      const tbody = table.tBodies[0];
      const headers = Array.from(table.querySelectorAll(".header-row th"));
      const filterInputs = Array.from(document.querySelectorAll(".filter-input"));
      const positionPills = Array.from(document.querySelectorAll(".position-pill"));
      const clearButton = document.getElementById("clear-filters");
      const refreshButton = document.getElementById("refresh-data");
      const refreshStatus = document.getElementById("refresh-status");
      const sportSelect = document.getElementById("sport-select");
      const visibleCount = document.getElementById("visible-count");
      const rows = Array.from(tbody.rows);
      const state = {{
        sortIndex: 2,
        sortDir: "desc",
        filters: headers.map((header) =>
          header.dataset.filterMode === "multiselect" ? [] : ""
        ),
      }};

      const compareNumeric = (left, right) => {{
        const leftNumber = Number(left);
        const rightNumber = Number(right);
        if (Number.isNaN(leftNumber) && Number.isNaN(rightNumber)) return 0;
        if (Number.isNaN(leftNumber)) return 1;
        if (Number.isNaN(rightNumber)) return -1;
        return leftNumber - rightNumber;
      }};

      const matchesNumericFilter = (rawValue, query) => {{
        if (!query) return true;
        if (rawValue === "") return false;

        const normalized = query.replace(/\\s+/g, "");
        const match = normalized.match(/^(<=|>=|=|<|>)(-?\\d+(?:\\.\\d+)?)$/);
        if (match) {{
          const operator = match[1];
          const target = Number(match[2]);
          const actual = Number(rawValue);
          if (Number.isNaN(actual)) return false;
          if (operator === "<") return actual < target;
          if (operator === "<=") return actual <= target;
          if (operator === ">") return actual > target;
          if (operator === ">=") return actual >= target;
          return actual === target;
        }}

        return rawValue.toLowerCase().includes(query.toLowerCase());
      }};

      const rowMatches = (row) => {{
        return state.filters.every((query, index) => {{
          const cell = row.cells[index];
          const filterMode = headers[index].dataset.filterMode || "text";
          const rawValue = cell.dataset.filter || "";
          if (filterMode === "multiselect") {{
            if (!Array.isArray(query) || query.length === 0) return true;
            const cellValues = (cell.dataset.filterValues || "")
              .split("|")
              .map((item) => item.trim())
              .filter(Boolean);
            return query.some((item) => cellValues.includes(item));
          }}
          if (filterMode === "max-number") {{
            if (!query) return true;
            if (rawValue === "") return false;
            const normalized = query.replace(/[$,\\s]+/g, "");
            const maxValue = Number(normalized);
            if (Number.isNaN(maxValue)) return true;
            return Number(rawValue) <= maxValue;
          }}

          if (!query) return true;
          const type = headers[index].dataset.type;
          if (type === "number") {{
            return matchesNumericFilter(rawValue, query);
          }}
          return rawValue.toLowerCase().includes(query.toLowerCase());
        }});
      }};

      const compareRows = (leftRow, rightRow) => {{
        const index = state.sortIndex;
        const direction = state.sortDir === "asc" ? 1 : -1;
        const type = headers[index].dataset.type;
        const leftValue = leftRow.cells[index].dataset.sort || "";
        const rightValue = rightRow.cells[index].dataset.sort || "";

        if (!leftValue && !rightValue) return 0;
        if (!leftValue) return 1;
        if (!rightValue) return -1;

        if (type === "number") {{
          return compareNumeric(leftValue, rightValue) * direction;
        }}
        return leftValue.localeCompare(rightValue, undefined, {{ sensitivity: "base" }}) * direction;
      }};

      const updateIndicators = () => {{
        headers.forEach((header, index) => {{
          const indicator = header.querySelector(".sort-indicator");
          if (!indicator) return;
          indicator.textContent =
            state.sortIndex === index
              ? (state.sortDir === "asc" ? "\\u2191" : "\\u2193")
              : "\\u2195";
        }});
      }};

      const render = () => {{
        const filteredRows = rows.filter(rowMatches).sort(compareRows);
        tbody.replaceChildren(...filteredRows);
        if (visibleCount) {{
          visibleCount.textContent = String(filteredRows.length);
        }}
        updateIndicators();
      }};

      headers.forEach((header, index) => {{
        const button = header.querySelector(".sort-button");
        button.addEventListener("click", () => {{
          if (state.sortIndex === index) {{
            state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
          }} else {{
            state.sortIndex = index;
            state.sortDir = header.dataset.type === "number" ? "desc" : "asc";
          }}
          render();
        }});
      }});

      filterInputs.forEach((input) => {{
        const index = Number(input.dataset.columnIndex);
        input.addEventListener("input", (event) => {{
          state.filters[index] = event.target.value.trim();
          render();
        }});
      }});

      positionPills.forEach((pill) => {{
        const index = Number(pill.dataset.columnIndex);
        const value = pill.dataset.value || "";
        pill.addEventListener("click", () => {{
          const currentValues = Array.isArray(state.filters[index]) ? [...state.filters[index]] : [];
          const nextValues = currentValues.includes(value)
            ? currentValues.filter((item) => item !== value)
            : [...currentValues, value];
          state.filters[index] = nextValues;
          const isActive = nextValues.includes(value);
          pill.classList.toggle("is-active", isActive);
          pill.setAttribute("aria-pressed", isActive ? "true" : "false");
          render();
        }});
      }});

      clearButton.addEventListener("click", () => {{
        filterInputs.forEach((input) => {{
          input.value = "";
        }});
        positionPills.forEach((pill) => {{
          pill.classList.remove("is-active");
          pill.setAttribute("aria-pressed", "false");
        }});
        state.filters = headers.map((header) =>
          header.dataset.filterMode === "multiselect" ? [] : ""
        );
        render();
      }});

      if (pageMode === "static") {{
        sportSelect.addEventListener("change", () => {{
          if (sportSelect.value) {{
            window.location.href = sportSelect.value;
          }}
        }});
      }}

      if (refreshButton) {{
        refreshButton.addEventListener("click", async () => {{
          if (!window.location.protocol.startsWith("http")) {{
            refreshStatus.textContent = "Refresh requires local server mode (`python main.py --serve`).";
            return;
          }}

          refreshButton.disabled = true;
          sportSelect.disabled = true;
          refreshStatus.textContent = "Refreshing data...";
          try {{
            const response = await fetch("/refresh", {{
              method: "POST",
              headers: {{
                "Content-Type": "application/json",
              }},
              body: JSON.stringify({{ sport: sportSelect.value }}),
            }});
            if (!response.ok) {{
              throw new Error(`HTTP ${{response.status}}`);
            }}
            refreshStatus.textContent = "Refresh complete. Reloading...";
            window.location.reload();
          }} catch (error) {{
            refreshStatus.textContent = `Refresh failed: ${{error.message}}`;
            refreshButton.disabled = false;
            sportSelect.disabled = false;
          }}
        }});
      }}

      render();
    }})();
  </script>
</body>
</html>
"""
    write_text(path, html_report)


def build_position_options(records: list[AggregatedProjection], sport: str) -> list[str]:
    positions = {
        token
        for record in records
        if record.rw_position
        for token in split_position_filter_values(record.rw_position)
    }
    return sorted(positions, key=lambda value: position_sort_key(value, sport))


def render_position_pills(position_options: list[str], column_index: int) -> str:
    if not position_options:
        return '<div class="position-pill-empty">No positions available for the current sport.</div>'

    pills = []
    for option in position_options:
        pills.append(
            '<button '
            'type="button" '
            'class="position-pill" '
            f'data-column-index="{column_index}" '
            f'data-value="{escape_attr(option)}" '
            f'aria-pressed="false">'
            f"{escape_html(option)}"
            "</button>"
        )
    return f'<div class="position-pill-group">{"".join(pills)}</div>'


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


def join_position_filter_values(value: str | None) -> str:
    return "|".join(split_position_filter_values(value))


def build_metric_stats(records: list[AggregatedProjection], keys: list[str]) -> dict[str, dict[str, float | None]]:
    stats: dict[str, dict[str, float | None]] = {}
    for key in keys:
        values = [float(value) for value in (getattr(record, key) for record in records) if value is not None]
        stats[key] = {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return stats


def render_name_cell(record: AggregatedProjection) -> str:
    name_markup = f'<span class="name-text">{escape_html(record.name)}</span>'
    badge_markup = render_name_badges(record)
    if not badge_markup:
        return f'<span class="name-cell">{name_markup}</span>'
    return (
        '<span class="name-cell">'
        f"{name_markup}"
        '<span class="name-badges">'
        f"{badge_markup}"
        "</span>"
        "</span>"
    )


def render_name_badges(record: AggregatedProjection) -> str:
    has_projection_highlight = record.avg_projection is not None and record.avg_projection >= 90.0
    has_value_highlight = record.avg_value is not None and record.avg_value >= 90.0

    if has_projection_highlight and has_value_highlight:
        return (
            '<span class="name-badge name-badge-star" '
            'title="90th+ percentile in Avg Proj and Avg Value"'
            ' aria-label="Elite projection and value">&#9733;</span>'
        )
    if has_value_highlight:
        return (
            '<span class="name-badge name-badge-value" '
            'title="90th+ percentile in Avg Value"'
            ' aria-label="Elite value">$</span>'
        )
    if has_projection_highlight:
        return (
            '<span class="name-badge name-badge-projection" '
            'title="90th+ percentile in Avg Proj"'
            ' aria-label="Elite projection">&#128170;</span>'
        )
    return ""


def render_metric_cell(display: str, value: float | None, stats: dict[str, float | None]) -> str:
    if value is None:
        return ""

    ratio = metric_ratio(float(value), stats)
    color = metric_bar_color(ratio)
    width = ratio * 100
    return (
        '<div class="metric-wrap">'
        f'<span class="metric-fill" style="width: {width:.1f}%; background: {color};"></span>'
        f'<span class="metric-text">{escape_html(display)}</span>'
        "</div>"
    )


def metric_ratio(value: float, stats: dict[str, float | None]) -> float:
    min_value = stats.get("min")
    max_value = stats.get("max")
    if min_value is None or max_value is None:
        return 0.0
    if max_value <= min_value:
        return 1.0
    ratio = (value - min_value) / (max_value - min_value)
    return max(0.0, min(1.0, ratio))


def metric_bar_color(ratio: float) -> str:
    hue = 120 * ratio
    return f"hsl({hue:.0f} 72% 45%)"


def escape_html(value: str) -> str:
    return html.escape(value, quote=True)


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def format_number(
    value: float | None,
    is_currency: bool = False,
    is_percent: bool = False,
) -> str:
    if value is None:
        return ""
    if is_currency:
        return f"${value:,.0f}"
    if is_percent:
        return f"{value:.1f}%"
    return f"{value:.2f}"
