from __future__ import annotations

from collections.abc import Iterable
from itertools import count
from typing import Any

from pm2insomnia.models import (
    Body,
    Collection,
    CollectionNode,
    ConversionResult,
    EnvironmentSpec,
    ExampleResponse,
    Folder,
    RequestItem,
    WarningMessage,
)


def convert_collection(
    collection: Collection, workspace_name: str | None = None
) -> ConversionResult:
    workspace_id = _resource_id("wrk", 1)
    environment_id = _resource_id("env", 1)
    sequence = count(start=1)

    resources: list[dict[str, Any]] = [
        {
            "_id": workspace_id,
            "_type": "workspace",
            "name": workspace_name or collection.name,
            "description": collection.description,
            "scope": "collection",
        },
        {
            "_id": environment_id,
            "_type": "environment",
            "parentId": workspace_id,
            "name": "Base Environment",
            "data": collection.variables,
        },
    ]
    resources.extend(_to_insomnia_environments(environment_id, collection.environments, sequence))

    warnings = list(collection.warnings)
    resources.extend(_convert_nodes(collection.items, workspace_id, sequence, warnings))

    return ConversionResult(
        workspace_name=workspace_name or collection.name,
        resources=resources,
        infos=list(collection.infos),
        warnings=warnings,
    )


def _convert_nodes(
    items: Iterable[CollectionNode],
    parent_id: str,
    sequence: count,
    warnings: list[WarningMessage],
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Folder):
            folder_id = _resource_id("fld", next(sequence))
            resources.append(
                {
                    "_id": folder_id,
                    "_type": "request_group",
                    "parentId": parent_id,
                    "name": item.name,
                    "description": item.description,
                    "environment": {},
                }
            )
            resources.extend(_convert_nodes(item.items, folder_id, sequence, warnings))
        elif isinstance(item, RequestItem):
            request_id = _resource_id("req", next(sequence))
            resources.append(_to_insomnia_request(request_id, parent_id, item))
            resources.extend(_to_insomnia_responses(request_id, item.examples, sequence))
            warnings.extend(item.warnings)
    return resources


def _to_insomnia_request(request_id: str, parent_id: str, item: RequestItem) -> dict[str, Any]:
    request: dict[str, Any] = {
        "_id": request_id,
        "_type": "request",
        "parentId": parent_id,
        "name": item.name,
        "description": item.description,
        "method": item.method,
        "url": item.url,
        "headers": [
            {"name": header.name, "value": header.value, "disabled": not header.enabled}
            for header in item.headers
        ],
        "parameters": [
            {"name": param.name, "value": param.value, "disabled": not param.enabled}
            for param in item.query_params
        ],
        "pathParameters": [
            {
                "name": param.name,
                "value": param.value,
                "description": param.description,
                "disabled": not param.enabled,
            }
            for param in item.path_params
        ],
    }
    if item.authentication and item.authentication.type == "bearer":
        request["authentication"] = {
            "type": "bearer",
            "token": item.authentication.token or "",
        }
    if item.body:
        request["body"] = _to_insomnia_body(item.body)
    return request


def _to_insomnia_body(body: Body) -> dict[str, Any]:
    if body.mode == "raw":
        mime_type = body.options.get("raw", {}).get("language")
        if mime_type == "json":
            mime_type = "application/json"
        return {"mimeType": mime_type or "text/plain", "text": body.raw or ""}
    if body.mode == "urlencoded":
        return {
            "mimeType": "application/x-www-form-urlencoded",
            "params": [_to_form_param(entry) for entry in body.form_entries],
        }
    if body.mode == "formdata":
        return {
            "mimeType": "multipart/form-data",
            "params": [_to_form_param(entry) for entry in body.form_entries],
        }
    return {"mimeType": "text/plain", "text": body.raw or ""}


def _to_insomnia_environments(
    base_environment_id: str,
    environments: list[EnvironmentSpec],
    sequence: count,
) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for environment in environments:
        environment_id = _resource_id("env", next(sequence) + 1000)
        resources.append(
            {
                "_id": environment_id,
                "_type": "environment",
                "parentId": base_environment_id,
                "name": environment.name,
                "data": environment.variables,
            }
        )
    return resources


def _to_insomnia_responses(
    request_id: str, examples: list[ExampleResponse], sequence: count
) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for example in examples:
        response_id = _resource_id("rsp", next(sequence))
        responses.append(
            {
                "_id": response_id,
                "_type": "response",
                "parentId": request_id,
                "name": example.name,
                "statusCode": example.status_code,
                "statusMessage": example.status_text,
                "body": example.body,
                "headers": [
                    {"name": header.name, "value": header.value, "disabled": not header.enabled}
                    for header in example.headers
                ],
                "contentType": example.mime_type,
                "mimeType": example.mime_type,
            }
        )
    return responses


def _to_form_param(entry: dict[str, Any]) -> dict[str, Any]:
    param: dict[str, Any] = {
        "name": str(entry.get("key", "")),
        "value": str(entry.get("value", "")),
        "disabled": bool(entry.get("disabled", False)),
    }
    if entry.get("type") == "file":
        param["fileName"] = str(entry.get("src", ""))
    return param


def _resource_id(prefix: str, value: int) -> str:
    return f"{prefix}_{value:04d}"
