"""Export the current configuration as a portable ZIP archive.

The archive mirrors the CLI's own layering: one ``--config`` file for the
experiment and startup settings, one device module per ``--device-config``
file, a JSON snapshot for auditing, and a README with the exact command line.
Everything is generated in memory, so an export also works from a browser on
another computer and never writes files on the machine running the panel.
"""

from __future__ import annotations

import io
import json
import platform
import re
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from .. import __version__
from ..core.config import ExperimentConfig, toml_document
from ..core.settings import CONFIG_FILE_FIELDS, DEFAULT_SOURCE, DEVICE_MODULES

CONFIG_DOCUMENT = "config.toml"
SNAPSHOT_DOCUMENT = "config.json"
README_DOCUMENT = "README.md"
SNAPSHOT_SCHEMA = "webgrid.config/1"
ARCHIVE_STEM = "webgrid-config"

# Short description per device module, used in the generated README.
_MODULE_SUMMARY = {
    "velocity_input": "输入设备（demo_speed / joystick_* / lsl_velocity_*）",
    "reward": "奖励硬件（reward*）",
    "lsl_outputs": "LSL 输出（lsl、lsl_stream、lsl_state*）",
}

# Subject labels are already validated, but the archive name is built from a
# string that may come from a file or another front-end: keep it a plain file
# name that cannot escape the download folder.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class ConfigArchive:
    """One downloadable configuration archive."""

    filename: str
    body: bytes
    documents: tuple[str, ...]


def module_document(module: str) -> str:
    """File name of one device module inside the archive."""
    return f"{module}.toml"


def build_config_archive(
    config: ExperimentConfig,
    *,
    sources: Mapping[str, str] | None = None,
    config_files: Mapping[str, str] | None = None,
    exported: datetime | None = None,
) -> ConfigArchive:
    """Serialise ``config`` as a ZIP the CLI can consume directly.

    ``sources`` / ``config_files`` are the panel's provenance maps; they only
    become trailing ``# source: ...`` comments and the JSON snapshot, never
    part of the parsed values.
    """
    exported = exported or datetime.now().astimezone()
    stem = _archive_stem(config.subject, exported)
    notes = _provenance_notes(sources, config_files)
    data = config.to_dict()

    documents: dict[str, bytes] = {}
    documents[CONFIG_DOCUMENT] = config.to_toml(
        role="config", comments=notes
    ).encode("utf-8")
    for module, names in DEVICE_MODULES.items():
        subset = {name: value for name, value in data.items() if name in names}
        documents[module_document(module)] = toml_document(
            subset,
            title=f"# BCI Web-Grid device module ({module})",
            comments=notes,
        ).encode("utf-8")
    documents[SNAPSHOT_DOCUMENT] = _snapshot(
        config, sources, config_files, exported
    ).encode("utf-8")
    documents[README_DOCUMENT] = _readme(config, exported, stem).encode("utf-8")

    order = (
        README_DOCUMENT,
        CONFIG_DOCUMENT,
        *(module_document(module) for module in DEVICE_MODULES),
        SNAPSHOT_DOCUMENT,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for document in order:
            # One top-level folder keeps an extracted archive tidy.
            archive.writestr(f"{stem}/{document}", documents[document])
    return ConfigArchive(
        filename=f"{stem}.zip",
        body=buffer.getvalue(),
        documents=order,
    )


def _archive_stem(subject: str, exported: datetime) -> str:
    slug = _UNSAFE_FILENAME.sub("-", str(subject)).strip(".-_") or "config"
    return f"{ARCHIVE_STEM}-{slug[:48]}-{exported.strftime('%Y%m%d-%H%M%S')}"


def _provenance_notes(
    sources: Mapping[str, str] | None,
    config_files: Mapping[str, str] | None,
) -> dict[str, str]:
    """``name -> "source: webui"``, or ``... (file)`` for module values.

    Code defaults are left unannotated: a comment then marks exactly the
    values that differ from the built-in defaults in a meaningful way.
    """
    notes: dict[str, str] = {}
    for name, source in (sources or {}).items():
        if not source or source == DEFAULT_SOURCE:
            continue
        path = (config_files or {}).get(name)
        notes[name] = f"source: {source} ({path})" if path else f"source: {source}"
    return notes


def _snapshot(
    config: ExperimentConfig,
    sources: Mapping[str, str] | None,
    config_files: Mapping[str, str] | None,
    exported: datetime,
) -> str:
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "exported_utc": exported.astimezone(UTC).isoformat(
            timespec="milliseconds"
        ),
        "webgrid_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "config": config.to_dict(),
        "config_sources": dict(sorted((sources or {}).items())),
        "config_files": dict(sorted((config_files or {}).items())),
        "documents": {
            "config": CONFIG_DOCUMENT,
            "device": [module_document(module) for module in DEVICE_MODULES],
            "snapshot": SNAPSHOT_DOCUMENT,
            "readme": README_DOCUMENT,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _readme(config: ExperimentConfig, exported: datetime, stem: str) -> str:
    local = exported.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    utc = exported.astimezone(UTC).isoformat(timespec="seconds")
    rows = [
        f"| `{CONFIG_DOCUMENT}` | `--config` | 实验设计 + 启动项 | "
        f"{len(CONFIG_FILE_FIELDS)} |",
        *(
            f"| `{module_document(module)}` | `--device-config` | "
            f"{_MODULE_SUMMARY.get(module, module)} | {len(names)} |"
            for module, names in DEVICE_MODULES.items()
        ),
        f"| `{SNAPSHOT_DOCUMENT}` | — | 全量快照：全部字段 + 来源 + 版本 | "
        f"{len(config.to_dict())} |",
    ]
    usage = [
        "uv run webgrid `",
        "  --config config.toml `",
        *(
            f"  --device-config {module_document(module)} `"
            for module in DEVICE_MODULES
        ),
    ]
    usage[-1] = usage[-1].removesuffix(" `")
    return "\n".join(
        [
            "# BCI Web-Grid 配置导出",
            "",
            f"- 归档：`{stem}.zip`",
            f"- 导出时间：{local}（UTC {utc}）",
            "- 来源：Web 控制台的当前参数（页面上的值覆盖启动配置）",
            "",
            "## 文件",
            "",
            "| 文件 | 命令行 | 内容 | 键数 |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
            "## 使用",
            "",
            "```powershell",
            *usage,
            "```",
            "",
            "只带需要的设备文件也可以：设备文件的键彼此不重叠，可以任意组合。",
            "",
            "## 说明",
            "",
            "- 所有 TOML 都是平铺的，键名与 `ExperimentConfig` 字段一一对应，"
            "可直接被 CLI 读取；`config.toml` 只含实验与启动键，"
            "三个设备文件只含设备键。",
            "- 行尾 `# source: ...` 记录该值在导出时的来源：`webui`（本页面改过）、"
            "`device`（来自设备配置文件，括号内是文件名）、`cli`（命令行）、"
            "`config`（`--config` 文件）。没有该注释的行是代码默认值；注释不参与解析。",
            f"- `{SNAPSHOT_DOCUMENT}` 不是 CLI 输入，只用于审计或给其他程序读取。",
            "- 导出只读取页面上的当前参数：不启动实验，"
            "也不在控制台所在机器上写文件。",
            "",
        ]
    )
