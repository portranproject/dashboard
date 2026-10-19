""".env 로딩.

저장소 루트의 .env를 읽어 os.environ에 채운다. 이미 설정된 환경변수는 덮어쓰지 않는다
(셸에서 `INFLUX_URL=... python -m ...`처럼 일시적으로 바꿀 수 있도록).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE 형식만 지원한다. 빈 줄과 # 주석은 무시하고, 값의 양끝 따옴표는 벗긴다."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for key, value in parse_env_file(path).items():
        os.environ.setdefault(key, value)


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"환경변수 {key}가 없습니다. .env.example을 .env로 복사했는지 확인하세요.")
    return value


@dataclass(frozen=True)
class InfluxSettings:
    url: str
    org: str
    bucket: str
    token: str


def influx_settings() -> InfluxSettings:
    load_env()
    return InfluxSettings(
        url=_require("INFLUX_URL"),
        org=_require("INFLUX_ORG"),
        bucket=_require("INFLUX_BUCKET"),
        token=_require("INFLUX_TOKEN"),
    )
