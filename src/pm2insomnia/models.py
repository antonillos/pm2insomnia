from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WarningMessage:
    kind: str
    message: str
    location: str


@dataclass(slots=True)
class Header:
    name: str
    value: str
    enabled: bool = True


@dataclass(slots=True)
class QueryParam:
    name: str
    value: str
    enabled: bool = True


@dataclass(slots=True)
class PathParam:
    name: str
    value: str
    enabled: bool = True
    description: str = ""


@dataclass(slots=True)
class Body:
    mode: str
    raw: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    form_entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ExampleResponse:
    name: str
    status_code: int
    status_text: str
    headers: list[Header] = field(default_factory=list)
    body: str = ""
    mime_type: str = "text/plain"


@dataclass(slots=True)
class EnvironmentSpec:
    name: str
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Authentication:
    type: str
    token: str | None = None


@dataclass(slots=True)
class InfoMessage:
    kind: str
    message: str


@dataclass(slots=True)
class RequestItem:
    name: str
    method: str
    url: str
    description: str = ""
    headers: list[Header] = field(default_factory=list)
    query_params: list[QueryParam] = field(default_factory=list)
    path_params: list[PathParam] = field(default_factory=list)
    body: Body | None = None
    authentication: Authentication | None = None
    examples: list[ExampleResponse] = field(default_factory=list)
    warnings: list[WarningMessage] = field(default_factory=list)


@dataclass(slots=True)
class Folder:
    name: str
    description: str = ""
    items: list["CollectionNode"] = field(default_factory=list)


CollectionNode = Folder | RequestItem


@dataclass(slots=True)
class Collection:
    name: str
    items: list[CollectionNode]
    description: str = ""
    variables: dict[str, Any] = field(default_factory=dict)
    environments: list[EnvironmentSpec] = field(default_factory=list)
    authentication: Authentication | None = None
    infos: list[InfoMessage] = field(default_factory=list)
    warnings: list[WarningMessage] = field(default_factory=list)


@dataclass(slots=True)
class ConversionResult:
    workspace_name: str
    resources: list[dict[str, Any]]
    infos: list[InfoMessage] = field(default_factory=list)
    warnings: list[WarningMessage] = field(default_factory=list)
