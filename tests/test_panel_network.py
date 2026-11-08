"""Panel addressing: loopback by default, LAN URLs when bound to 0.0.0.0."""

from __future__ import annotations

import pytest

from web_grid_paradigm.panel import Station
from web_grid_paradigm.panel.state import is_wildcard, lan_ipv4_addresses


@pytest.mark.parametrize("host", ["0.0.0.0", "", "::", "[::]", " 0.0.0.0 "])
def test_wildcard_hosts_are_detected(host: str) -> None:
    assert is_wildcard(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "192.168.0.20"])
def test_specific_hosts_are_not_wildcards(host: str) -> None:
    assert not is_wildcard(host)


def test_lan_addresses_skip_loopback_and_link_local() -> None:
    for address in lan_ipv4_addresses():
        assert not address.startswith(("127.", "169.254."))
        assert address.count(".") == 3


def test_loopback_station_has_no_remote_url() -> None:
    station = Station("127.0.0.1", 0, open_browser=False)
    try:
        assert station.url == f"http://127.0.0.1:{station.port}/"
        assert station.lan_urls == []
        assert station.is_loopback and not station.is_wildcard
    finally:
        station.close()


def test_wildcard_station_opens_locally_and_lists_lan_urls() -> None:
    station = Station("0.0.0.0", 0, open_browser=False)
    try:
        # The browser on this machine keeps using loopback ...
        assert station.url == f"http://127.0.0.1:{station.port}/"
        assert station.is_wildcard and not station.is_loopback
        # ... while the console lists the addresses another computer can use.
        for url in station.lan_urls:
            assert url.startswith("http://")
            assert url.endswith(f":{station.port}/")
            assert "127.0.0.1" not in url
            assert "169.254." not in url
    finally:
        station.close()
