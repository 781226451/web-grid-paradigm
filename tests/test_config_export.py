"""The panel's configuration export: a ZIP the CLI can consume directly."""

from __future__ import annotations

import io
import json
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from web_grid_paradigm.core.config import ExperimentConfig, read_config_table
from web_grid_paradigm.core.settings import CONFIG_FILE_FIELDS, DEVICE_MODULES
from web_grid_paradigm.panel.export import (
    CONFIG_DOCUMENT,
    README_DOCUMENT,
    SNAPSHOT_DOCUMENT,
    build_config_archive,
    module_document,
)

EXPORTED = datetime(2026, 11, 9, 22, 47, 25, tzinfo=UTC)


def _documents(body: bytes) -> tuple[str, dict[str, bytes]]:
    """Return the archive's top-level folder and its documents by name."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        roots = {name.split("/", 1)[0] for name in names}
        assert len(roots) == 1, "the archive has exactly one top-level folder"
        root = roots.pop()
        assert all(name.startswith(f"{root}/") for name in names)
        return root, {
            name.split("/", 1)[1]: archive.read(name) for name in names
        }


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        subject="sub-07",
        rows=8,
        cols=10,
        blocks=2,
        targets=12,
        input="joystick",
        joystick_port="COM9",
        reward_port="COM7",
        lsl_state=True,
        lsl_state_stream="RigState",
    )


def test_archive_lists_the_cli_modules() -> None:
    archive = build_config_archive(_config(), exported=EXPORTED)
    root, documents = _documents(archive.body)

    assert archive.filename == "webgrid-config-sub-07-20261109-224725.zip"
    assert root == "webgrid-config-sub-07-20261109-224725"
    expected = (
        README_DOCUMENT,
        CONFIG_DOCUMENT,
        *(f"{module}.toml" for module in DEVICE_MODULES),
        SNAPSHOT_DOCUMENT,
    )
    assert archive.documents == expected
    assert set(documents) == set(expected)
    assert documents[CONFIG_DOCUMENT].startswith(
        b"# BCI Web-Grid configuration (config)"
    )


def test_toml_modules_partition_the_configuration() -> None:
    config = _config()
    _, documents = _documents(build_config_archive(config, exported=EXPORTED).body)
    experiment = tomllib.loads(documents[CONFIG_DOCUMENT].decode("utf-8"))
    assert set(experiment) == set(CONFIG_FILE_FIELDS)

    merged = dict(experiment)
    for module, names in DEVICE_MODULES.items():
        document = tomllib.loads(documents[f"{module}.toml"].decode("utf-8"))
        assert set(document) == set(names)
        assert not set(document) & set(merged), f"{module} overlaps another file"
        merged |= document
    assert merged == config.to_dict()


def test_archive_round_trips_through_the_config_loaders(tmp_path: Path) -> None:
    config = _config()
    _, documents = _documents(build_config_archive(config, exported=EXPORTED).body)

    loaded: dict[str, object] = {}
    for name, body in documents.items():
        if name.endswith(".toml"):
            path = tmp_path / name
            path.write_bytes(body)
            loaded.update(read_config_table(path))
    assert loaded == config.to_dict()
    assert ExperimentConfig.from_dict(loaded) == config

    # config.toml alone is a complete, valid --config file; a run that needs
    # device values (input = joystick) additionally loads the module files.
    plain = ExperimentConfig(rows=8, cols=10, blocks=2)
    _, plain_documents = _documents(
        build_config_archive(plain, exported=EXPORTED).body
    )
    path = tmp_path / "plain.toml"
    path.write_bytes(plain_documents[CONFIG_DOCUMENT])
    experiment = ExperimentConfig.from_toml(path)
    assert (experiment.rows, experiment.cols, experiment.blocks) == (8, 10, 2)


def test_archive_is_loaded_by_the_real_cli(tmp_path: Path) -> None:
    """The strongest check: `webgrid` accepts the extracted files as they are."""
    from web_grid_paradigm.app.cli_args import build_parser, load_config

    config = _config()
    _, documents = _documents(build_config_archive(config, exported=EXPORTED).body)
    for name, body in documents.items():
        if name.endswith(".toml"):
            (tmp_path / name).write_bytes(body)
    arguments = ["--config", str(tmp_path / CONFIG_DOCUMENT)]
    for module in DEVICE_MODULES:
        arguments += ["--device-config", str(tmp_path / module_document(module))]

    loaded = load_config(build_parser().parse_args(arguments))
    assert loaded == config


def test_provenance_becomes_a_comment_and_a_snapshot() -> None:
    sources = {
        "rows": "webui",
        "joystick_port": "device",
        "lsl": "config",
        "subject": "default",
    }
    config_files = {"joystick_port": "configs/velocity_input.toml"}
    archive = build_config_archive(
        _config(),
        sources=sources,
        config_files=config_files,
        exported=EXPORTED,
    )
    _, documents = _documents(archive.body)

    experiment = documents[CONFIG_DOCUMENT].decode("utf-8")
    assert "rows = 8  # source: webui" in experiment
    subject_line = next(
        line for line in experiment.splitlines() if line.startswith("subject = ")
    )
    assert subject_line == 'subject = "sub-07"'  # default source: no note
    assert (
        "lsl = false  # source: config"
    ) in documents["lsl_outputs.toml"].decode("utf-8")
    assert (
        'joystick_port = "COM9"  # source: device '
        "(configs/velocity_input.toml)"
    ) in documents["velocity_input.toml"].decode("utf-8")
    # Values that still match the code default stay unannotated.
    assert 'reward_port = "COM7"\n' in documents["reward.toml"].decode("utf-8")

    snapshot = json.loads(documents[SNAPSHOT_DOCUMENT])
    assert snapshot["schema"] == "webgrid.config/1"
    assert snapshot["exported_utc"] == "2026-11-09T22:47:25.000+00:00"
    assert snapshot["config"]["joystick_port"] == "COM9"
    assert snapshot["config_sources"] == sources
    assert snapshot["config_files"] == config_files
    assert snapshot["documents"]["config"] == CONFIG_DOCUMENT
    assert snapshot["documents"]["device"] == [
        f"{module}.toml" for module in DEVICE_MODULES
    ]
    assert snapshot["webgrid_version"]
    assert snapshot["python_version"].startswith("3.")
    assert snapshot["platform"]  # resolved once, at import


def test_readme_names_every_document() -> None:
    body = build_config_archive(_config(), exported=EXPORTED).body
    _, documents = _documents(body)
    readme = documents[README_DOCUMENT].decode("utf-8")

    for name in documents:
        if name != README_DOCUMENT:  # a README need not list itself
            assert f"`{name}`" in readme
    assert "uv run webgrid" in readme
    assert "--device-config velocity_input.toml" in readme
    assert "2026-11-09 22:47:25" in readme
    assert "`# source: ...`" in readme


def test_archive_name_cannot_escape_the_download_folder() -> None:
    archive = build_config_archive(
        ExperimentConfig(subject="../../evil"), exported=EXPORTED
    )
    assert "/" not in archive.filename and "\\" not in archive.filename
    assert not archive.filename.startswith(".")
    assert archive.filename == "webgrid-config-evil-20261109-224725.zip"
    root, documents = _documents(archive.body)
    assert root == archive.filename.removesuffix(".zip")
    assert set(documents) == set(archive.documents)
