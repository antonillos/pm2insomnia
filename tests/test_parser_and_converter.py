import json
import zipfile
from pathlib import Path

from pm2insomnia.converter import convert_collection
from pm2insomnia.postman_environment_parser import parse_postman_environments
from pm2insomnia.postman_parser import parse_postman_collection

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_and_convert_simple_collection() -> None:
    collection = parse_postman_collection(FIXTURES / "simple_collection.postman.json")

    assert collection.name == "Demo Collection"
    assert len(collection.items) == 1

    result = convert_collection(collection)

    assert result.workspace_name == "Demo Collection"
    assert sum(1 for resource in result.resources if resource["_type"] == "request") == 2
    assert sum(1 for resource in result.resources if resource["_type"] == "request_group") == 1
    create_request = next(
        resource for resource in result.resources if resource.get("name") == "Create user"
    )
    assert create_request["body"]["mimeType"] == "application/json"
    assert create_request["body"]["text"] == '{"name":"Ada"}'


def test_convert_collection_level_bearer_auth() -> None:
    collection = parse_postman_collection(FIXTURES / "bearer_auth_collection.postman.json")

    result = convert_collection(collection)

    request = next(
        resource for resource in result.resources if resource.get("name") == "Create resource"
    )
    assert request["authentication"] == {
        "type": "bearer",
        "token": "{{bearerToken}}",
    }
    assert "unsupported_auth" not in [warning.kind for warning in result.warnings]


def test_convert_path_params_and_query_without_duplication() -> None:
    collection = parse_postman_collection(FIXTURES / "path_params_collection.postman.json")

    result = convert_collection(collection)

    request = next(resource for resource in result.resources if resource["_type"] == "request")
    assert request["url"] == "http://localhost:8080/api/items/:id"
    assert request["parameters"] == [
        {"name": "expand", "value": "details", "disabled": False},
        {"name": "version", "value": "1", "disabled": False},
    ]
    assert request["pathParameters"] == [
        {"name": "id", "value": "123", "description": "", "disabled": False},
    ]


def test_preserve_path_param_metadata_in_request_export() -> None:
    collection = parse_postman_collection(FIXTURES / "path_param_metadata_collection.postman.json")

    result = convert_collection(collection)

    request = next(resource for resource in result.resources if resource["_type"] == "request")
    assert request["url"] == "https://api.example.com/orders/:orderId/lines/:lineId"
    assert request["pathParameters"] == [
        {
            "name": "orderId",
            "value": "order-123",
            "description": "Customer-facing order identifier.",
            "disabled": False,
        },
        {
            "name": "lineId",
            "value": "line-9",
            "description": "Optional line selector used in mocks.",
            "disabled": True,
        },
    ]
    assert "Path variables:" in request["description"]
    assert "`orderId`:" in request["description"]
    assert "Customer-facing order identifier." in request["description"]
    assert "`lineId` (disabled):" in request["description"]
    assert "Optional line selector used in mocks." in request["description"]


def test_improve_response_export_fallback_name_and_mime_type() -> None:
    collection = parse_postman_collection(FIXTURES / "response_quality_collection.postman.json")

    result = convert_collection(collection)

    response = next(resource for resource in result.resources if resource["_type"] == "response")
    assert response["name"] == "Response 201 Created"
    assert response["mimeType"] == "application/json"
    assert response["contentType"] == "application/json"


def test_collect_warnings_for_unsupported_features() -> None:
    collection = parse_postman_collection(FIXTURES / "warnings_collection.postman.json")

    assert collection.variables == {"baseUrl": "https://api.example.com"}

    result = convert_collection(collection)

    assert len(result.warnings) == 2
    responses = [resource for resource in result.resources if resource["_type"] == "response"]
    assert len(responses) == 1
    assert responses[0]["name"] == "sample"
    request = next(resource for resource in result.resources if resource["_type"] == "request")
    assert request["authentication"] == {"type": "bearer", "token": ""}
    environment = next(
        resource for resource in result.resources if resource["_type"] == "environment"
    )
    assert environment["data"] == {"baseUrl": "https://api.example.com"}
    warning_kinds = sorted(warning.kind for warning in result.warnings)
    assert warning_kinds == [
        "unsupported_body",
        "unsupported_event",
    ]


def test_preserve_collection_folder_and_request_descriptions() -> None:
    collection = parse_postman_collection(FIXTURES / "descriptions_collection.postman.json")

    assert collection.description == "Collection level overview."

    folder = collection.items[0]
    assert folder.description == "Folder guidance for this section."

    request_item = folder.items[0]
    assert request_item.description == "Request details for Insomnia users."

    result = convert_collection(collection)

    workspace = next(resource for resource in result.resources if resource["_type"] == "workspace")
    request_group = next(
        resource for resource in result.resources if resource["_type"] == "request_group"
    )
    request = next(resource for resource in result.resources if resource["_type"] == "request")

    assert workspace["description"] == "Collection level overview."
    assert request_group["description"] == "Folder guidance for this section."
    assert request["description"] == "Request details for Insomnia users."


def test_parse_environment_zip_and_export_sub_environments(tmp_path: Path) -> None:
    collection = parse_postman_collection(FIXTURES / "simple_collection.postman.json")
    environment_zip = tmp_path / "environments.zip"
    payloads = {
        "sample.env.pre.dev.json": {
            "name": "sample.env.pre.dev",
            "values": [{"key": "baseUrl", "value": "https://pre-dev.example.com", "enabled": True}],
        },
        "sample.env.pre.pro.json": {
            "name": "sample.env.pre.pro",
            "values": [{"key": "baseUrl", "value": "https://pre-pro.example.com", "enabled": True}],
        },
        "sample.env.pro.cp.json": {
            "name": "sample.env.pro.cp",
            "values": [{"key": "baseUrl", "value": "https://pro-cp.example.com", "enabled": True}],
        },
        "sample.env.pro.store.json": {
            "name": "sample.env.pro.store",
            "values": [
                {"key": "baseUrl", "value": "https://pro-store.example.com", "enabled": True}
            ],
        },
        "sample.env.lab.local.json": {
            "name": "sample.env.lab.local",
            "values": [
                {"key": "baseUrl", "value": "https://lab-local.example.com", "enabled": True}
            ],
        },
    }
    with zipfile.ZipFile(environment_zip, "w") as archive:
        for filename, payload in payloads.items():
            archive.writestr(filename, json.dumps(payload))

    environments, infos = parse_postman_environments(environment_zip)
    collection.environments.extend(environments)
    collection.infos.extend(infos)

    result = convert_collection(collection)

    environments = [resource for resource in result.resources if resource["_type"] == "environment"]
    assert len(environments) == 6
    sub_environments = [
        resource for resource in environments if resource["name"] != "Base Environment"
    ]
    assert len(sub_environments) == 5
    assert {environment["name"] for environment in sub_environments} == {
        "pre.dev",
        "pre.pro",
        "pro.cp",
        "pro.store",
        "lab.local",
    }
    assert all(
        not environment["name"].startswith("sample.env.") for environment in sub_environments
    )
    assert sub_environments[0]["data"]["baseUrl"].startswith("https://")
    assert len(result.infos) == 1
    assert result.infos[0].kind == "normalized_environment_names"
