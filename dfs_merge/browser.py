from __future__ import annotations

import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService


WINDOWS_BROWSER_PATHS: dict[str, list[Path]] = {
    "edge": [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ],
    "chrome": [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ],
}


def _existing_paths(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path and path.exists()]


def build_headless_driver(download_dir: Path, browser: str = "auto", headless: bool = True) -> webdriver.Remote:
    if browser == "auto":
        candidates = ["edge", "chrome"]
    else:
        candidates = [browser]

    errors: list[str] = []
    for candidate in candidates:
        try:
            return _build_driver_for(candidate, download_dir, headless=headless)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate}: {exc}")

    joined = "; ".join(errors) if errors else "No browser candidates were attempted."
    raise RuntimeError(
        "Unable to start a Selenium browser. "
        "Install Microsoft Edge or Google Chrome, or update the binary path logic. "
        f"Details: {joined}"
    )


def _build_driver_for(browser: str, download_dir: Path, headless: bool) -> webdriver.Remote:
    if browser == "edge":
        options = EdgeOptions()
        for binary_path in _existing_paths(WINDOWS_BROWSER_PATHS["edge"]):
            options.binary_location = str(binary_path)
            break
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1600,1200")
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(download_dir.resolve()),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
        try:
            driver = webdriver.Edge(options=options)
        except Exception:  # noqa: BLE001
            driver = webdriver.Edge(service=EdgeService(_install_driver(browser)), options=options)
    elif browser == "chrome":
        options = ChromeOptions()
        for binary_path in _existing_paths(WINDOWS_BROWSER_PATHS["chrome"]):
            options.binary_location = str(binary_path)
            break
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1600,1200")
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(download_dir.resolve()),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
        try:
            driver = webdriver.Chrome(options=options)
        except Exception:  # noqa: BLE001
            driver = webdriver.Chrome(service=ChromeService(_install_driver(browser)), options=options)
    else:
        raise ValueError(f"Unsupported browser: {browser}")

    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(download_dir.resolve())},
        )
    except WebDriverException:
        pass

    return driver


def _install_driver(browser: str) -> str:
    if browser == "edge":
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        return EdgeChromiumDriverManager().install()
    if browser == "chrome":
        from webdriver_manager.chrome import ChromeDriverManager

        return ChromeDriverManager().install()
    raise ValueError(f"Unsupported browser: {browser}")


def wait_for_download(download_dir: Path, before: set[str], timeout_seconds: int = 45) -> Path:
    deadline = time.time() + timeout_seconds
    partial_suffixes = {".crdownload", ".tmp", ".part"}

    while time.time() < deadline:
        current_files = list(download_dir.iterdir())
        new_files = [path for path in current_files if path.name not in before]
        finished = [
            path
            for path in new_files
            if path.is_file() and path.suffix.lower() not in partial_suffixes
        ]
        if finished:
            finished.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            return finished[0]

        time.sleep(1)

    raise TimeoutError(f"No completed download appeared in {download_dir} within {timeout_seconds} seconds.")
