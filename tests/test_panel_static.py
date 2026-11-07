"""The built Vue app is served under /app/ by the Python control panel."""

from __future__ import annotations

import re
import urllib.error
import urllib.request

import pytest

from web_grid_paradigm.config import ExperimentConfig
from web_grid_paradigm.panel import Station


@pytest.fixture
def station():
    board = Station("127.0.0.1", 0, base_config=ExperimentConfig(), open_browser=False)
    yield board
    board.close()


def _get(station: Station, path: str) -> tuple[int, str, bytes]:
    url = f"http://127.0.0.1:{station.port}{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], response.read()


def test_app_index_is_served(station: Station) -> None:
    status, content_type, body = _get(station, "/app/")
    assert status == 200
    assert content_type.startswith("text/html")
    text = body.decode("utf-8")
    assert "BCI Web-Grid" in text
    assert "/app/assets/" in text


def test_app_assets_have_correct_mime_types(station: Station) -> None:
    _, _, body = _get(station, "/app/")
    html = body.decode("utf-8")
    assets = re.findall(r"/app/(assets/[^\"']+)", html)
    assert assets, "index.html must reference its bundle"
    for asset in assets:
        status, content_type, payload = _get(station, f"/app/{asset}")
        assert status == 200 and payload
        if asset.endswith(".js"):
            assert "javascript" in content_type
        elif asset.endswith(".css"):
            assert content_type.startswith("text/css")


def test_missing_asset_and_traversal_are_404(station: Station) -> None:
    for path in ("/app/assets/nope.js", "/app/../dashboard.html"):
        with pytest.raises(urllib.error.HTTPError) as info:
            _get(station, path)
        assert info.value.code == 404


def test_legacy_page_is_still_the_default(station: Station) -> None:
    """The hand-written panel stays at / until the rewrite reaches parity."""
    status, content_type, body = _get(station, "/")
    assert status == 200 and content_type.startswith("text/html")
    assert "rewardDialog" in body.decode("utf-8")
