from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Iterable
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from dfs_merge.browser import build_headless_driver, wait_for_download
from dfs_merge.models import PlayerProjection
from dfs_merge.sports import SportConfig, get_sport_config
from dfs_merge.utils import (
    DEFAULT_HEADERS,
    clean_name,
    combine_name,
    compute_value,
    normalize_key,
    parse_float,
    write_json,
    write_text,
)


GRAPHQL_URL = "https://fdresearch-api.fanduel.com/graphql"
GET_PROJECTIONS_QUERY = """
query GetProjections($input: ProjectionsInput!) {
  getProjections(input: $input) {
    ... on NbaPlayer {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
    ... on MlbBatter {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
    ... on MlbPitcher {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
    ... on NflSkill {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
    ... on NflKicker {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
    ... on NflDefenseSt {
      player {
        name
        position
      }
      salary
      value
      fantasy
      team {
        abbreviation
      }
      gameInfo {
        gameTime
        homeTeam {
          abbreviation
        }
        awayTeam {
          abbreviation
        }
      }
    }
  }
}
"""


class FanDuelCollector:
    def __init__(
        self,
        timeout_seconds: int = 30,
        browser: str = "auto",
        headless: bool = True,
        sport: str = "nba",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.browser = browser
        self.headless = headless
        self.sport_config = get_sport_config(sport)

    def collect(self, raw_dir: Path) -> tuple[list[PlayerProjection], dict]:
        if not self.sport_config.fanduel_page_url:
            metadata = {
                "collection_mode": "not_supported",
                "sport": self.sport_config.label,
                "record_count": 0,
                "reason": "No public FanDuel Research projection source is configured for this sport.",
            }
            write_json(raw_dir / "metadata.json", metadata)
            return [], metadata

        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        page_response = session.get(self.sport_config.fanduel_page_url, timeout=self.timeout_seconds)
        page_response.raise_for_status()
        html = page_response.text
        write_text(raw_dir / "page.html", html)

        next_data = self._extract_next_data(html)
        if next_data is not None:
            write_json(raw_dir / "next_data.json", next_data)

        graphql_rows, graphql_attempted = self._collect_via_graphql(session, next_data, raw_dir)
        if graphql_attempted:
            metadata = {
                "collection_mode": "graphql",
                "sport": self.sport_config.label,
                "record_count": len(graphql_rows),
            }
            return graphql_rows, metadata

        http_rows = self._try_extract_rows_from_next_data(next_data)
        if http_rows:
            metadata = {
                "collection_mode": "http_embedded_json",
                "sport": self.sport_config.label,
                "record_count": len(http_rows),
            }
            return http_rows, metadata

        csv_path = self._download_csv_via_selenium(raw_dir)
        rows = self._parse_csv(csv_path)
        metadata = {
            "collection_mode": "selenium_csv_export",
            "sport": self.sport_config.label,
            "record_count": len(rows),
            "csv_path": str(csv_path),
        }
        return rows, metadata

    def _extract_next_data(self, html: str) -> dict | None:
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script_tag or not script_tag.string:
            return None
        return json.loads(script_tag.string)

    def _collect_via_graphql(
        self,
        session: requests.Session,
        next_data: dict | None,
        raw_dir: Path,
    ) -> tuple[list[PlayerProjection], bool]:
        if not next_data:
            return [], False

        page_props = next_data.get("props", {}).get("pageProps", {})
        sport = page_props.get("sport", {})
        projection_info = page_props.get("projectionInfo", {})

        projection_type = projection_info.get("projectionId")
        slate_id = projection_info.get("selectedSlate")
        if not slate_id:
            slates = projection_info.get("slatesFilter") or []
            if slates:
                slate_id = slates[0].get("value")

        sport_name = sport.get("name")
        position_values = self._projection_positions(projection_info)
        if not all([projection_type, sport_name]) or not position_values:
            return [], False

        graphql_payloads: list[dict] = []
        parsed_rows: list[PlayerProjection] = []
        seen_names: set[str] = set()
        for position_value in position_values:
            projection_input = {
                "type": projection_type,
                "position": position_value,
                "sport": sport_name,
            }
            if slate_id:
                projection_input["slateId"] = str(slate_id)

            payload = {
                "operationName": "GetProjections",
                "query": GET_PROJECTIONS_QUERY,
                "variables": {"input": projection_input},
            }

            response = session.post(GRAPHQL_URL, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            graphql_payload = response.json()
            graphql_payloads.append(
                {
                    "position_value": position_value,
                    "response": graphql_payload,
                }
            )

            rows = graphql_payload.get("data", {}).get("getProjections") or []
            for row in rows:
                player = row.get("player") or {}
                name = clean_name(str(player.get("name", "")).strip())
                if not name or name in seen_names:
                    continue

                salary = parse_float(row.get("salary"))
                projection = parse_float(row.get("fantasy"))
                value = parse_float(row.get("value")) or compute_value(projection, salary)

                parsed_rows.append(
                    PlayerProjection(
                        source="fanduel",
                        name=name,
                        position=self._format_position(player.get("position")),
                        salary=salary,
                        projection=projection,
                        value=value,
                        raw=row,
                    )
                )
                seen_names.add(name)

        write_json(raw_dir / "graphql_response.json", graphql_payloads)

        return parsed_rows, True

    def _projection_positions(self, projection_info: dict) -> list[str]:
        position_filter = projection_info.get("positionFilter") or []
        positions: list[str] = []
        seen: set[str] = set()
        for item in position_filter:
            value = item.get("value")
            if not value or value in seen:
                continue
            positions.append(str(value))
            seen.add(str(value))

        if positions:
            return positions

        selected = projection_info.get("selectedPositionValue")
        return [str(selected)] if selected else []

    def _format_position(self, positions: object) -> str | None:
        if isinstance(positions, list):
            cleaned = [clean_name(str(position)) for position in positions if str(position).strip()]
            return "/".join(cleaned) if cleaned else None
        if positions is None:
            return None
        text = clean_name(str(positions))
        return text or None

    def _try_extract_rows_from_next_data(self, payload: dict | None) -> list[PlayerProjection]:
        if not payload:
            return []

        candidates: list[tuple[int, list[dict]]] = []

        def visit(node: object) -> None:
            if isinstance(node, list):
                if node and all(isinstance(item, dict) for item in node):
                    score = self._score_candidate_list(node)
                    if score >= 6:
                        candidates.append((score, node))
                for item in node:
                    visit(item)
            elif isinstance(node, dict):
                for value in node.values():
                    visit(value)

        visit(payload)

        for _, rows in sorted(candidates, key=lambda item: item[0], reverse=True):
            parsed = self._coerce_rows(rows)
            if parsed:
                return parsed

        return []

    def _score_candidate_list(self, rows: list[dict]) -> int:
        keys = {
            normalize_key(str(key))
            for row in rows[:10]
            for key in row.keys()
        }

        score = 0
        if any("player" in key or "name" in key for key in keys):
            score += 3
        if any("salary" in key for key in keys):
            score += 2
        if any(key in {"fpts", "fantasy", "projection", "projectedpoints"} or "projection" in key for key in keys):
            score += 2
        if any("value" in key for key in keys):
            score += 2
        return score

    def _coerce_rows(self, rows: list[dict]) -> list[PlayerProjection]:
        parsed_rows: list[PlayerProjection] = []
        for row in rows:
            name = self._extract_name(row)
            if not name:
                continue

            salary = self._extract_number(row, ["salary"])
            projection = self._extract_number(row, ["fpts", "fantasy", "projection", "projected"])
            value = self._extract_number(row, ["value"]) or compute_value(projection, salary)
            if projection is None and salary is None:
                continue

            parsed_rows.append(
                PlayerProjection(
                    source="fanduel",
                    name=name,
                    position=None,
                    salary=salary,
                    projection=projection,
                    value=value,
                    raw=row,
                )
            )

        return parsed_rows

    def _extract_name(self, row: dict) -> str | None:
        flattened = self._flatten_dict(row)
        for key, value in flattened.items():
            normalized = normalize_key(key)
            if normalized in {"player", "playername", "name", "fullname"} and isinstance(value, str):
                return clean_name(value)

        first = None
        last = None
        for key, value in flattened.items():
            normalized = normalize_key(key)
            if normalized.endswith("firstname") and isinstance(value, str):
                first = value
            if normalized.endswith("lastname") and isinstance(value, str):
                last = value

        if first or last:
            return combine_name(first, last)
        return None

    def _extract_number(self, row: dict, hints: Iterable[str]) -> float | None:
        flattened = self._flatten_dict(row)
        hint_set = tuple(hints)
        for key, value in flattened.items():
            normalized = normalize_key(key)
            if any(hint in normalized for hint in hint_set):
                number = parse_float(value)
                if number is not None:
                    return number
        return None

    def _flatten_dict(self, payload: dict, prefix: str = "") -> dict[str, object]:
        flattened: dict[str, object] = {}
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                flattened.update(self._flatten_dict(value, next_prefix))
            else:
                flattened[next_prefix] = value
        return flattened

    def _download_csv_via_selenium(self, raw_dir: Path) -> Path:
        download_dir = raw_dir / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        before = {path.name for path in download_dir.iterdir()}

        driver = build_headless_driver(download_dir, browser=self.browser, headless=self.headless)
        try:
            driver.get(self.sport_config.fanduel_page_url)
            wait = WebDriverWait(driver, self.timeout_seconds)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            self._dismiss_common_banners(driver)
            self._click_csv_button(driver, wait)

            downloaded_file = wait_for_download(download_dir, before, timeout_seconds=45)
            destination = raw_dir / "fanduel_export.csv"
            shutil.copy2(downloaded_file, destination)
            return destination
        finally:
            driver.quit()

    def _dismiss_common_banners(self, driver) -> None:
        labels = ["Accept", "Accept All", "I Accept", "Allow All", "Close"]
        for label in labels:
            xpath = (
                "//button[contains(normalize-space(.), '%s')] | "
                "//a[contains(normalize-space(.), '%s')]"
            ) % (label, label)
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for element in elements[:1]:
                    element.click()
                    return
            except Exception:  # noqa: BLE001
                continue

    def _click_csv_button(self, driver, wait: WebDriverWait) -> None:
        selectors = [
            "//button[contains(normalize-space(.), 'Download as CSV')]",
            "//a[contains(normalize-space(.), 'Download as CSV')]",
            "//button[contains(normalize-space(.), 'CSV')]",
            "//a[contains(normalize-space(.), 'CSV')]",
        ]

        last_error: Exception | None = None
        for xpath in selectors:
            try:
                element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                driver.execute_script("arguments[0].click();", element)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        raise RuntimeError("Unable to find or click the FanDuel CSV export control.") from last_error

    def _parse_csv(self, csv_path: Path) -> list[PlayerProjection]:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)

        parsed_rows: list[PlayerProjection] = []
        for row in rows:
            name = self._csv_name(row)
            if not name:
                continue

            salary = self._csv_number(row, ["salary"])
            projection = self._csv_number(row, ["fpts", "fantasypoints", "projection", "projectedpoints"])
            value = self._csv_number(row, ["value"]) or compute_value(projection, salary)

            parsed_rows.append(
                PlayerProjection(
                    source="fanduel",
                    name=name,
                    position=None,
                    salary=salary,
                    projection=projection,
                    value=value,
                    raw=row,
                )
            )

        if not parsed_rows:
            raise RuntimeError(
                "FanDuel CSV download completed, but no player rows could be parsed. "
                "The CSV schema may have changed."
            )

        return parsed_rows

    def _csv_name(self, row: dict[str, str]) -> str | None:
        normalized_map = {normalize_key(key): value for key, value in row.items()}
        for key in ("playername", "player", "name", "fullname"):
            value = normalized_map.get(key)
            if value:
                return clean_name(value)

        first = normalized_map.get("firstname")
        last = normalized_map.get("lastname")
        if first or last:
            return combine_name(first, last)
        return None

    def _csv_number(self, row: dict[str, str], hints: Iterable[str]) -> float | None:
        normalized_hints = tuple(hints)
        for key, value in row.items():
            normalized_key = normalize_key(key)
            if any(hint in normalized_key for hint in normalized_hints):
                number = parse_float(value)
                if number is not None:
                    return number
        return None
