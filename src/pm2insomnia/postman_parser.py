from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pm2insomnia.models import Authentication, Body, Collection, ExampleResponse, Folder, Header, PathParam, QueryParam, RequestItem, WarningMessage


def parse_postman_collection(path: Path) -> Collection:
    payload = json.loads(path.read_text(encoding="utf-8"))
    info = payload.get("info", {})
    name = info.get("name") or path.stem
    description = _parse_description(info.get("description"))
    collection_auth = _parse_auth(payload.get("auth"))
    items = [_parse_item(item, [name], collection_auth) for item in payload.get("item", [])]
    collection_items = [item for item in items if item is not None]
    warnings = _collection_level_warnings(payload, name)
    variables = _parse_collection_variables(payload.get("variable", []))
    return Collection(
        name=name,
        items=collection_items,
        description=description,
        variables=variables,
        authentication=collection_auth,
        warnings=warnings,
    )


def _collection_level_warnings(payload: dict[str, Any], collection_name: str) -> list[WarningMessage]:
    warnings: list[WarningMessage] = []
    events = payload.get("event", [])
    if events:
        warnings.append(
            WarningMessage(
                kind="unsupported_event",
                message="Collection-level events are not converted.",
                location=collection_name,
            )
        )
    return warnings


def _parse_collection_variables(entries: list[dict[str, Any]]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for entry in entries:
        key = str(entry.get("key", "")).strip()
        if not key:
            continue
        variables[key] = entry.get("value")
    return variables


def _parse_item(item: dict[str, Any], path_parts: list[str], inherited_auth: Authentication | None) -> Folder | RequestItem | None:
    name = item.get("name", "Unnamed item")
    current_path = [*path_parts, name]
    if "item" in item:
        children = [_parse_item(child, current_path, inherited_auth) for child in item.get("item", [])]
        folder_items = [child for child in children if child is not None]
        return Folder(name=name, description=_parse_description(item.get("description")), items=folder_items)
    if "request" in item:
        return _parse_request_item(name, item, current_path, inherited_auth)
    return None


def _parse_request_item(name: str, item: dict[str, Any], path_parts: list[str], inherited_auth: Authentication | None) -> RequestItem:
    request = item["request"]
    method = request.get("method", "GET")
    url, query_params, path_params = _parse_url(request.get("url"))
    headers = _parse_headers(request.get("header", []))
    body = _parse_body(request.get("body"))
    description = _merge_descriptions(
        request.get("description"),
        item.get("description"),
        _build_path_param_description(path_params),
    )
    authentication = _parse_auth(request.get("auth")) or inherited_auth
    examples = _parse_examples(item.get("response", []))
    warnings = _parse_request_warnings(item=item, request=request, location=" / ".join(path_parts), inherited_auth=inherited_auth)
    return RequestItem(
        name=name,
        method=method,
        url=url,
        description=description,
        headers=headers,
        query_params=query_params,
        path_params=path_params,
        body=body,
        authentication=authentication,
        examples=examples,
        warnings=warnings,
    )


def _parse_url(raw_url: Any) -> tuple[str, list[QueryParam], list[PathParam]]:
    if isinstance(raw_url, str):
        return _strip_query_string(raw_url), [], []
    if not isinstance(raw_url, dict):
        return "", [], []

    query = _parse_query_params(raw_url.get("query", []))
    path_params = _parse_path_params(raw_url.get("variable", []))
    structured_url = _build_structured_url(raw_url)
    if structured_url:
        return structured_url, query, path_params

    raw = raw_url.get("raw")
    if raw:
        return _strip_query_string(str(raw)), query, path_params

    protocol = raw_url.get("protocol", "")
    host = ".".join(raw_url.get("host", []))
    path = "/".join(_normalize_path_segments(raw_url.get("path", [])))
    base = f"{protocol}://{host}" if protocol else host
    return (f"{base}/{path}" if path else base), query, path_params


def _build_structured_url(raw_url: dict[str, Any]) -> str:
    protocol = str(raw_url.get("protocol", ""))
    host_segments = [str(segment) for segment in raw_url.get("host", [])]
    path_segments = [str(segment) for segment in raw_url.get("path", [])]

    if not host_segments and not path_segments:
        return ""

    host = ".".join(host_segments)
    base = f"{protocol}://{host}" if protocol else host
    if path_segments:
        return f"{base}/{'/'.join(path_segments)}"
    return base


def _strip_query_string(raw_url: str) -> str:
    split_result = urlsplit(raw_url)
    if not split_result.query:
        return raw_url
    return urlunsplit((split_result.scheme, split_result.netloc, split_result.path, "", split_result.fragment))


def _parse_query_params(entries: list[dict[str, Any]]) -> list[QueryParam]:
    params: list[QueryParam] = []
    for entry in entries:
        params.append(
            QueryParam(
                name=str(entry.get("key", "")),
                value=str(entry.get("value", "")),
                enabled=not bool(entry.get("disabled", False)),
            )
        )
    return params


def _parse_path_params(entries: list[dict[str, Any]]) -> list[PathParam]:
    params: list[PathParam] = []
    for entry in entries:
        params.append(
            PathParam(
                name=str(entry.get("key", "")),
                value=str(entry.get("value", "")),
                enabled=not bool(entry.get("disabled", False)),
                description=_parse_description(entry.get("description")),
            )
        )
    return params


def _parse_headers(entries: list[dict[str, Any]]) -> list[Header]:
    headers: list[Header] = []
    for entry in entries:
        headers.append(
            Header(
                name=str(entry.get("key", "")),
                value=str(entry.get("value", "")),
                enabled=not bool(entry.get("disabled", False)),
            )
        )
    return headers


def _parse_description(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content.strip()
    return ""


def _merge_descriptions(*values: Any) -> str:
    descriptions: list[str] = []
    for value in values:
        description = _parse_description(value)
        if description and description not in descriptions:
            descriptions.append(description)
    return "\n\n".join(descriptions)


def _build_path_param_description(path_params: list[PathParam]) -> str:
    described_params = [param for param in path_params if param.description]
    if not described_params:
        return ""

    lines = ["Path variables:"]
    for param in described_params:
        state = " (disabled)" if not param.enabled else ""
        default = f" default `{param.value}`" if param.value else ""
        lines.append(f"- `{param.name}`{state}:{default} {param.description}".rstrip())
    return "\n".join(lines)


def _parse_body(body: dict[str, Any] | None) -> Body | None:
    if not body:
        return None
    mode = body.get("mode")
    if mode == "raw":
        return Body(mode="raw", raw=body.get("raw", ""), options=body.get("options", {}))
    if mode in {"urlencoded", "formdata"}:
        key = "urlencoded" if mode == "urlencoded" else "formdata"
        return Body(mode=mode, form_entries=body.get(key, []))
    return Body(mode=mode or "unknown", options=body)


def _parse_auth(auth: dict[str, Any] | None) -> Authentication | None:
    if not auth:
        return None
    auth_type = str(auth.get("type", "")).strip().lower()
    if auth_type != "bearer":
        return Authentication(type=auth_type)

    for entry in auth.get("bearer", []):
        if str(entry.get("key")) == "token":
            return Authentication(type="bearer", token=str(entry.get("value", "")))
    return Authentication(type="bearer", token="")


def _parse_examples(entries: list[dict[str, Any]]) -> list[ExampleResponse]:
    examples: list[ExampleResponse] = []
    for entry in entries:
        headers = _parse_headers(entry.get("header", []))
        status_code = _parse_status_code(entry.get("code"))
        status_text = str(entry.get("status", ""))
        examples.append(
            ExampleResponse(
                name=_build_example_name(entry, status_code, status_text),
                status_code=status_code,
                status_text=status_text,
                headers=headers,
                body=str(entry.get("body", "") or ""),
                mime_type=_infer_mime_type(entry, headers),
            )
        )
    return examples


def _parse_status_code(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _infer_mime_type(entry: dict[str, Any], headers: list[Header]) -> str:
    for header in headers:
        if header.name.lower() == "content-type" and header.value:
            return header.value

    preview_language = str(entry.get("_postman_previewlanguage", "")).lower()
    preview_mapping = {
        "json": "application/json",
        "xml": "application/xml",
        "html": "text/html",
        "text": "text/plain",
    }
    if preview_language in preview_mapping:
        return preview_mapping[preview_language]

    return _infer_mime_type_from_body(str(entry.get("body", "") or ""))


def _build_example_name(entry: dict[str, Any], status_code: int, status_text: str) -> str:
    raw_name = str(entry.get("name", "")).strip()
    if raw_name:
        return raw_name

    status_parts = [part for part in [str(status_code) if status_code else "", status_text.strip()] if part]
    if status_parts:
        return f"Response {' '.join(status_parts)}"
    return "Example Response"


def _infer_mime_type_from_body(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return "text/plain"
    # Best-effort fallback when Postman does not provide explicit content metadata.
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        return "application/json"
    if stripped.startswith("<?xml") or (stripped.startswith("<") and stripped.endswith(">")):
        return "application/xml" if stripped.startswith("<?xml") else "text/html"
    return "text/plain"


def _parse_request_warnings(
    item: dict[str, Any],
    request: dict[str, Any],
    location: str,
    inherited_auth: Authentication | None,
) -> list[WarningMessage]:
    warnings: list[WarningMessage] = []
    request_auth = _parse_auth(request.get("auth"))
    effective_auth = request_auth or inherited_auth
    if effective_auth and effective_auth.type != "bearer":
        warnings.append(
            WarningMessage(
                kind="unsupported_auth",
                message=f"Auth type '{effective_auth.type}' is not converted in this version.",
                location=location,
            )
        )
    events = item.get("event", []) or request.get("event", [])
    if events:
        warnings.append(
            WarningMessage(
                kind="unsupported_event",
                message="Request scripts/tests are not converted.",
                location=location,
            )
        )
    body = request.get("body", {})
    mode = body.get("mode")
    if mode and mode not in {"raw", "urlencoded", "formdata"}:
        warnings.append(
            WarningMessage(
                kind="unsupported_body",
                message=f"Body mode '{mode}' is not fully supported.",
                location=location,
            )
        )
    return warnings
