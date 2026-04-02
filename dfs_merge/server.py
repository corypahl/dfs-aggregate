from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dfs_merge.pipeline import run_pipeline
from dfs_merge.sports import get_sport_config


@dataclass
class AggregateApp:
    output_dir: Path
    browser: str = "auto"
    headless: bool = True
    sport: str = "nba"
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def refresh(self, sport: str | None = None) -> dict[str, Any]:
        with self._lock:
            if sport is not None:
                self.sport = get_sport_config(sport).key
            return run_pipeline(
                output_dir=self.output_dir,
                browser=self.browser,
                headless=self.headless,
                sport=self.sport,
            )

    def load_summary(self) -> dict[str, Any]:
        summary_path = self.output_dir / "run_summary.json"
        if not summary_path.exists():
            return self.refresh(self.sport)
        return json.loads(summary_path.read_text(encoding="utf-8"))

    def ensure_started(self) -> dict[str, Any]:
        aggregate_html_path = self.output_dir / "aggregate.html"
        if not aggregate_html_path.exists():
            return self.refresh(self.sport)
        summary = self.load_summary()
        if summary.get("sport") != self.sport:
            return self.refresh(self.sport)
        return summary


class AggregateHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], app: AggregateApp) -> None:
        super().__init__(server_address, AggregateRequestHandler)
        self.app = app


class AggregateRequestHandler(BaseHTTPRequestHandler):
    server: AggregateHTTPServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/aggregate", "/aggregate.html"}:
            self._serve_file(self.server.app.output_dir / "aggregate.html", "text/html; charset=utf-8")
            return
        if path == "/aggregate.csv":
            self._serve_file(self.server.app.output_dir / "aggregate.csv", "text/csv; charset=utf-8")
            return
        if path == "/name_match_report.json":
            self._serve_file(self.server.app.output_dir / "name_match_report.json", "application/json; charset=utf-8")
            return
        if path == "/name_match_report.txt":
            self._serve_file(self.server.app.output_dir / "name_match_report.txt", "text/plain; charset=utf-8")
            return
        if path == "/run_summary.json":
            self._serve_file(self.server.app.output_dir / "run_summary.json", "application/json; charset=utf-8")
            return
        if path == "/summary":
            self._send_json(self.server.app.load_summary())
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/refresh":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            payload = self._read_json_body()
            requested_sport = payload.get("sport") if isinstance(payload, dict) else None
            summary = self.server.app.refresh(requested_sport)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(summary)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))


def serve_aggregate(
    *,
    output_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    browser: str = "auto",
    headless: bool = True,
    sport: str = "nba",
) -> int:
    app = AggregateApp(output_dir=output_dir, browser=browser, headless=headless, sport=get_sport_config(sport).key)
    app.ensure_started()
    server = AggregateHTTPServer((host, port), app)
    try:
        print(f"Serving DFS Aggregate at http://{host}:{port}/")
        print("Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
