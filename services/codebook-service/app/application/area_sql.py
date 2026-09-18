from __future__ import annotations

import ast
import re

from app.domain.models import AREA_CODE_FIELDS

_VALUES_RE = re.compile(r"VALUES\s*\((.*)\)\s*;?\s*$", re.IGNORECASE)


def parse_area_sql(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if "cfg_all_area_code_info" not in line or "VALUES" not in line.upper():
            continue
        match = _VALUES_RE.search(line)
        if match is None:
            continue
        try:
            values = ast.literal_eval("[" + match.group(1) + "]")
        except (SyntaxError, ValueError):
            continue
        if not isinstance(values, list) or len(values) < len(AREA_CODE_FIELDS):
            continue
        item = {field: str(values[index] or "").strip() for index, field in enumerate(AREA_CODE_FIELDS)}
        county_id = item["county_id"]
        if not county_id or county_id in seen:
            continue
        seen.add(county_id)
        rows.append(item)
    return rows
