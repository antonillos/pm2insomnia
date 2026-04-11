from __future__ import annotations

from pm2insomnia.models import ConversionResult


def build_summary(result: ConversionResult) -> str:
    request_count = sum(1 for resource in result.resources if resource.get("_type") == "request")
    folder_count = sum(1 for resource in result.resources if resource.get("_type") == "request_group")
    lines = [
        _format_section_header("Summary"),
        f"    workspace: {result.workspace_name}",
        f"    requests: {request_count}",
        f"    folders: {folder_count}",
        f"    warnings: {len(result.warnings)}",
    ]
    return "\n".join(lines)


def format_infos(result: ConversionResult) -> str:
    if not result.infos:
        return ""
    lines = [_format_section_header("Info")]
    for info in result.infos:
        lines.append(f"    - [{info.kind}] {info.message}")
    return "\n".join(lines)


def format_warnings(result: ConversionResult) -> str:
    if not result.warnings:
        return ""
    lines = [_format_section_header("Warnings")]
    for warning in result.warnings:
        lines.append(f"    - [{warning.kind}] {warning.location}: {warning.message}")
    return "\n".join(lines)


def _format_section_header(label: str) -> str:
    marker = "==>"
    return f"\033[1;36m{marker}\033[0m {label}" if _supports_color() else f"{marker} {label}"


def _supports_color() -> bool:
    import os
    import sys

    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty() and os.getenv("TERM") not in {None, "", "dumb"}
