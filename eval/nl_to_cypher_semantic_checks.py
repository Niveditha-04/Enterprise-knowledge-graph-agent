"""Helpers for NL→Cypher semantic correctness tests."""

from __future__ import annotations

from typing import Any


def flatten_result_values(results: list[dict] | None) -> list[Any]:
    values: list[Any] = []
    if not results:
        return values
    for row in results:
        for value in row.values():
            _collect(value, values)
    return values


def _collect(value: Any, out: list[Any]) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _collect(nested, out)
    elif isinstance(value, list):
        for item in value:
            _collect(item, out)
    elif value is not None:
        out.append(value)


def normalize_string(value: Any) -> str:
    return str(value).strip().casefold()


def values_include_string(results: list[dict] | None, expected: str) -> bool:
    target = normalize_string(expected)
    return any(normalize_string(v) == target for v in flatten_result_values(results))


def values_include_int(results: list[dict] | None, expected: int) -> bool:
    for value in flatten_result_values(results):
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value == expected:
            return True
        if isinstance(value, float) and abs(value - expected) < 1e-6:
            return True
        if str(value).isdigit() and int(value) == expected:
            return True
    return False


def values_include_bool(results: list[dict] | None, expected: bool) -> bool:
    for value in flatten_result_values(results):
        if isinstance(value, bool) and value == expected:
            return True
        if str(value).lower() in {"true", "false"} and str(value).lower() == str(expected).lower():
            return True
    return False


def values_include_all_strings(results: list[dict] | None, expected_values: list[str]) -> bool:
    normalized_results = {normalize_string(v) for v in flatten_result_values(results)}
    return all(normalize_string(item) in normalized_results for item in expected_values)


def is_unsupported_response(result: dict) -> bool:
    """Pass when the system does not return a fabricated scalar answer."""
    if result.get("error"):
        return True
    values = flatten_result_values(result.get("results"))
    return len(values) == 0


def semantic_match(results: list[dict] | None, expected: dict) -> bool:
    expected_type = expected["type"]
    if expected_type == "string":
        return values_include_string(results, expected["value"])
    if expected_type == "int":
        return values_include_int(results, expected["value"])
    if expected_type == "bool":
        return values_include_bool(results, expected["value"])
    if expected_type == "string_set":
        return values_include_all_strings(results, expected["value"])
    raise ValueError(f"Unsupported expected type: {expected_type}")
