from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

from dfs_merge.frontend import copy_frontend_assets
from dfs_merge.pipeline import run_pipeline
from dfs_merge.sports import SPORT_ORDER, get_sport_config
from dfs_merge.utils import ensure_directory, write_text


SPORT_EMOJI = {
    "nfl": "🏈",
    "nba": "🏀",
    "wnba": "🏀",
    "nhl": "🏒",
    "mlb": "⚾",
    "pga": "⛳",
    "mma": "🥊",
    "nascar": "🏁",
    "cfb": "🏈",
    "cbb": "🏀",
    "cricket": "🏏",
    "epl": "⚽",
}


def build_pages_site(
    *,
    artifacts_root: Path,
    site_dir: Path,
    browser: str = "auto",
    headless: bool = True,
) -> dict[str, Any]:
    ensure_directory(artifacts_root)
    ensure_directory(site_dir)
    copy_frontend_assets(site_dir)

    sport_page_links = {sport: f"../{sport}/" for sport in SPORT_ORDER}
    sport_summaries: list[dict[str, Any]] = []

    for sport in SPORT_ORDER:
        sport_site_dir = site_dir / sport
        if sport_site_dir.exists():
            shutil.rmtree(sport_site_dir)
        ensure_directory(sport_site_dir)

        sport_output_dir = artifacts_root / sport
        summary = run_pipeline(
            output_dir=sport_output_dir,
            browser=browser,
            headless=headless,
            sport=sport,
            report_mode="static",
            sport_page_links=sport_page_links,
            asset_path_prefix="../",
        )
        sport_summaries.append(summary)

        _copy_if_present(Path(summary["aggregate_html"]), sport_site_dir / "index.html")
        _copy_if_present(Path(summary["aggregate_data_json"]), sport_site_dir / "aggregate-data.json")
        _copy_if_present(Path(summary["aggregate_csv"]), sport_site_dir / "aggregate.csv")
        _copy_if_present(Path(summary["run_summary"]), sport_site_dir / "run_summary.json")
        _copy_if_present(Path(summary["name_match_report_json"]), sport_site_dir / "name_match_report.json")
        _copy_if_present(Path(summary["name_match_report_txt"]), sport_site_dir / "name_match_report.txt")

    index_html = render_pages_index(sport_summaries)
    write_text(site_dir / "index.html", index_html)
    write_text(site_dir / "404.html", index_html)
    write_text(site_dir / ".nojekyll", "")

    return {
        "artifacts_root": str(artifacts_root.resolve()),
        "site_dir": str(site_dir.resolve()),
        "sports": [
            {
                "sport": summary["sport"],
                "sport_label": summary["sport_label"],
                "page": str((site_dir / summary["sport"] / "index.html").resolve()),
                "aggregate_csv": str((site_dir / summary["sport"] / "aggregate.csv").resolve()),
                "generated_at": summary["generated_at"],
                "aggregate_record_count": summary["aggregate_record_count"],
                "slate_count": len(summary["rotowire"].get("available_slates") or []),
            }
            for summary in sport_summaries
        ],
    }


def render_pages_index(summaries: list[dict[str, Any]]) -> str:
    rows = []
    built_at = summaries[0]["generated_at"] if summaries else ""
    sorted_summaries = sorted(
        summaries,
        key=lambda summary: (
            len(summary["rotowire"].get("available_slates") or []),
            summary["aggregate_record_count"],
            summary["sport_label"],
        ),
        reverse=True,
    )
    for summary in sorted_summaries:
        sport_config = get_sport_config(summary["sport"])
        rows.append(
            """
            <tr>
              <td><a class="sport-link" href="./{sport}/"><span class="sport-emoji" aria-hidden="true">{emoji}</span>{label}</a></td>
              <td class="numeric-cell">{slates}</td>
              <td class="numeric-cell">{players}</td>
              <td class="numeric-cell">{fanduel}</td>
              <td class="numeric-cell">{rotowire}</td>
            </tr>
            """.format(
                sport=html.escape(summary["sport"], quote=True),
                emoji=html.escape(SPORT_EMOJI.get(summary["sport"], "•"), quote=True),
                label=html.escape(sport_config.label, quote=True),
                slates=html.escape(str(len(summary["rotowire"].get("available_slates") or [])), quote=True),
                players=html.escape(str(summary["aggregate_record_count"]), quote=True),
                fanduel=html.escape(str(summary["fanduel"]["record_count"]), quote=True),
                rotowire=html.escape(str(summary["rotowire"]["record_count"]), quote=True),
            ).strip()
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DFS Aggregate</title>
  <style>
    :root {{
      color-scheme: light;
      --page-bg: #e9eff7;
      --hero-bg: linear-gradient(135deg, #07172d 0%, #0d2440 48%, #153a60 100%);
      --panel: #ffffff;
      --text: #10233d;
      --muted: #60758f;
      --line: #d7e0eb;
      --accent: #128000;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Proxima Nova", "Avenir Next", "Segoe UI", sans-serif;
      background: var(--page-bg);
      color: var(--text);
    }}
    .hero {{
      background: var(--hero-bg);
      color: #ffffff;
    }}
    .hero-inner {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 48px 24px 96px;
    }}
    .built-at {{
      display: inline-flex;
      align-items: center;
      margin-bottom: 14px;
      color: #a9bfd8;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2.4rem, 5vw, 4rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }}
    .content {{
      max-width: 1180px;
      margin: -76px auto 0;
      padding: 0 24px 48px;
    }}
    .panel {{
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 0;
      box-shadow: 0 24px 60px rgba(10, 24, 44, 0.12);
      overflow: hidden;
    }}
    .sport-table-shell {{
      overflow-x: auto;
      background: #ffffff;
    }}
    .sport-table {{
      width: 100%;
      min-width: 720px;
      border-collapse: collapse;
    }}
    .sport-table th,
    .sport-table td {{
      padding: 13px 16px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
    }}
    .sport-table th {{
      background: #f4f7fb;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .sport-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .sport-table tbody tr:hover td {{
      background: #eef5ff;
    }}
    .sport-link {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--header);
      font-weight: 800;
      text-decoration: none;
    }}
    .sport-link:hover {{
      color: #1d68ff;
    }}
    .sport-emoji {{
      display: inline-flex;
      width: 1.4rem;
      justify-content: center;
      font-size: 1.05rem;
      line-height: 1;
    }}
    .numeric-cell {{
      text-align: right;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }}
    code {{
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 0.95em;
    }}
    @media (max-width: 720px) {{
      .hero-inner {{
        padding-bottom: 96px;
      }}
      .content {{
        margin-top: -62px;
        padding-inline: 16px;
      }}
      .panel {{
        padding: 18px;
      }}
    }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="hero-inner">
      <h1>DFS Aggregate</h1>
      <span class="built-at">Built {html.escape(built_at, quote=True)}</span>
    </div>
  </section>
  <main class="content">
    <section class="panel">
      <div class="sport-table-shell">
        <table class="sport-table">
          <thead>
            <tr>
              <th>Sport</th>
              <th class="numeric-cell">Slates</th>
              <th class="numeric-cell">Players</th>
              <th class="numeric-cell">FanDuel</th>
              <th class="numeric-cell">RotoWire</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _copy_if_present(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    ensure_directory(destination.parent)
    shutil.copy2(source, destination)
