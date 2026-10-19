"""메시지 JSON Schema 검증.

스키마의 단일 기준은 schema/messages.schema.json 이다.
mock, collector, 테스트 모두 이 모듈을 통해 같은 파일로 검증한다.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, validators

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "messages.schema.json"


def _is_strict_integer(checker, instance) -> bool:
    # JSON Schema 표준은 1.0도 integer로 보지만, ns 타임스탬프를 float로 보내면
    # 정밀도가 깨지므로 실제 int만 허용한다.
    return isinstance(instance, int) and not isinstance(instance, bool)


def _is_finite_number(checker, instance) -> bool:
    # json.loads는 NaN/Infinity를 받아들이지만 InfluxDB에는 쓸 수 없다.
    return (
        isinstance(instance, (int, float))
        and not isinstance(instance, bool)
        and math.isfinite(instance)
    )


_StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine_many(
        {"integer": _is_strict_integer, "number": _is_finite_number}
    ),
)


@lru_cache(maxsize=1)
def get_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return _StrictValidator(schema)


def validation_errors(msg: Any) -> list[str]:
    """검증 실패 사유 목록. 통과하면 빈 리스트."""
    errors = sorted(get_validator().iter_errors(msg), key=lambda e: list(e.absolute_path))
    return [f"{e.json_path}: {e.message}" for e in errors]


def is_valid(msg: Any) -> bool:
    return get_validator().is_valid(msg)
