import json
import subprocess
import sys
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pm2insomnia.cli", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={"PYTHONPATH": str(ROOT / "src")},
    )


def build_environment_zip(path: Path) -> Path:
    payloads = {
        "technical-design.env.pre.dev.json": {
            "name": "technical-design.env.pre.dev",
            "values": [{"key": "baseUrl", "value": "https://pre-dev.example.com", "enabled": True}],
        },
        "technical-design.env.pre.pro.json": {
            "name": "technical-design.env.pre.pro",
            "values": [{"key": "baseUrl", "value": "https://pre-pro.example.com", "enabled": True}],
        },
        "technical-design.env.pro.cp.json": {
            "name": "technical-design.env.pro.cp",
            "values": [{"key": "baseUrl", "value": "https://pro-cp.example.com", "enabled": True}],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        for filename, payload in payloads.items():
            archive.writestr(filename, json.dumps(payload))
    return path


def build_environment_zip_with_traversal_entry(path: Path) -> Path:
    payload = {
        "name": "safe-environment",
        "values": [{"key": "baseUrl", "value": "https://example.com", "enabled": True}],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../../etc/passwd.json", json.dumps(payload))
        archive.writestr("safe-environment.json", json.dumps(payload))
    return path


def test_cli_convert_pretty_and_workspace_name(tmp_path: Path) -> None:
    output = tmp_path / "insomnia.json"

    result = run_cli(
        "convert",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output",
        str(output),
        "--workspace-name",
        "Custom Workspace",
        "--pretty",
    )

    assert result.returncode == 0
    assert "Processing [p] ==> (i)..." in result.stdout
    assert "==> Converting simple_collection.postman.json" in result.stdout
    assert "==> Writing insomnia.json" in result.stdout
    assert "==> Summary" in result.stdout
    assert "✓ Done" in result.stdout
    assert f"    output: {output}" in result.stdout
    assert "    workspace: Custom Workspace" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    workspace = next(resource for resource in payload["resources"] if resource["_type"] == "workspace")
    assert workspace["name"] == "Custom Workspace"
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_cli_help_displays_ascii_art_icon() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "Postman to Insomnia" in result.stdout
    assert " [p] ==> (i)" in result.stdout


def test_cli_convert_help_mentions_default_output_location() -> None:
    result = run_cli("convert", "--help")

    assert result.returncode == 0
    assert "Defaults to writing" in result.stdout
    assert "<input>.insomnia.json next to the input file." in result.stdout


def test_cli_generates_default_output_path_for_postman_input(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.postman.json"
    input_path.write_text((FIXTURES / "simple_collection.postman.json").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_cli(
        "convert",
        "--input",
        str(input_path),
    )

    expected_output = tmp_path / "sample.insomnia.json"
    assert result.returncode == 0
    assert f"    output: {expected_output}" in result.stdout
    assert expected_output.exists()


def test_cli_generates_output_inside_output_dir(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.postman.json"
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    input_path.write_text((FIXTURES / "simple_collection.postman.json").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_cli(
        "convert",
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )

    expected_output = output_dir / "sample.insomnia.json"
    assert result.returncode == 0
    assert f"    output: {expected_output}" in result.stdout
    assert expected_output.exists()


def test_cli_appends_version_from_input_filename(tmp_path: Path) -> None:
    input_path = tmp_path / "sample-api-1.9.1.postman.json"
    output_path = tmp_path / "insomnia.json"
    input_path.write_text((FIXTURES / "simple_collection.postman.json").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_cli(
        "convert",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--append-version-from-input",
    )

    assert result.returncode == 0
    assert "    workspace: Demo Collection 1.9.1" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    workspace = next(resource for resource in payload["resources"] if resource["_type"] == "workspace")
    assert workspace["name"] == "Demo Collection 1.9.1"


def test_cli_strict_fails_when_warnings_exist(tmp_path: Path) -> None:
    output = tmp_path / "insomnia.json"

    result = run_cli(
        "convert",
        "--input",
        str(FIXTURES / "warnings_collection.postman.json"),
        "--output",
        str(output),
        "--strict",
    )

    assert result.returncode == 2
    assert "==> Warnings" in result.stdout


def test_cli_accepts_environment_zip(tmp_path: Path) -> None:
    output = tmp_path / "insomnia.json"
    environment_zip = build_environment_zip(tmp_path / "environments.zip")

    result = run_cli(
        "convert",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--environment",
        str(environment_zip),
        "--output",
        str(output),
    )

    assert result.returncode == 0
    assert "==> Info" in result.stdout
    assert "normalized_environment_names" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    environments = [resource for resource in payload["resources"] if resource["_type"] == "environment"]
    assert len(environments) == 4
    sub_environments = [resource for resource in environments if resource["name"] != "Base Environment"]
    assert all(not environment["name"].startswith("technical-design.env.") for environment in sub_environments)


def test_cli_skips_environment_zip_entries_with_parent_path_segments(tmp_path: Path) -> None:
    output = tmp_path / "insomnia.json"
    environment_zip = build_environment_zip_with_traversal_entry(tmp_path / "environments.zip")

    result = run_cli(
        "convert",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--environment",
        str(environment_zip),
        "--output",
        str(output),
    )

    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    environments = [resource for resource in payload["resources"] if resource["_type"] == "environment"]
    imported_environments = [resource for resource in environments if resource["name"] != "Base Environment"]
    assert len(imported_environments) == 1
    assert imported_environments[0]["name"] == "safe-environment"


def test_cli_bundle_generates_versioned_outputs_and_bundle_readme(tmp_path: Path) -> None:
    spec_path = tmp_path / "payments-service.yaml"
    spec_path.write_text("openapi: 3.0.0\ninfo:\n  title: Payments Service 1.9.1\n  version: 1.9.1\n", encoding="utf-8")

    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "Payments Service",
        "--api-version",
        "1.9.1",
        "--spec",
        str(spec_path),
        "--pretty",
    )

    collection_output = tmp_path / "bundle" / "collections" / "payments-service" / "1.9.1" / "payments-service.insomnia.json"
    spec_output = tmp_path / "bundle" / "api-docs" / "payments-service" / "1.9.1" / "openapi.yaml"
    readme_output = tmp_path / "bundle" / "api-docs" / "payments-service" / "1.9.1" / "README.md"

    assert result.returncode == 0
    assert "Processing [p] ==> (i)..." in result.stdout
    assert "==> Bundling simple_collection.postman.json" in result.stdout
    assert "==> Writing bundle Payments Service 1.9.1" in result.stdout
    assert f"    collection: {collection_output}" in result.stdout
    assert f"    spec: {spec_output}" in result.stdout
    assert f"    readme: {readme_output}" in result.stdout
    assert "✓ Done" in result.stdout
    assert collection_output.exists()
    assert spec_output.exists()
    assert readme_output.exists()
    spec_text = spec_output.read_text(encoding="utf-8")
    assert 'title: "Payments Service"' in spec_text
    assert "Payments Service 1.9.1" not in spec_text

    payload = json.loads(collection_output.read_text(encoding="utf-8"))
    workspace = next(resource for resource in payload["resources"] if resource["_type"] == "workspace")
    assert "API name: payments-service" in workspace["description"]
    assert "API version: 1.9.1" in workspace["description"]
    assert "Original spec filename: payments-service.yaml" in workspace["description"]

    readme_text = readme_output.read_text(encoding="utf-8")
    assert "Import the API docs file as an Insomnia `Design Document`" in readme_text
    assert "../../../collections/payments-service/1.9.1/payments-service.insomnia.json" in readme_text
    assert "Runtime environment values in the Insomnia collection come from collection variables." in readme_text
    assert "OpenAPI server entries are treated as documentation hints" in readme_text
    assert "Insomnia may auto-generate a spec-based collection" in readme_text
    assert "Use the exported Insomnia collection JSON as the canonical working collection." in readme_text
    assert "OpenAPI env <host>" in readme_text


def test_cli_bundle_marks_imported_environments_as_runtime_source(tmp_path: Path) -> None:
    spec_path = tmp_path / "payments-service.yaml"
    spec_path.write_text(
        "openapi: 3.0.0\ninfo:\n  title: Payments Service\n  version: 1.9.1\nservers:\n  - url: https://docs.example.com\n",
        encoding="utf-8",
    )
    environment_zip = build_environment_zip(tmp_path / "environments.zip")

    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--environment",
        str(environment_zip),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "Payments Service",
        "--api-version",
        "1.9.1",
        "--spec",
        str(spec_path),
    )

    collection_output = tmp_path / "bundle" / "collections" / "payments-service" / "1.9.1" / "payments-service.insomnia.json"
    readme_output = tmp_path / "bundle" / "api-docs" / "payments-service" / "1.9.1" / "README.md"
    bundled_spec_output = tmp_path / "bundle" / "api-docs" / "payments-service" / "1.9.1" / "openapi.yaml"

    assert result.returncode == 0
    assert "spec_servers_replaced" in result.stdout
    payload = json.loads(collection_output.read_text(encoding="utf-8"))
    workspace = next(resource for resource in payload["resources"] if resource["_type"] == "workspace")
    assert "Runtime environments: imported Postman environment exports" in workspace["description"]

    environments = [resource for resource in payload["resources"] if resource["_type"] == "environment"]
    assert len(environments) == 4

    readme_text = readme_output.read_text(encoding="utf-8")
    assert "Runtime environment values in the Insomnia collection come from imported Postman environment files." in readme_text
    assert "OpenAPI server entries are treated as documentation hints" in readme_text
    assert "Use the exported Insomnia collection JSON as the canonical working collection." in readme_text
    assert "OpenAPI env <host>" in readme_text

    bundled_spec_text = bundled_spec_output.read_text(encoding="utf-8")
    assert "servers:" in bundled_spec_text
    assert "https://docs.example.com" not in bundled_spec_text
    assert "https://pre-dev.example.com" in bundled_spec_text
    assert "https://pre-pro.example.com" in bundled_spec_text
    assert "https://pro-cp.example.com" in bundled_spec_text
    assert "description:" not in bundled_spec_text


def test_cli_bundle_normalizes_json_spec_title_when_version_is_duplicated(tmp_path: Path) -> None:
    spec_path = tmp_path / "orders-api.json"
    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {
                    "title": "Orders API v2.4.0",
                    "version": "2.4.0",
                },
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "Orders API",
        "--api-version",
        "2.4.0",
        "--spec",
        str(spec_path),
    )

    bundled_spec_output = tmp_path / "bundle" / "api-docs" / "orders-api" / "2.4.0" / "openapi.json"

    assert result.returncode == 0
    bundled_payload = json.loads(bundled_spec_output.read_text(encoding="utf-8"))
    assert bundled_payload["info"]["title"] == "Orders API"
    assert bundled_payload["info"]["version"] == "2.4.0"


def test_cli_bundle_includes_path_param_notes_in_bundle_readme(tmp_path: Path) -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "path_param_metadata_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "Orders API",
        "--api-version",
        "1.0.0",
    )

    readme_output = tmp_path / "bundle" / "api-docs" / "orders-api" / "1.0.0" / "README.md"

    assert result.returncode == 0
    readme_text = readme_output.read_text(encoding="utf-8")
    assert "## Path variable notes" in readme_text
    assert "### Get order line" in readme_text
    assert "Path variables:" in readme_text
    assert "`orderId`:" in readme_text
    assert "Customer-facing order identifier." in readme_text
    assert "`lineId` (disabled):" in readme_text


def test_cli_bundle_keeps_path_param_metadata_inside_collection_json(tmp_path: Path) -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "path_param_metadata_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "Orders API",
        "--api-version",
        "1.0.0",
    )

    collection_output = tmp_path / "bundle" / "collections" / "orders-api" / "1.0.0" / "orders-api.insomnia.json"

    assert result.returncode == 0
    payload = json.loads(collection_output.read_text(encoding="utf-8"))
    request = next(resource for resource in payload["resources"] if resource.get("_type") == "request")
    assert request["pathParameters"] == [
        {"name": "orderId", "value": "order-123", "description": "Customer-facing order identifier.", "disabled": False},
        {"name": "lineId", "value": "line-9", "description": "Optional line selector used in mocks.", "disabled": True},
    ]


def test_cli_bundle_detects_api_version_from_input_filename(tmp_path: Path) -> None:
    input_path = tmp_path / "demo-api-2.4.0.postman.json"
    input_path.write_text((FIXTURES / "simple_collection.postman.json").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_cli(
        "bundle",
        "--input",
        str(input_path),
        "--output-dir",
        str(tmp_path / "bundle"),
    )

    collection_output = tmp_path / "bundle" / "collections" / "demo-collection" / "2.4.0" / "demo-collection.insomnia.json"
    readme_output = tmp_path / "bundle" / "api-docs" / "demo-collection" / "2.4.0" / "README.md"

    assert result.returncode == 0
    assert collection_output.exists()
    assert readme_output.exists()


def test_cli_bundle_does_not_repeat_version_in_progress_message(tmp_path: Path) -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "IOP - PATTERN 3.2.0",
        "--api-version",
        "3.2.0",
    )

    assert result.returncode == 0
    assert "==> Writing bundle IOP - PATTERN 3.2.0\n" in result.stdout
    assert "==> Writing bundle IOP - PATTERN 3.2.0 3.2.0" not in result.stdout


def test_cli_bundle_strips_version_from_generated_slug_paths(tmp_path: Path) -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--workspace-name",
        "technical-design-1.9.1",
        "--api-version",
        "1.9.1",
    )

    collection_output = tmp_path / "bundle" / "collections" / "technical-design" / "1.9.1" / "technical-design.insomnia.json"
    readme_output = tmp_path / "bundle" / "api-docs" / "technical-design" / "1.9.1" / "README.md"

    assert result.returncode == 0
    assert f"    collection: {collection_output}" in result.stdout
    assert f"    readme: {readme_output}" in result.stdout
    assert collection_output.exists()
    assert readme_output.exists()


def test_cli_bundle_reports_missing_spec_file_without_traceback(tmp_path: Path) -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        str(tmp_path / "bundle"),
        "--api-version",
        "1.0.0",
        "--spec",
        str(tmp_path / "missing-openapi.yaml"),
    )

    assert result.returncode != 0
    assert "✗ spec file not found:" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_convert_reports_missing_input_file_without_traceback(tmp_path: Path) -> None:
    result = run_cli(
        "convert",
        "--input",
        str(tmp_path / "missing.postman.json"),
    )

    assert result.returncode != 0
    assert "✗ input collection file not found:" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_bundle_rejects_empty_workspace_name() -> None:
    result = run_cli(
        "bundle",
        "--input",
        str(FIXTURES / "simple_collection.postman.json"),
        "--output-dir",
        ".",
        "--workspace-name",
        "",
        "--api-version",
        "1.0.0",
    )

    assert result.returncode != 0
    assert "argument --workspace-name: value must not be empty" in result.stderr
