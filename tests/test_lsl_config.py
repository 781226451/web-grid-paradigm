"""The bundled liblsl configuration must survive package moves."""

from pathlib import Path

from web_grid_paradigm.recording import lsl

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "web_grid_paradigm"


def test_bundled_lsl_config_is_found() -> None:
    assert lsl._LSL_CFG == PACKAGE_ROOT / "lsl_api.cfg"
    assert lsl._LSL_CFG.is_file()
