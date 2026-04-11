from __future__ import annotations

import json
from pathlib import Path

from pm2insomnia.models import ConversionResult


def write_insomnia_export(result: ConversionResult, output: Path, pretty: bool = False) -> None:
    payload = {
        "_type": "export",
        "__export_format": 4,
        "__export_date": "2026-04-09T00:00:00.000Z",
        "__export_source": "pm2insomnia",
        "resources": result.resources,
    }
    indent = 2 if pretty else None
    text = json.dumps(payload, indent=indent, ensure_ascii=False)
    if pretty:
        text = f"{text}\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
