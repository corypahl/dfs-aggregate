# DFS Aggregate

This project collects public DFS data from FanDuel Research and RotoWire, then aggregates the player pool into a single board with:

- sortable columns
- position and salary filters
- percentile-based `Avg Proj`, `Avg Value`, and `Grade`
- player highlight badges
- sport support for `NBA`, `MLB`, `NFL`, and `EPL`

The app has two deployment modes:

- local live mode with a working `Refresh Data` button
- static GitHub Pages mode built by GitHub Actions

## Sources

### FanDuel Research

The collector reads the public FanDuel Research pages and uses the public GraphQL projection endpoint exposed by the site.

- NBA: `https://www.fanduel.com/research/nba/fantasy/dfs-projections`
- MLB: `https://www.fanduel.com/research/mlb/fantasy/dfs-projections`
- NFL: `https://www.fanduel.com/research/nfl/fantasy/fantasy-football-projections`

EPL currently has no public FanDuel Research projection source configured in this app, so EPL runs as RotoWire-only.

If that request path changes, the code still keeps a Selenium fallback available.

### RotoWire

The collector reads the public optimizer endpoints used by the RotoWire app itself.

- `https://www.rotowire.com/daily/<sport>/api/slate-list.php?siteID=2`
- `https://www.rotowire.com/daily/<sport>/api/players.php?slateID=<slate_id>`

`siteID=2` is the FanDuel site mapping.

For EPL, the RotoWire slug is `soccer`, so the public optimizer path is:

- `https://www.rotowire.com/daily/soccer/optimizer.php?site=FanDuel`

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run One Sport

Build a single sport into an output directory:

```bash
python main.py --sport nba --output-dir artifacts/latest
```

Optional flags:

```bash
python main.py --sport mlb --output-dir artifacts/latest --browser auto --headless
```

Outputs written under the chosen output directory:

- `aggregate.csv`
- `aggregate.html`
- `name_match_report.json`
- `name_match_report.txt`
- `run_summary.json`
- `raw/fanduel/*`
- `raw/rotowire/*`

## Local Live Server

To use the in-page `Refresh Data` button locally, run:

```bash
python main.py --serve --sport nba --output-dir artifacts/aggregate-test
```

Then open:

```text
http://127.0.0.1:8000/
```

## Build GitHub Pages Site

GitHub Pages cannot run the Python refresh server, so the Pages version is built as a static snapshot for all sports.

Build the static site locally:

```bash
python main.py --build-pages --output-dir artifacts/pages-build --site-dir site
```

This writes:

- `site/index.html`
- `site/nba/index.html`
- `site/mlb/index.html`
- `site/nfl/index.html`

Each sport folder also includes:

- `aggregate.csv`
- `run_summary.json`
- `name_match_report.json`
- `name_match_report.txt`

## GitHub Pages Setup

This repo includes:

- `.github/workflows/pages.yml`

That workflow:

- builds the static Pages site on push to `main` or `master`
- supports manual runs with `workflow_dispatch`
- refreshes the snapshot daily at `15:00 UTC` which is `11:00 AM` in `America/New_York` during daylight saving time
- deploys with the official GitHub Pages Actions flow

After pushing the repo to GitHub:

1. Open the repository on GitHub.
2. Go to `Settings` -> `Pages`.
3. Set the source to `GitHub Actions`.
4. Let the `Deploy GitHub Pages` workflow run.

After deployment, the Pages site will serve the static `site/` build artifact.

## Notes

- `Avg Proj` and `Avg Value` are stored and displayed as percentiles.
- `Grade` is calculated as `((Avg Proj percentile * 2) + (Avg Value percentile * 3)) / 5`.
- Name matching uses exact matches first, then normalization, then salary-gated fuzzy matching.
- Position pills are aggregated by base position. For example, an NBA player with `SF/PF` will match both `SF` and `PF`.
- If a sport shows zero players, that usually means the public source pages are currently empty for that slate or season.
