"""메시지 → InfluxDB Point 변환과 쓰기. 매핑 기준은 CLAUDE.md 6절."""
from __future__ import annotations

import json
from typing import Any

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from common.config import InfluxSettings


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def to_point(msg: dict) -> Point:
    """스키마 검증을 통과한 메시지를 Point로. 숫자 필드는 타입을 고정한다
    (InfluxDB는 같은 필드에 정수·실수가 섞이면 쓰기를 거부하므로)."""
    t = msg["type"]
    if t == "metric":
        labels = msg.get("labels", {})
        p = (Point("metric").time(msg["ts"], WritePrecision.NS)
             .tag("src", msg["src"]).tag("node", msg["node"]).tag("kind", msg["kind"]).tag("name", msg["name"])
             .field("value", float(msg["value"])).field("unit", msg["unit"]))
        for key in ("cell", "ue"):
            if key in labels:
                p.tag(key, labels[key])
        return p

    if t == "detection":
        target = msg["target"]
        p = (Point("detection").time(msg["ts_detected"], WritePrecision.NS)
             .tag("attack_type", msg["attack_type"]).tag("severity", msg["severity"])
             .tag("ruleset", msg["ruleset"]).tag("rule_id", msg["rule_id"]).tag("node", target["node"])
             .field("event_id", msg["event_id"]).field("rule_version", msg["rule_version"])
             .field("ts_first_evidence", int(msg["ts_first_evidence"]))
             .field("latency_ms", (msg["ts_detected"] - msg["ts_first_evidence"]) / 1e6)
             .field("ue_list", _json(target.get("ue", [])))
             .field("evidence_json", _json(msg["evidence"])))
        if "cell" in target:
            p.field("cell", target["cell"])
        return p

    if t == "attack_run":
        return (Point("attack_run").time(msg["ts_start"], WritePrecision.NS)
                .tag("scenario", msg["scenario"])
                .field("run_id", msg["run_id"]).field("ts_end", int(msg["ts_end"]))
                .field("params_json", _json(msg["params"])))

    if t == "overhead":
        return (Point("overhead").time(msg["ts"], WritePrecision.NS)
                .tag("node", msg["node"]).tag("ebpf_on", "true" if msg["ebpf_on"] else "false")
                .field("cpu_pct", float(msg["cpu_pct"])).field("mem_mb", float(msg["mem_mb"])))

    raise ValueError(f"알 수 없는 메시지 type: {t!r}")


class WriteError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class InfluxWriter:
    def __init__(self, settings: InfluxSettings, timeout_ms: int):
        self.settings = settings
        # 재시도는 collector가 배치 단위로 하므로 클라이언트 자체 재시도는 끈다.
        self.client = InfluxDBClient(url=settings.url, token=settings.token, org=settings.org,
                                     timeout=timeout_ms, retries=False)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def check(self) -> None:
        """접속과 bucket을 확인한다. 문제가 있으면 RuntimeError."""
        if not self.client.ping():
            raise RuntimeError(f"InfluxDB에 접속할 수 없습니다: {self.settings.url} (docker compose up -d 했는지 확인)")
        try:
            bucket = self.client.buckets_api().find_bucket_by_name(self.settings.bucket)
        except ApiException as e:
            raise RuntimeError(f"InfluxDB 인증/조회 실패({e.status}): .env의 INFLUX_TOKEN·INFLUX_ORG 확인") from None
        if bucket is None:
            raise RuntimeError(f"bucket이 없습니다: {self.settings.bucket}")

    def write(self, points: list[Point]) -> None:
        try:
            self.write_api.write(bucket=self.settings.bucket, record=points, write_precision=WritePrecision.NS)
        except ApiException as e:
            # 4xx는 데이터 문제(형식, 타입 충돌)라 다시 보내도 같다. 429·5xx는 나중에 다시 시도.
            retryable = e.status is None or e.status == 429 or e.status >= 500
            raise WriteError(f"HTTP {e.status}: {(e.body or e.reason or '').strip()[:300]}", retryable) from None
        except Exception as e:  # 연결 실패, 타임아웃 등
            raise WriteError(f"{type(e).__name__}: {e}"[:300], retryable=True) from None

    def close(self) -> None:
        self.client.close()
