from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any

from jsonschema import ValidationError, validate


JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
PY_BLOCK_RE = re.compile(r"```python\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class ValidationResult:
    passed: bool = True
    issues: list[str] = field(default_factory=list)


AGENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
    "additionalProperties": True,
}


def validate_python_syntax(text: str) -> ValidationResult:
    result = ValidationResult()
    for idx, block in enumerate(PY_BLOCK_RE.findall(text), start=1):
        try:
            ast.parse(block)
        except SyntaxError as exc:
            result.passed = False
            result.issues.append(f"Python syntax error in block {idx}: {exc}")
    return result


def validate_json_schema(text: str) -> ValidationResult:
    result = ValidationResult()
    for idx, block in enumerate(JSON_BLOCK_RE.findall(text), start=1):
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            result.passed = False
            result.issues.append(f"Invalid JSON in block {idx}: {exc}")
            continue

        try:
            validate(instance=data, schema=AGENT_JSON_SCHEMA)
        except ValidationError as exc:
            result.passed = False
            result.issues.append(f"JSON schema error in block {idx}: {exc.message}")
    return result


def combine_validations(*items: ValidationResult) -> ValidationResult:
    combined = ValidationResult(passed=True, issues=[])
    for item in items:
        if not item.passed:
            combined.passed = False
        combined.issues.extend(item.issues)
    return combined
