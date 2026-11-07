"""The Vue app owns the root path; the old page is served at /legacy."""

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


def test_root_serves_the_vue_app(station: Station) -> None:
    status, content_type, body = _get(station, "/")
    assert status == 200
    assert content_type.startswith("text/html")
    text = body.decode("utf-8")
    assert "BCI Web-Grid" in text
    assert "/assets/" in text


def test_assets_have_correct_mime_types(station: Station) -> None:
    _, _, body = _get(station, "/")
    html = body.decode("utf-8")
    assets = re.findall(r"/assets/([^\"']+)", html)
    assert assets, "index.html must reference its bundle"
    for asset in assets:
        status, content_type, payload = _get(station, f"/assets/{asset}")
        assert status == 200 and payload
        if asset.endswith(".js"):
            assert "javascript" in content_type
        elif asset.endswith(".css"):
            assert content_type.startswith("text/css")


def test_missing_asset_and_traversal_are_404(station: Station) -> None:
    for path in ("/assets/nope.js", "/assets/../dashboard.html"):
        with pytest.raises(urllib.error.HTTPError) as info:
            _get(station, path)
        assert info.value.code == 404


def test_legacy_page_is_kept_as_fallback(station: Station) -> None:
    status, content_type, body = _get(station, "/legacy")
    assert status == 200 and content_type.startswith("text/html")
    assert "rewardDialog" in body.decode("utf-8")


def test_app_path_redirects_to_root(station: Station) -> None:
    request = urllib.request.Request(f"http://127.0.0.1:{station.port}/app/")
    opener = urllib.request.build_opener(NoRedirect)
    with pytest.raises(urllib.error.HTTPError) as info:
        opener.open(request, timeout=5)
    assert info.value.code == 302
    assert info.value.headers["Location"] == "/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
