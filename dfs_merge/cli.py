from __future__ import annotations

import argparse
from pathlib import Path

from dfs_merge.pages import build_pages_site
from dfs_merge.pipeline import run_pipeline
from dfs_merge.server import serve_aggregate
from dfs_merge.sports import SPORT_ORDER, get_sport_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect public DFS data from FanDuel Research and RotoWire, then aggregate it.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/latest",
        help="Directory where raw artifacts and aggregate outputs will be written.",
    )
    parser.add_argument(
        "--browser",
        choices=["auto", "edge", "chrome"],
        default="auto",
        help="Browser to use for FanDuel Selenium fallback.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the Selenium browser in headless mode.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a local server for the aggregate page with a working refresh button.",
    )
    parser.add_argument(
        "--build-pages",
        action="store_true",
        help="Build a static multi-sport site suitable for GitHub Pages.",
    )
    parser.add_argument(
        "--site-dir",
        default="site",
        help="Directory where the static GitHub Pages site will be written.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for local server mode.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for local server mode.",
    )
    parser.add_argument(
        "--sport",
        choices=SPORT_ORDER,
        default="nba",
        help="Sport to aggregate.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.build_pages:
        site_dir = Path(args.site_dir)
        summary = build_pages_site(
            artifacts_root=output_dir,
            site_dir=site_dir,
            browser=args.browser,
            headless=args.headless,
        )
        print("GitHub Pages site built.")
        print(f"Artifacts directory: {summary['artifacts_root']}")
        print(f"Site directory: {summary['site_dir']}")
        for sport_summary in summary["sports"]:
            print(
                f"{sport_summary['sport_label']}: "
                f"{sport_summary['aggregate_record_count']} players, "
                f"page={sport_summary['page']}"
            )
        return 0

    if args.serve:
        return serve_aggregate(
            output_dir=output_dir,
            host=args.host,
            port=args.port,
            browser=args.browser,
            headless=args.headless,
            sport=args.sport,
        )

    summary = run_pipeline(
        output_dir=output_dir,
        browser=args.browser,
        headless=args.headless,
        sport=args.sport,
    )
    sport_label = get_sport_config(summary["sport"]).label

    print(f"{sport_label} DFS aggregate written.")
    print(f"Output directory: {summary['output_dir']}")
    print(f"Aggregate CSV: {summary['aggregate_csv']}")
    print(f"Aggregate HTML: {summary['aggregate_html']}")
    print(f"Aggregate Data JSON: {summary['aggregate_data_json']}")
    print(f"Name match report (JSON): {summary['name_match_report_json']}")
    print(f"Name match report (TXT): {summary['name_match_report_txt']}")
    print(f"FanDuel records: {summary['fanduel']['record_count']}")
    print(f"RotoWire records: {summary['rotowire']['record_count']}")
    print(f"Aggregate records: {summary['aggregate_record_count']}")
    print(f"Exact name matches: {summary['name_matching']['exact_matches']}")
    print(f"Normalized name matches: {summary['name_matching']['normalized_matches']}")
    print(f"Salary fuzzy matches: {summary['name_matching']['salary_fuzzy_matches']}")
    print(
        "Remaining unmatched: "
        f"FanDuel {summary['name_matching']['fanduel_unmatched_after_matching']}, "
        f"RotoWire {summary['name_matching']['rotowire_unmatched_after_matching']}"
    )
    return 0
