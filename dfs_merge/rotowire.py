from __future__ import annotations

from pathlib import Path

import requests

from dfs_merge.models import PlayerProjection
from dfs_merge.sports import get_sport_config
from dfs_merge.utils import DEFAULT_HEADERS, clean_name, combine_name, compute_value, ensure_directory, write_json, write_text


SITE_NAME = "FanDuel"
SITE_ID = 2


class RotoWireCollector:
    def __init__(self, timeout_seconds: int = 30, sport: str = "nba") -> None:
        self.timeout_seconds = timeout_seconds
        self.sport_config = get_sport_config(sport)

    def collect(self, raw_dir: Path) -> tuple[list[PlayerProjection], dict]:
        slate_collections, metadata = self.collect_all_slates(raw_dir)
        selected_slate_id = (metadata.get("selected_slate") or {}).get("slateID")
        if selected_slate_id is not None:
            for slate_collection in slate_collections:
                slate = slate_collection.get("slate") or {}
                if slate.get("slateID") == selected_slate_id:
                    return slate_collection["records"], metadata
        if slate_collections:
            return slate_collections[0]["records"], metadata
        return [], metadata

    def collect_all_slates(self, raw_dir: Path) -> tuple[list[dict], dict]:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)

        page_response = session.get(self.page_url, timeout=self.timeout_seconds)
        page_response.raise_for_status()
        write_text(raw_dir / "page.html", page_response.text)

        slate_response = session.get(
            self.slate_list_url,
            params={"siteID": SITE_ID},
            timeout=self.timeout_seconds,
        )
        slate_response.raise_for_status()
        slate_payload = slate_response.json()
        write_json(raw_dir / "slates.json", slate_payload)

        slate_candidates = self._ordered_slates(slate_payload)
        fetch_attempts: list[dict] = []
        slate_collections: list[dict] = []
        selected_slate: dict | None = None
        slates_raw_dir = ensure_directory(raw_dir / "slates")

        for index, slate in enumerate(slate_candidates):
            players_payload: list[dict] = []
            max_attempts = 2 if index == 0 else 1
            for attempt_number in range(1, max_attempts + 1):
                players_response = session.get(
                    self.players_url,
                    params={"slateID": slate["slateID"]},
                    timeout=self.timeout_seconds,
                )
                players_response.raise_for_status()
                candidate_players = players_response.json()
                fetch_attempts.append(
                    {
                        "slateID": slate["slateID"],
                        "slateName": slate.get("slateName"),
                        "contestType": slate.get("contestType"),
                        "attempt": attempt_number,
                        "player_count": len(candidate_players),
                    }
                )
                players_payload = candidate_players
                if candidate_players:
                    break

            slate_raw_dir = ensure_directory(slates_raw_dir / str(slate["slateID"]))
            write_json(slate_raw_dir / "players.json", players_payload)

            records = [self._to_projection(player) for player in players_payload]
            slate_collections.append(
                {
                    "slate": slate,
                    "records": records,
                    "record_count": len(records),
                }
            )
            if selected_slate is None and records:
                selected_slate = slate

        write_json(raw_dir / "player_fetch_attempts.json", fetch_attempts)
        write_json(
            raw_dir / "players_by_slate.json",
            [
                {
                    "slate": slate_collection["slate"],
                    "record_count": slate_collection["record_count"],
                }
                for slate_collection in slate_collections
            ],
        )
        metadata = {
            "site": SITE_NAME,
            "site_id": SITE_ID,
            "sport": self.sport_config.label,
            "selected_slate": selected_slate,
            "available_slates": slate_candidates,
            "player_fetch_attempts": fetch_attempts,
            "record_count": next(
                (
                    slate_collection["record_count"]
                    for slate_collection in slate_collections
                    if (slate_collection.get("slate") or {}).get("slateID")
                    == (selected_slate or {}).get("slateID")
                ),
                0,
            ),
        }
        return slate_collections, metadata

    def _ordered_slates(self, slate_payload: dict) -> list[dict]:
        slates = slate_payload.get("slates") or []
        if not slates:
            return []

        return sorted(
            slates,
            key=lambda slate: (
                not bool(slate.get("defaultSlate")),
                slate.get("contestType") != "Full Roster",
                slate.get("startDate", ""),
                slate.get("slateID", 0),
            ),
        )

    def _to_projection(self, player: dict) -> PlayerProjection:
        name = combine_name(player.get("firstName"), player.get("lastName"))
        position = self._format_position(player.get("pos"))
        salary = float(player["salary"]) if player.get("salary") is not None else None
        projection = float(player["pts"]) if player.get("pts") is not None else None
        value = compute_value(projection, salary)

        cleaned_player = dict(player)
        cleaned_player["firstName"] = clean_name(str(player.get("firstName", "")))
        cleaned_player["lastName"] = clean_name(str(player.get("lastName", "")))

        return PlayerProjection(
            source="rotowire",
            name=name,
            position=position,
            salary=salary,
            projection=projection,
            value=value,
            raw=cleaned_player,
        )

    def _format_position(self, positions: object) -> str | None:
        if isinstance(positions, list):
            cleaned = [clean_name(str(position)) for position in positions if str(position).strip()]
            return "/".join(cleaned) if cleaned else None
        if positions is None:
            return None
        text = clean_name(str(positions))
        return text or None

    @property
    def page_url(self) -> str:
        return f"https://www.rotowire.com/daily/{self.sport_config.rotowire_slug}/optimizer.php?site=FanDuel"

    @property
    def slate_list_url(self) -> str:
        return f"https://www.rotowire.com/daily/{self.sport_config.rotowire_slug}/api/slate-list.php"

    @property
    def players_url(self) -> str:
        return f"https://www.rotowire.com/daily/{self.sport_config.rotowire_slug}/api/players.php"
