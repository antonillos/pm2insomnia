from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from pm2insomnia.insomnia_writer import write_insomnia_export
from pm2insomnia.models import ConversionResult, InfoMessage


@dataclass(slots=True)
class BundlePaths:
    collection_output: Path
    docs_readme_output: Path
    spec_output: Path | None = None


def write_versioned_bundle(
    result: ConversionResult,
    output_dir: Path,
    api_name: str,
    api_version: str,
    spec_path: Path | None = None,
    pretty: bool = False,
) -> BundlePaths:
    api_slug = slugify_api_name(api_name, api_version)
    has_imported_environments = _has_imported_environments(result)
    collection_output = output_dir / "collections" / api_slug / api_version / f"{api_slug}.insomnia.json"
    docs_dir = output_dir / "api-docs" / api_slug / api_version
    docs_readme_output = docs_dir / "README.md"

    spec_output = None
    if spec_path is not None:
        spec_output = docs_dir / _normalized_spec_filename(spec_path)
        spec_output.parent.mkdir(parents=True, exist_ok=True)
        _write_spec_for_bundle(
            result=result,
            source_path=spec_path,
            output_path=spec_output,
            replace_servers_from_environments=has_imported_environments,
        )
        if has_imported_environments:
            result.infos.append(
                InfoMessage(
                    kind="spec_servers_replaced",
                    message=(
                        "Replaced top-level OpenAPI servers in the bundled spec with URLs from imported "
                        "Postman environments so Insomnia uses the same runtime targets in the spec-derived collection."
                    ),
                )
            )

    _attach_bundle_metadata(
        result,
        api_slug=api_slug,
        api_version=api_version,
        spec_path=spec_path,
        has_imported_environments=has_imported_environments,
    )
    write_insomnia_export(result, collection_output, pretty=pretty)

    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_readme_output.write_text(
        _build_bundle_readme(
            api_name=api_name,
            api_slug=api_slug,
            api_version=api_version,
            collection_filename=collection_output.name,
            spec_filename=spec_output.name if spec_output is not None else None,
            has_imported_environments=has_imported_environments,
            path_param_notes=_collect_path_param_notes(result),
        ),
        encoding="utf-8",
    )

    return BundlePaths(
        collection_output=collection_output,
        docs_readme_output=docs_readme_output,
        spec_output=spec_output,
    )


def slugify_api_name(value: str, version: str | None = None) -> str:
    normalized_value = value.strip()
    if version:
        normalized_value = _strip_version_suffix(normalized_value, version)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized_value.lower())
    normalized = normalized.strip("-")
    return normalized or "api"


def _normalized_spec_filename(spec_path: Path) -> str:
    suffix = spec_path.suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        return spec_path.name
    return f"openapi{suffix}"


def _write_spec_for_bundle(
    result: ConversionResult,
    source_path: Path,
    output_path: Path,
    replace_servers_from_environments: bool,
) -> None:
    suffix = source_path.suffix.lower()
    servers = _build_openapi_servers_from_result(result) if replace_servers_from_environments else []

    if suffix == ".json":
        _write_json_spec(source_path, output_path, servers)
        return

    if suffix in {".yaml", ".yml"}:
        _write_yaml_spec(source_path, output_path, servers)
        return

    shutil.copyfile(source_path, output_path)


def _write_json_spec(source_path: Path, output_path: Path, servers: list[dict[str, str]]) -> None:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        _normalize_openapi_info_title(payload)
        if servers:
            payload["servers"] = servers
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_yaml_spec(source_path: Path, output_path: Path, servers: list[dict[str, str]]) -> None:
    lines = _normalize_yaml_info_title(source_path.read_text(encoding="utf-8").splitlines())
    if not servers:
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    filtered_lines: list[str] = []
    skipping = False

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if not skipping and indent == 0 and stripped.startswith("servers:"):
            skipping = True
            continue

        if skipping:
            if indent == 0 and stripped:
                skipping = False
            else:
                continue

        filtered_lines.append(line)

    server_lines = _render_yaml_servers_block(servers)
    inserted = False
    final_lines: list[str] = []
    for line in filtered_lines:
        if not inserted and line.startswith("paths:"):
            final_lines.extend(server_lines)
            inserted = True
        final_lines.append(line)

    if not inserted:
        final_lines.extend(server_lines)

    output_path.write_text("\n".join(final_lines) + "\n", encoding="utf-8")


def _normalize_openapi_info_title(payload: dict) -> None:
    info = payload.get("info")
    if not isinstance(info, dict):
        return
    title = info.get("title")
    version = info.get("version")
    if not isinstance(title, str) or not isinstance(version, str):
        return
    normalized_title = _strip_version_suffix(title, version)
    if normalized_title != title:
        info["title"] = normalized_title


def _normalize_yaml_info_title(lines: list[str]) -> list[str]:
    normalized_lines = list(lines)
    in_info = False
    info_indent = 0
    version_value = ""
    title_index: int | None = None
    title_value = ""

    for index, line in enumerate(normalized_lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if not in_info and stripped == "info:":
            in_info = True
            info_indent = indent
            continue

        if in_info and indent <= info_indent and stripped:
            break

        if not in_info:
            continue

        if title_index is None and stripped.startswith("title:"):
            title_index = index
            title_value = stripped.partition(":")[2].strip()
            continue

        if stripped.startswith("version:"):
            version_value = stripped.partition(":")[2].strip()

    if title_index is None or not version_value:
        return normalized_lines

    unquoted_title = _unquote_yaml_scalar(title_value)
    unquoted_version = _unquote_yaml_scalar(version_value)
    normalized_title = _strip_version_suffix(unquoted_title, unquoted_version)
    if normalized_title == unquoted_title:
        return normalized_lines

    normalized_lines[title_index] = re.sub(r"(:\s*).*$", rf"\1{_yaml_quote(normalized_title)}", normalized_lines[title_index], count=1)
    return normalized_lines


def _strip_version_suffix(title: str, version: str) -> str:
    normalized_title = title.strip()
    normalized_version = version.strip().lstrip("vV")
    if not normalized_title or not normalized_version:
        return normalized_title

    version_pattern = re.escape(normalized_version)
    stripped_title = re.sub(rf"(?i)(?:\s+|[-_/])v?{version_pattern}$", "", normalized_title).strip()
    return stripped_title or normalized_title


def _unquote_yaml_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _attach_bundle_metadata(
    result: ConversionResult,
    api_slug: str,
    api_version: str,
    spec_path: Path | None,
    has_imported_environments: bool,
) -> None:
    workspace = next((resource for resource in result.resources if resource.get("_type") == "workspace"), None)
    if workspace is None:
        return

    lines = [
        "Generated by pm2insomnia bundle export.",
        f"API name: {api_slug}",
        f"API version: {api_version}",
    ]
    if has_imported_environments:
        lines.append("Runtime environments: imported Postman environment exports")
    else:
        lines.append("Runtime environments: collection variables only")
    if spec_path is not None:
        lines.append(f"Original spec filename: {spec_path.name}")

    current_description = str(workspace.get("description", "")).strip()
    if current_description:
        lines.insert(0, current_description)
    workspace["description"] = "\n".join(lines)


def _build_bundle_readme(
    api_name: str,
    api_slug: str,
    api_version: str,
    collection_filename: str,
    spec_filename: str | None,
    has_imported_environments: bool,
    path_param_notes: list[tuple[str, str]],
) -> str:
    lines = [
        f"# {api_name}",
        "",
        f"Version: `{api_version}`",
        "",
        "## Files",
        "",
        f"- Requests and environments: `../../../collections/{api_slug}/{api_version}/{collection_filename}`",
    ]
    if spec_filename is not None:
        lines.append(f"- API docs: `{spec_filename}`")
    else:
        lines.append("- API docs: not included in this bundle")

    lines.extend(
        [
            "",
            "## Import order",
            "",
            "1. Import the API docs file as an Insomnia `Design Document` if one is included.",
            "2. Import the Insomnia collection JSON for requests, environments, and examples.",
            "3. Treat both imports as parallel artifacts. Insomnia may auto-generate a spec-based collection when importing the OpenAPI file.",
            "4. Use the exported Insomnia collection JSON as the canonical working collection.",
            "",
            "## Notes",
            "",
            (
                "- Runtime environment values in the Insomnia collection come from imported "
                "Postman environment files."
                if has_imported_environments
                else "- Runtime environment values in the Insomnia collection come from collection variables."
            ),
            (
                "- OpenAPI server entries are treated as documentation hints and may not match the "
                "runtime environments used by the collection."
                if spec_filename is not None
                else "- OpenAPI server entries are not included unless you provide a spec file."
            ),
            (
                "- Insomnia may name spec-derived environments as `OpenAPI env <host>`. "
                "That label is generated by Insomnia and can be renamed manually in `Manage Environments`."
                if spec_filename is not None
                else "- No spec-derived Insomnia environments are created unless you provide a spec file."
            ),
            "- Review environment values before sharing or committing them.",
            "- Do not store real secrets in exported environments.",
            "",
        ]
    )

    if path_param_notes:
        lines.extend(
            [
                "## Path variable notes",
                "",
                "The generated Insomnia collection keeps these request-specific path-variable notes:",
                "",
            ]
        )
        for request_name, note in path_param_notes:
            lines.extend(
                [
                    f"### {request_name}",
                    "",
                    note,
                    "",
                ]
            )

    return "\n".join(lines)


def _has_imported_environments(result: ConversionResult) -> bool:
    environment_count = sum(1 for resource in result.resources if resource.get("_type") == "environment")
    return environment_count > 1


def _build_openapi_servers_from_result(result: ConversionResult) -> list[dict[str, str]]:
    servers: list[dict[str, str]] = []
    for resource in result.resources:
        if resource.get("_type") != "environment":
            continue
        data = resource.get("data", {})
        if not isinstance(data, dict):
            continue
        base_url = data.get("baseUrl")
        if not isinstance(base_url, str) or not base_url.strip():
            continue
        servers.append(
            {
                "url": base_url.strip(),
            }
        )
    return servers


def _render_yaml_servers_block(servers: list[dict[str, str]]) -> list[str]:
    lines = ["servers:"]
    for server in servers:
        lines.append(f"  - url: {_yaml_quote(server['url'])}")
    return lines


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _collect_path_param_notes(result: ConversionResult) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    for resource in result.resources:
        if resource.get("_type") != "request":
            continue
        description = str(resource.get("description", "")).strip()
        if "Path variables:" not in description:
            continue
        _, _, note = description.partition("Path variables:")
        cleaned_note = note.strip()
        if not cleaned_note:
            continue
        notes.append((str(resource.get("name", "Unnamed request")), f"Path variables:\n{cleaned_note}"))
    return notes
