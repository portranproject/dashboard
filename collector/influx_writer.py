"""메시지 → InfluxDB Point 변환과 쓰기. 매핑 기준은 CLAUDE.md 6절.

레코드(alert·evidence·gap·kpm2·hello·f1_evt·overhead)는 시각이 ms라서 ns로 바꿔 쓴다(쓰기 precision은 ns 하나).
같은 series·같은 시각의 점은 InfluxDB가 덮어쓰므로, 서로 다른 레코드가 겹치지 않도록 series 키와 시각을 정한다.
그래서 같은 줄을 다시 써도(전송기 재전송, collector 재시작 뒤) 결과가 그대로다.
"""
from __future__ import annotations

import json
import time
from typing import Any

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from common.config import InfluxSettings

MS = 1_000_000  # 1 ms = 1,000,000 ns

# 화면에 값 하나만 보일 때의 룰별 대표 값 (27_ §5.3 '대표 값(제안)'). values의 키, ues_total만 맨 위 필드.
REPRESENTATIVE_KEY = {
    "L3-01-V": "ratio", "L3-01-O": "stalls_w", "L3-20": "victims", "L3-21": "fails_w",
    "L3-24": "ues_total", "L3-14": "ues_total", "L3-06": "ues_total",
    "AN-01": "sync_w", "AN-02": "idreq_w", "AN-04": "short_ues", "AN-06a": "reauth_ues",
    "AN-07": "fail_ues", "AN-08": "reg_w",
}
HELD_REPRESENTATIVE_KEY = "held_w"  # 판정 보류 경보 (27_ §5.5)

ALERT_JSON_FIELDS = ("cond", "candidates", "conditions", "values", "params", "refs", "ues")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _seq_offset(seq: Any) -> int:
    """같은 ms에 여러 줄이 올 수 있어(27_ §4.2 '같은 ms 안의 순서는 seq 순') ms 안의 ns 자리에 seq를 넣어 가른다."""
    return seq % MS if _is_int(seq) else 0


def is_held_alert(msg: dict) -> bool:
    """판정 보류 경보: rule이 AN-으로 시작하지 않고 cond가 ["held_count"] (27_ §5.5)."""
    return not msg["rule"].startswith("AN-") and msg.get("cond") == ["held_count"]


def representative(msg: dict) -> tuple[str, float] | None:
    """alert의 대표 값 (키 이름, 값). 그 이벤트에 값이 없으면 None."""
    key = HELD_REPRESENTATIVE_KEY if is_held_alert(msg) else REPRESENTATIVE_KEY.get(msg["rule"])
    if key is None:
        return None
    value = msg.get(key) if key == "ues_total" else (msg.get("values") or {}).get(key)
    return (key, float(value)) if _is_number(value) else None


def kpm_fields(record: dict) -> dict[str, float]:
    """kpm2의 cc·si·ext를 '<묶음>.<이름>[.<하위 키>]' 필드로 편다. 모르는 값(null)은 넣지 않는다(그래프에서 '데이터 없음').
    정수·실수가 섞이면 InfluxDB가 쓰기를 거부하므로 모두 실수로 쓴다(27_ §7.1 6번)."""
    fields: dict[str, float] = {}
    for section in ("cc", "si", "ext"):
        values = record.get(section)
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            if _is_number(value):
                fields[f"{section}.{name}"] = float(value)
            elif isinstance(value, dict):
                for sub, sub_value in value.items():
                    if _is_number(sub_value):
                        fields[f"{section}.{name}.{sub}"] = float(sub_value)
    return fields


def _alert_point(msg: dict, env: str) -> Point:
    """alert의 series 키와 시각. 같은 경보의 레코드는 event로 갈린다.
    alert_id는 경보마다 하나라 tag로 둔다 — 경보 상세에서 변수로 고르고, 같은 시각·같은 룰의 다른 경보와 겹치지 않게."""
    return (Point("alert").time(msg["t"] * MS, WritePrecision.NS)
            .tag("env", env).tag("alert_id", msg["alert_id"]).tag("rule", msg["rule"])
            .tag("stage", str(msg["stage"])).tag("kind", msg["kind"]).tag("event", msg["event"])
            .tag("cell", str(msg["cell"])))


def _gap_point(msg: dict, env: str) -> Point:
    return (Point("gap").time(msg["t_from"] * MS, WritePrecision.NS)
            .tag("env", env).tag("alert_id", msg["alert_id"]).tag("cell", str(msg["cell"])))


def session_point(msg: dict, env: str, session: str) -> Point:
    """먼저 세션 없이 쓴 alert·gap 점에 session 필드만 더하는 점(같은 series·같은 시각이면 필드가 합쳐진다)."""
    base = _alert_point(msg, env) if msg["type"] == "alert" else _gap_point(msg, env)
    return base.field("session", session)


def evidence_time_ns(msg: dict, received_ns: int | None = None) -> int:
    raw = msg["raw"]
    for key in ("t_ms", "t_start_ms"):
        if _is_int(raw.get(key)):
            return raw[key] * MS + _seq_offset(msg["seq"])
    # 원본 줄에 시각이 없으면(모르는 raw 형식) 받은 시각으로 쓴다
    received_ns = time.time_ns() if received_ns is None else received_ns
    return (received_ns // MS) * MS + _seq_offset(msg["seq"])


def _new_record_point(msg: dict, env: str, session: str | None, received_ns: int | None) -> Point:
    t = msg["type"]
    if t == "alert":
        p = _alert_point(msg, env)
        p.field("severity", msg["severity"]).field("mode", msg["mode"])
        p.field("unit", msg["unit"]).field("fmt", msg["fmt"])
        for key in ("branch", "reason"):
            if isinstance(msg.get(key), str):
                p.field(key, msg[key])
        for key in ("ues_total", "duration_ms", "evidence_sent", "evidence_dropped"):
            if _is_int(msg.get(key)):
                p.field(key, msg[key])
        for key in ALERT_JSON_FIELDS:
            if key in msg:
                p.field(f"{key}_json", _json(msg[key]))
        rep = representative(msg)
        if rep is not None:
            p.field("rep_key", rep[0]).field("rep_value", rep[1])
        if session:
            p.field("session", session)
        return p

    if t == "evidence":
        raw = msg["raw"]
        p = (Point("evidence").time(evidence_time_ns(msg, received_ns), WritePrecision.NS)
             .tag("env", env).tag("alert_id", msg["alert_id"]).tag("phase", msg["phase"])
             .tag("raw_type", raw["type"]))
        cell = raw.get("cell_id") if _is_int(raw.get("cell_id")) else (msg["ue"][0] if "ue" in msg else None)
        if cell is not None:
            p.tag("cell", str(cell))
        if isinstance(raw.get("session"), str) and raw["session"]:
            p.tag("session", raw["session"])
        p.field("seq", msg["seq"]).field("raw_json", _json(raw))
        if "ue" in msg:
            p.field("du_ue_id", msg["ue"][1]).field("uid", msg["ue"][2])
        if raw["type"] == "kpm2":
            for name, value in kpm_fields(raw).items():
                p.field(name, value)
        else:
            for key in ("msg", "dir", "proto"):
                if isinstance(raw.get(key), str):
                    p.field(key, raw[key])
        return p

    if t == "gap":
        p = _gap_point(msg, env).field("t_to", msg["t_to"])
        for key in ("seq_from", "seq_to"):
            if _is_int(msg.get(key)):
                p.field(key, msg[key])
        if session:
            p.field("session", session)
        return p

    if t == "kpm2":
        # agg_ms를 tag로 둔다 — 주기를 바꾼 직후 옛 주기와 새 주기의 칸이 겹쳐도 둘 다 남도록(27_ §4.1)
        p = (Point("kpm2").time(msg["t_start_ms"] * MS, WritePrecision.NS)
             .tag("env", env).tag("session", msg["session"]).tag("cell", str(msg["cell_id"]))
             .tag("agg_ms", str(msg["agg_ms"]))
             .field("t_end_ms", msg["t_end_ms"]).field("n", msg["n"])
             .field("partial_json", _json(msg.get("partial", []))))
        for key in ("seq_from", "seq_to"):
            if _is_int(msg.get(key)):
                p.field(key, msg[key])
        for name, value in kpm_fields(msg).items():
            p.field(name, value)
        return p

    if t == "hello":
        # hello에는 시각이 없다(27_ §4.3). 받은 시각을 쓴다.
        p = (Point("hello").time(time.time_ns() if received_ns is None else received_ns, WritePrecision.NS)
             .tag("env", env).tag("session", msg["session"]).field("seq", msg["seq"]))
        for key in ("producer", "node_id", "clock"):
            if isinstance(msg.get(key), str):
                p.field(key, msg[key])
        for key in ("period_ms", "noreply_timeout_ms", "si_sample_ms"):
            if _is_int(msg.get(key)):
                p.field(key, msg[key])
        if isinstance(msg.get("ue_evt"), bool):
            p.field("ue_evt", msg["ue_evt"])
        if "cells" in msg:
            p.field("cells_json", _json(msg["cells"]))
        return p

    if t == "f1_evt":
        p = (Point("f1_evt").time(msg["t_ms"] * MS + _seq_offset(msg["seq"]), WritePrecision.NS)
             .tag("env", env).tag("session", msg["session"])
             .field("seq", msg["seq"]).field("msg", msg["msg"]))
        for key in ("cells", "du_ue_ids"):
            if key in msg:
                p.field(f"{key}_json", _json(msg[key]))
        return p

    if t == "overhead":
        # 노드·계측기 자원 (SCHEMA.md 6절). 코어 수는 0도 유효한 측정값이라 늘 실수로, 못 읽은 값(null)은 뺀다
        p = _overhead_base("overhead", msg, env)
        if isinstance(msg.get("process_scope"), str):
            p.field("process_scope", msg["process_scope"])
        cpu = msg["cpu"] if isinstance(msg.get("cpu"), dict) else {}
        memory = msg["memory"] if isinstance(msg.get("memory"), dict) else {}
        if _is_int(cpu.get("count")):
            p.field("cpu_count", cpu["count"])
        for key in ("node_busy_cores", "process_cores"):
            if _is_number(cpu.get(key)):
                p.field(key, float(cpu[key]))
        for key, field_name in (("total_bytes", "mem_total_bytes"), ("used_bytes", "mem_used_bytes"),
                                ("process_rss_bytes", "process_rss_bytes")):
            if _is_int(memory.get(key)):
                p.field(field_name, memory[key])
        return p

    raise ValueError(f"알 수 없는 메시지 type: {t!r}")


NEW_RECORD_TYPES = frozenset({"alert", "evidence", "gap", "kpm2", "hello", "f1_evt", "overhead"})


def _overhead_base(measurement: str, msg: dict, env: str) -> Point:
    """overhead·overhead_link 공통: 시각 = 구간 시작(kpm2와 같은 3초 칸), series = 환경·세션·노드."""
    p = (Point(measurement).time(msg["t_start_ms"] * MS, WritePrecision.NS)
         .tag("env", env).tag("session", msg["session"])
         .field("t_end_ms", msg["t_end_ms"]).field("seq", msg["seq"]))
    if isinstance(msg.get("node_id"), str) and msg["node_id"]:
        p.tag("node", msg["node_id"])
    return p


def overhead_link_points(msg: dict, env: str) -> list[Point]:
    """overhead의 link[] 한 칸(NIC 하나) = 점 하나(measurement overhead_link). 값은 구간 증가분 그대로.
    값이 없는 방향(null·빈 객체·키 없음)은 필드를 뺀다 — 점에는 늘 t_end_ms·seq가 있다."""
    if msg["type"] != "overhead" or not isinstance(msg.get("link"), list):
        return []
    points = []
    for link in msg["link"]:
        if not isinstance(link, dict) or not isinstance(link.get("interface_name"), str):
            continue
        p = _overhead_base("overhead_link", msg, env).tag("iface", link["interface_name"])
        if isinstance(link.get("role"), str) and link["role"]:
            p.tag("role", link["role"])
        for direction in ("ingress", "egress"):
            counts = link.get(direction) if isinstance(link.get(direction), dict) else {}
            for key, name in (("sctp_packet_count", "sctp_packets"), ("wire_byte_count", "wire_bytes")):
                if _is_int(counts.get(key)):
                    p.field(f"{direction}_{name}", counts[key])
        points.append(p)
    return points


def _joined(value: Any, sep: str = ",") -> str | None:
    if isinstance(value, list) and all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in value):
        return sep.join(str(v) for v in value)
    return None


def alert_ue_points(msg: dict, env: str) -> list[Point]:
    """alert의 ues[] 한 칸 = 점 하나(measurement alert_ue). 경보 상세의 '걸린 UE' 표를 행으로 그리려고 따로 둔다
    (ues_json 배열은 Flux·Grafana에서 행으로 펴기 어렵다). update에는 새로 걸린 UE만 오므로 모으면 그 경보의 전체 UE다."""
    if msg["type"] != "alert" or not isinstance(msg.get("ues"), list):
        return []
    points = []
    for ue in msg["ues"]:
        key = f'{ue["cell"]}-{ue["du_ue_id"]}-{ue["uid"]}'
        t_hit = ue["t_hit"] if _is_int(ue.get("t_hit")) else msg["t"]
        p = (Point("alert_ue").time(t_hit * MS, WritePrecision.NS)
             .tag("env", env).tag("alert_id", msg["alert_id"]).tag("ue", key)
             .field("cell", ue["cell"]).field("du_ue_id", ue["du_ue_id"]).field("uid", ue["uid"])
             .field("event", msg["event"]))
        for k in ("cu_ue_id", "crnti"):
            if _is_int(ue.get(k)):
                p.field(k, ue[k])
        if isinstance(ue.get("s_tmsi"), str):
            p.field("s_tmsi", ue["s_tmsi"])
        for k in ("cond", "uncertain", "conditions"):
            joined = _joined(ue.get(k))
            if joined is not None:
                p.field(k, joined)
        if isinstance(ue.get("peers"), list):
            p.field("peers", "; ".join("-".join(str(x) for x in peer) for peer in ue["peers"] if isinstance(peer, list)))
        if isinstance(ue.get("seq_range"), list) and len(ue["seq_range"]) == 2:
            p.field("seq_from", ue["seq_range"][0]).field("seq_to", ue["seq_range"][1])
        if isinstance(ue.get("evidence"), bool):
            p.field("evidence", ue["evidence"])
        if isinstance(ue.get("values"), dict):
            p.field("values_json", _json(ue["values"]))
        points.append(p)
    return points


# 수집 지연(D211): /ingest로 받은 시각 − 레코드의 데이터 시각. 종류마다 기준 시각이 다르다 — kpm2·overhead는 칸이 끝난 시각
# (칸 시작으로 재면 3초 묶음이 섞인다), alert는 탐지 엔진이 판정한 시각, f1_evt는 재시작을 본 시각. evidence(지난 원본 줄)·
# gap·hello(데이터 시각 없음)는 재지 않는다. 두 시계(분석 엔진 노드·대시보드 서버)가 어긋나면 그만큼 틀린다(음수도 가능)
DELAY_REFERENCE = {"kpm2": "t_end_ms", "overhead": "t_end_ms", "alert": "t", "f1_evt": "t_ms"}


def ingest_delay_point(msg: dict, env: str, received_ns: int, offset: int) -> Point | None:
    """measurement ingest_delay — 받은 줄 하나 = 점 하나. 시각 = 받은 시각 + offset ns(같은 요청의 줄끼리 겹치지 않게),
    tags env·type(·event: alert), field delay_ms(실수). 기준 시각이 없는 종류면 None."""
    key = DELAY_REFERENCE.get(msg["type"])
    if key is None or not _is_int(msg.get(key)):
        return None
    p = (Point("ingest_delay").time(received_ns + offset, WritePrecision.NS)
         .tag("env", env).tag("type", msg["type"]).field("delay_ms", received_ns / MS - msg[key]))
    if msg["type"] == "alert":
        p.tag("event", msg["event"])
    return p


def to_point(msg: dict, env: str = "unknown", session: str | None = None, received_ns: int | None = None) -> Point:
    """스키마 검증을 통과한 메시지를 Point로. 숫자 필드는 타입을 고정한다
    (InfluxDB는 같은 필드에 정수·실수가 섞이면 쓰기를 거부하므로).

    env = X-Env, session = 그 경보의 세션(alert·gap), received_ns = 받은 시각(시각 필드가 없는 hello, 시각을 모르는 evidence).
    overhead의 link[]는 overhead_link_points가 따로 만든다."""
    t = msg["type"]
    if t in NEW_RECORD_TYPES:
        return _new_record_point(msg, env, session, received_ns)
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
