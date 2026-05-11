from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import time
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parent


def get_requires_for_build_wheel(config_settings: object | None = None) -> list[str]:
    return []


def get_requires_for_build_editable(config_settings: object | None = None) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: object | None = None,
) -> str:
    dist_info = dist_info_name()
    target = Path(metadata_directory) / dist_info
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_text(metadata_text(), encoding="utf-8")
    (target / "WHEEL").write_text(wheel_text(), encoding="utf-8")
    (target / "entry_points.txt").write_text(entry_points_text(), encoding="utf-8")
    (target / "RECORD").write_text("", encoding="utf-8")
    return dist_info


def prepare_metadata_for_build_editable(
    metadata_directory: str,
    config_settings: object | None = None,
) -> str:
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(
    wheel_directory: str,
    config_settings: object | None = None,
    metadata_directory: str | None = None,
) -> str:
    return write_wheel(Path(wheel_directory), editable=False)


def build_editable(
    wheel_directory: str,
    config_settings: object | None = None,
    metadata_directory: str | None = None,
) -> str:
    return write_wheel(Path(wheel_directory), editable=True)


def write_wheel(wheel_directory: Path, editable: bool) -> str:
    wheel_directory.mkdir(parents=True, exist_ok=True)
    project = project_metadata()
    wheel_name = f"{normalise(project['name'])}-{project['version']}-py3-none-any.whl"
    wheel_path = wheel_directory / wheel_name
    dist_info = dist_info_name(project)
    written: list[tuple[str, bytes]] = []

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if editable:
            add_bytes(archive, written, "open_gate_editable.pth", str(ROOT).replace("\\", "/").encode("utf-8") + b"\n")
        else:
            for path in sorted((ROOT / "open_gate").rglob("*.py")):
                add_file(archive, written, path, path.relative_to(ROOT).as_posix())
        add_bytes(archive, written, f"{dist_info}/METADATA", metadata_text(project).encode("utf-8"))
        add_bytes(archive, written, f"{dist_info}/WHEEL", wheel_text().encode("utf-8"))
        add_bytes(archive, written, f"{dist_info}/entry_points.txt", entry_points_text(project).encode("utf-8"))
        record_name = f"{dist_info}/RECORD"
        record = record_text([*written, (record_name, b"")])
        archive.writestr(record_name, record)
    return wheel_name


def add_file(archive: zipfile.ZipFile, written: list[tuple[str, bytes]], path: Path, name: str) -> None:
    data = path.read_bytes()
    info = zipfile.ZipInfo(name, date_time=time.gmtime(path.stat().st_mtime)[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)
    written.append((name, data))


def add_bytes(archive: zipfile.ZipFile, written: list[tuple[str, bytes]], name: str, data: bytes) -> None:
    archive.writestr(name, data)
    written.append((name, data))


def record_text(entries: list[tuple[str, bytes]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, data in entries:
        if data:
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            writer.writerow([name, f"sha256={digest}", str(len(data))])
        else:
            writer.writerow([name, "", ""])
    return output.getvalue()


def project_metadata() -> dict[str, str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    return {
        "name": project["name"],
        "version": project["version"],
        "description": project.get("description", ""),
        "requires_python": project.get("requires-python", ">=3.11"),
    }


def metadata_text(project: dict[str, str] | None = None) -> str:
    project = project or project_metadata()
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {project['name']}\n"
        f"Version: {project['version']}\n"
        f"Summary: {project['description']}\n"
        f"Requires-Python: {project['requires_python']}\n"
    )


def wheel_text() -> str:
    return "Wheel-Version: 1.0\nGenerator: open_gate_build\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def entry_points_text(project: dict[str, str] | None = None) -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"].get("scripts", {})
    lines = ["[console_scripts]"]
    lines.extend(f"{name} = {target}" for name, target in sorted(scripts.items()))
    return "\n".join(lines) + "\n"


def dist_info_name(project: dict[str, str] | None = None) -> str:
    project = project or project_metadata()
    return f"{normalise(project['name'])}-{project['version']}.dist-info"


def normalise(value: str) -> str:
    return value.replace("-", "_").replace(".", "_")
