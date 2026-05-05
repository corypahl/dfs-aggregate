from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Any

from dfs_merge.frontend import copy_frontend_assets
from dfs_merge.pipeline import run_pipeline
from dfs_merge.sports import SPORT_ORDER, get_sport_config
from dfs_merge.utils import ensure_directory, write_text


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
            }
            for summary in sport_summaries
        ],
    }


def render_pages_index(summaries: list[dict[str, Any]]) -> str:
    cards = []
    for summary in summaries:
        sport_config = get_sport_config(summary["sport"])
        cards.append(
            """
            <a class="sport-card" href="./{sport}/">
              <span class="sport-card-label">{label}</span>
              <strong class="sport-card-count">{players}</strong>
              <span class="sport-card-copy">players aggregated</span>
              <dl class="sport-card-meta">
                <div><dt>FanDuel</dt><dd>{fanduel}</dd></div>
                <div><dt>RotoWire</dt><dd>{rotowire}</dd></div>
              </dl>
              <span class="sport-card-updated">Built {updated}</span>
            </a>
            """.format(
                sport=html.escape(summary["sport"], quote=True),
                label=html.escape(sport_config.label, quote=True),
                players=html.escape(str(summary["aggregate_record_count"]), quote=True),
                fanduel=html.escape(str(summary["fanduel"]["record_count"]), quote=True),
                rotowire=html.escape(str(summary["rotowire"]["record_count"]), quote=True),
                updated=html.escape(summary["generated_at"], quote=True),
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
      padding: 48px 24px 112px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 14px;
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
      font-size: clamp(2.4rem, 5vw, 4rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }}
    .hero-copy {{
      margin: 16px 0 0;
      max-width: 720px;
      color: #d7e3f4;
      font-size: 1rem;
      line-height: 1.6;
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
      padding: 22px;
      box-shadow: 0 24px 60px rgba(10, 24, 44, 0.12);
    }}
    .panel-copy {{
      margin: 0 0 20px;
      color: var(--muted);
      line-height: 1.55;
    }}
    .sport-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .sport-card {{
      display: grid;
      gap: 8px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: #ffffff;
      text-decoration: none;
      color: inherit;
      box-shadow: 0 12px 30px rgba(10, 24, 44, 0.08);
      transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
    }}
    .sport-card:hover {{
      transform: translateY(-2px);
      border-color: #9cb5d6;
      box-shadow: 0 18px 36px rgba(10, 24, 44, 0.12);
    }}
    .sport-card-label {{
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .sport-card-count {{
      font-size: 2rem;
      letter-spacing: -0.05em;
    }}
    .sport-card-copy {{
      color: var(--muted);
    }}
    .sport-card-meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin: 6px 0 0;
    }}
    .sport-card-meta div {{
      padding: 10px 12px;
      border-radius: 14px;
      background: #f4f7fb;
    }}
    .sport-card-meta dt {{
      margin: 0 0 4px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .sport-card-meta dd {{
      margin: 0;
      font-weight: 700;
    }}
    .sport-card-updated {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .footnote {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.55;
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
      <span class="eyebrow">GitHub Pages Ready</span>
      <h1>DFS Aggregate</h1>
      <p class="hero-copy">Static sport pages generated from the public FanDuel Research and RotoWire data sources. Each page keeps the sortable table, percentile-driven grading, and streamlined filters, while GitHub Actions handles rebuilding the snapshot.</p>
    </div>
  </section>
  <main class="content">
    <section class="panel">
      <p class="panel-copy">Choose a sport to open its latest aggregate board. The Pages site is static by design, so local live refresh still lives in <code>python main.py --serve</code>, while GitHub Actions publishes the static snapshot here.</p>
      <div class="sport-grid">
        {"".join(cards)}
      </div>
      <p class="footnote">If a sport has zero players, that usually means the public source pages are currently empty for that slate or season.</p>
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
