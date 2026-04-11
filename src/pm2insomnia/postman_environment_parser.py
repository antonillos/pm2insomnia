from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from pm2insomnia.models import EnvironmentSpec, InfoMessage


def parse_postman_environments(path: Path) -> tuple[list[EnvironmentSpec], list[InfoMessage]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _parse_environment_zip(path)
    if suffix == ".json":
        return [
            _parse_environment_payload(json.loads(path.read_text(encoding="utf-8")), path.stem)
        ], []
    raise ValueError(f"Unsupported environment file format: {path.name}")


def _parse_environment_zip(path: Path) -> tuple[list[EnvironmentSpec], list[InfoMessage]]:
    environments: list[EnvironmentSpec] = []
    with zipfile.ZipFile(path) as archive:
        for entry_name in sorted(archive.namelist()):
            if entry_name.endswith("/"):
                continue
            if ".." in Path(entry_name).parts:
                continue
            payload = json.loads(archive.read(entry_name).decode("utf-8"))
            fallback_name = Path(entry_name).stem
            environments.append(_parse_environment_payload(payload, fallback_name))
    return _normalize_environment_names(environments)


def _parse_environment_payload(payload: dict[str, Any], fallback_name: str) -> EnvironmentSpec:
    name = str(payload.get("name") or fallback_name)
    variables: dict[str, Any] = {}
    for entry in payload.get("values", []):
        key = str(entry.get("key", "")).strip()
        if not key:
            continue
        if not bool(entry.get("enabled", True)):
            continue
        variables[key] = entry.get("value")
    return EnvironmentSpec(name=name, variables=variables)


def _normalize_environment_names(
    environments: list[EnvironmentSpec],
) -> tuple[list[EnvironmentSpec], list[InfoMessage]]:
    if len(environments) < 2:
        return environments, []

    tokenized_names = [environment.name.split(".") for environment in environments]
    common_token_count = 0
    for candidate_tokens in zip(*tokenized_names, strict=False):
        if len(set(candidate_tokens)) != 1:
            break
        common_token_count += 1

    if common_token_count == 0:
        return environments, []

    stripped_prefix = ".".join(tokenized_names[0][:common_token_count])
    normalized_environments = [
        EnvironmentSpec(
            name=".".join(tokens[common_token_count:]) or environment.name,
            variables=environment.variables,
        )
        for environment, tokens in zip(environments, tokenized_names, strict=False)
    ]
    infos = [
        InfoMessage(
            kind="normalized_environment_names",
            message=(
                f"Trimmed shared environment name prefix '{stripped_prefix}.' "
                "to make Insomnia environment labels easier to distinguish."
            ),
        )
    ]
    return normalized_environments, infos
