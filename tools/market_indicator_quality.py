from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def load_indicator_metadata(cur: Any) -> dict[tuple[str, str], dict[str, Any]]:
    cur.execute(
        """
        select
          source_key, indicator_key, indicator_name, original_unit, normalized_unit,
          scale_factor, is_percentage, is_diffusion_index, neutral_value, frequency,
          aggregation_method, min_sanity_value, max_sanity_value, allow_zero,
          allow_null, description
        from public.market_indicator_metadata
        where active = true
        """
    )
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    for row in cur.fetchall():
        metadata[(row[0], row[1])] = {
            "source_key": row[0],
            "indicator_key": row[1],
            "indicator_name": row[2],
            "original_unit": row[3],
            "normalized_unit": row[4],
            "scale_factor": decimal_or_none(row[5]) or Decimal("1"),
            "is_percentage": bool(row[6]),
            "is_diffusion_index": bool(row[7]),
            "neutral_value": decimal_or_none(row[8]),
            "frequency": row[9],
            "aggregation_method": row[10],
            "min_sanity_value": decimal_or_none(row[11]),
            "max_sanity_value": decimal_or_none(row[12]),
            "allow_zero": bool(row[13]),
            "allow_null": bool(row[14]),
            "description": row[15],
        }
    return metadata


def alert(cur: Any, row: dict[str, Any], raw_value: Decimal | None, normalized_value: Decimal | None, rule: str, error: str) -> None:
    cur.execute(
        """
        insert into public.market_data_quality_alerts(
          source, indicator, period, raw_value, normalized_value,
          validation_rule, error, payload, detected_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
        """,
        (
            row.get("source_key"),
            row.get("indicador_key"),
            row.get("periodo_label") or row.get("periodo_inicio"),
            raw_value,
            normalized_value,
            rule,
            error,
            json.dumps(row.get("payload_original", row), ensure_ascii=False, default=str),
        ),
    )


def normalize_and_validate_indicator(cur: Any, row: dict[str, Any], metadata: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    key = (str(row.get("source_key")), str(row.get("indicador_key")))
    meta = metadata.get(key)
    if not meta:
        return row

    raw_value = decimal_or_none(row.get("valor"))
    if raw_value is None:
        if meta["allow_null"]:
            return row
        alert(cur, row, None, None, "allow_null", "Valor nulo nao permitido para o indicador.")
        return None

    normalized_value = raw_value * meta["scale_factor"]
    if normalized_value == 0 and not meta["allow_zero"]:
        alert(cur, row, raw_value, normalized_value, "allow_zero", "Valor zero nao permitido para o indicador.")
        return None
    if meta["min_sanity_value"] is not None and normalized_value < meta["min_sanity_value"]:
        alert(cur, row, raw_value, normalized_value, "min_sanity_value", "Valor abaixo do minimo de sanidade.")
        return None
    if meta["max_sanity_value"] is not None and normalized_value > meta["max_sanity_value"]:
        alert(cur, row, raw_value, normalized_value, "max_sanity_value", "Valor acima do maximo de sanidade.")
        return None

    clean = dict(row)
    clean["valor"] = float(normalized_value)
    clean["unidade"] = meta["normalized_unit"] or row.get("unidade")
    clean["dimensoes"] = {
        **(row.get("dimensoes") or {}),
        "raw_unit": row.get("unidade"),
        "normalized_unit": meta["normalized_unit"],
        "scale_factor": str(meta["scale_factor"]),
    }
    return clean


def normalize_and_validate_indicators(cur: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    metadata = load_indicator_metadata(cur)
    valid: list[dict[str, Any]] = []
    for row in rows:
        clean = normalize_and_validate_indicator(cur, row, metadata)
        if clean is not None:
            valid.append(clean)
    return valid
