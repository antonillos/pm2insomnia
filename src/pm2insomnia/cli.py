from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from pm2insomnia.bundle_writer import slugify_api_name, write_versioned_bundle
from pm2insomnia.converter import convert_collection
from pm2insomnia.insomnia_writer import write_insomnia_export
from pm2insomnia.models import Collection, ConversionResult
from pm2insomnia.postman_environment_parser import parse_postman_environments
from pm2insomnia.postman_parser import parse_postman_collection
from pm2insomnia.reporting import build_summary, format_infos, format_warnings

ASCII_ART = r"""
 [p] ==> (i)
"""


class CliError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pm2insomnia",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"{ASCII_ART}\nPostman to Insomnia",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser(
        "convert",
        help="Convert a Postman collection into an Insomnia import",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"{ASCII_ART}\nPostman to Insomnia",
    )
    _add_shared_collection_arguments(convert)
    convert.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Insomnia JSON. Defaults to writing <input>.insomnia.json next to the input file.",
    )
    convert.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where the generated output file should be written when --output is not provided.",
    )
    convert.set_defaults(handler=handle_convert)

    bundle = subparsers.add_parser(
        "bundle",
        help="Generate a versioned export bundle with Insomnia collection output and companion docs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"{ASCII_ART}\nPostman to Insomnia",
    )
    _add_shared_collection_arguments(bundle)
    bundle.add_argument(
        "--output-dir", required=True, type=Path, help="Root directory for the generated bundle"
    )
    bundle.add_argument(
        "--api-version", type=str, default=None, help="API version used in the bundle folder layout"
    )
    bundle.add_argument(
        "--spec",
        type=Path,
        default=None,
        help="Optional OpenAPI or Swagger file to copy into the bundle",
    )
    bundle.set_defaults(handler=handle_bundle)
    return parser


def handle_convert(args: argparse.Namespace) -> int:
    _print_processing_banner()
    _print_step(f"Converting {args.input.name}")
    collection, workspace_name = _load_collection_and_workspace_name(args)
    result = convert_collection(collection, workspace_name=workspace_name)
    output_path = _resolve_output_path(args.input, args.output, args.output_dir)
    _print_step(f"Writing {output_path.name}")
    _print_detail(f"output: {output_path}")
    write_insomnia_export(result, output_path, pretty=args.pretty)
    print(build_summary(result))
    exit_code = _finalize_command(result, strict=args.strict)
    _print_completion("Done" if exit_code == 0 else "Completed with warnings")
    return exit_code


def handle_bundle(args: argparse.Namespace) -> int:
    _print_processing_banner()
    _print_step(f"Bundling {args.input.name}")
    if args.spec is not None:
        _ensure_file_exists(args.spec, "spec")
    collection, workspace_name = _load_collection_and_workspace_name(args)
    result = convert_collection(collection, workspace_name=workspace_name)
    api_version = args.api_version or _detect_version_from_filename(args.input.name)
    if not api_version:
        raise CliError(
            "--api-version is required when it cannot be detected from the input filename"
        )
    bundle_label = _format_bundle_label(workspace_name, api_version)
    api_slug = slugify_api_name(workspace_name, api_version)
    collection_filename = f"{api_slug}.insomnia.json"
    bundled_collection_output = (
        args.output_dir / "collections" / api_slug / api_version / collection_filename
    )
    bundled_docs_dir = args.output_dir / "api-docs" / api_slug / api_version
    bundled_readme_output = bundled_docs_dir / "README.md"
    _print_step(f"Writing bundle {bundle_label}")
    _print_detail(f"collection: {bundled_collection_output}")
    if args.spec is not None:
        _print_detail(f"spec: {bundled_docs_dir / _normalize_spec_output_name(args.spec.name)}")
    _print_detail(f"readme: {bundled_readme_output}")
    write_versioned_bundle(
        result,
        output_dir=args.output_dir,
        api_name=workspace_name,
        api_version=api_version,
        spec_path=args.spec,
        pretty=args.pretty,
    )
    print(build_summary(result))
    exit_code = _finalize_command(result, strict=args.strict)
    _print_completion("Done" if exit_code == 0 else "Completed with warnings")
    return exit_code


def _add_shared_collection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, type=Path, help="Input Postman collection JSON")
    parser.add_argument(
        "--environment",
        action="append",
        type=Path,
        default=[],
        help="Optional Postman environment JSON or ZIP file. Repeat for multiple inputs.",
    )
    parser.add_argument(
        "--workspace-name",
        type=_non_empty_string,
        default=None,
        help="Override the Insomnia workspace name. `bundle` also uses it as the default bundle name.",
    )
    parser.add_argument(
        "--append-version-from-input",
        action="store_true",
        help="Append a detected version from the input filename to the generated workspace name.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail if warnings are generated")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")


def _load_collection_and_workspace_name(args: argparse.Namespace) -> tuple[Collection, str]:
    _ensure_file_exists(args.input, "input collection")
    for environment_path in args.environment:
        _ensure_file_exists(environment_path, "environment")

    collection = parse_postman_collection(args.input)
    for environment_path in args.environment:
        environments, infos = parse_postman_environments(environment_path)
        collection.environments.extend(environments)
        collection.infos.extend(infos)
    workspace_name = args.workspace_name or collection.name
    if args.append_version_from_input:
        workspace_name = _append_detected_version(workspace_name, args.input)
    return collection, workspace_name


def _finalize_command(result: ConversionResult, strict: bool) -> int:
    info_text = format_infos(result)
    if info_text:
        print(info_text)
    warning_text = format_warnings(result)
    if warning_text:
        print(warning_text)
    if strict and result.warnings:
        return 2
    return 0


def _ensure_file_exists(path: Path, label: str) -> None:
    if path.exists() and path.is_file():
        return
    raise CliError(f"{label} file not found: {path}")


def _non_empty_string(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("value must not be empty")
    return normalized


def _print_step(message: str) -> None:
    print(f"{_format_step_marker()} {message}")


def _print_completion(message: str) -> None:
    print(f"{_format_completion_marker()} {message}")


def _print_processing_banner() -> None:
    print(f"Processing {_colorize(ASCII_ART.strip(), '1;36')}...")


def _print_detail(message: str) -> None:
    print(f"    {message}")


def _format_step_marker() -> str:
    return _colorize("==>", "1;33")


def _format_completion_marker() -> str:
    return _colorize("✓", "1;32")


def _format_error_marker() -> str:
    return _colorize("✗", "1;31")


def _colorize(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty() and os.getenv("TERM") not in {None, "", "dumb"}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except CliError as error:
        print(f"{_format_error_marker()} {error}", file=sys.stderr)
        return 1


def _default_output_path(input_path: Path) -> Path:
    name = input_path.name
    if name.endswith(".postman.json"):
        return input_path.with_name(f"{name[:-13]}.insomnia.json")
    return input_path.with_name(f"{input_path.stem}.insomnia.json")


def _resolve_output_path(
    input_path: Path, output_path: Path | None, output_dir: Path | None
) -> Path:
    if output_path is not None:
        return output_path

    generated_name = _default_output_path(input_path).name
    if output_dir is not None:
        return output_dir / generated_name

    return _default_output_path(input_path)


def _format_bundle_label(api_name: str, api_version: str) -> str:
    normalized_name = api_name.strip()
    normalized_version = api_version.strip()
    if normalized_name.endswith(normalized_version):
        return normalized_name
    return f"{normalized_name} {normalized_version}"


def _normalize_spec_output_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".yaml", ".yml", ".json"}:
        return f"openapi{suffix}"
    return filename


def _append_detected_version(workspace_name: str, input_path: Path) -> str:
    detected_version = _detect_version_from_filename(input_path.name)
    if not detected_version or detected_version in workspace_name:
        return workspace_name
    return f"{workspace_name} {detected_version}"


def _detect_version_from_filename(filename: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", filename)
    if not match:
        return None
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
