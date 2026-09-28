"""Take the README screenshot of the map with headless Chromium (Playwright).

Usage: python scripts/screenshot.py <web dir> <output png>
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEW = "index.html#kennzahl=t:gp&zeit=wd_pm&ebene=raster"


def serve(directory: Path) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(web_dir: str, target: str) -> None:
    server = serve(Path(web_dir))
    url = f"http://127.0.0.1:{server.server_address[1]}/{VIEW}"
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_function("window.atlasReady === true", timeout=180_000)
        page.wait_for_timeout(2_000)
        page.screenshot(path=target)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
