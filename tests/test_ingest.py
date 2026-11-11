"""탐지 엔진 레코드 수집 — InfluxDB 변환, /ingest 요청 처리, HTTP 서버.

기준: reference/detection/27_ 명세, schema/SCHEMA.md 2·3·5절.
샘플은 탐지 쪽이 11/05에 보낸 경보 경로 32개(tests/data/detection/)와 SCHEMA.md의 예시다.
"""
import copy
import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from collector.collector import Collector, run
from collector.influx_writer import MS, WriteError, alert_ue_points, kpm_fields, representative, to_point
from collector.ingest import DEFAULT_ENV, IngestSource, dedup_key, parse_env

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = REPO_ROOT / "tests" / "data" / "detection"
EXAMPLES = {}
for block in re.findall(r"```json\n(.*?)```", (REPO_ROOT / "schema" / "SCHEMA.md").read_text(encoding="utf-8"), re.S):
    msg = json.loads(block)
    EXAMPLES[msg["type"]] = msg

T10 = "T10_긴공격_evidence.jsonl"  # 1단계 경보 하나 전체: raise → pre 21 → active → clear → post 10


def example(msg_type, **changes):
    msg = copy.deepcopy(EXAMPLES[msg_type])
    msg.update(changes)
    return msg


def sample_lines(name):
    return (SAMPLES / name).read_text(encoding="utf-8").splitlines()


def body_of(*lines):
    return "".join(line + "\n" for line in lines).encode("utf-8")


def lp(point):
    """line protocol → (series 키, 필드 문자열, 시각)."""
    text = point.to_line_protocol()
    series, rest = text.split(" ", 1)
    fields, t = rest.rsplit(" ", 1)
    return series, fields, int(t)


class FakeWriter:
    def __init__(self):
        self.batches = []
        self.fail_with = None   # 다음 write에서 던질 WriteError
        self.bad_text = None    # 이 글자가 든 점은 한 건씩 쓸 때도 거부 (데이터 문제)

    def write(self, points):
        if self.fail_with:
            raise self.fail_with
        lines = [p.to_line_protocol() for p in points]
        if self.bad_text and any(self.bad_text in l for l in lines):
            raise WriteError("HTTP 422: field type conflict", retryable=False)
        self.batches.append(lines)

    @property
    def points(self):
        return [l for b in self.batches for l in b]


def make_collector(tmp_path, writer, **kw):
    return Collector(writer, tmp_path / "rec", batch_size=kw.pop("batch_size", 500),
                     max_pending=kw.pop("max_pending", 100_000), **kw)


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- InfluxDB 변환

def test_alert_point():
    series, fields, t = lp(to_point(example("alert"), env="lab"))
    assert series == "alert,alert_id=S1-L3-01-V-1-65,cell=1,env=lab,event=raise,kind=attack,rule=L3-01-V,stage=1"
    assert t == 1792209006400 * MS
    for f in ('severity="medium"', 'mode="normal"', 'unit="cell"', "fmt=1i", 'rep_key="ratio"',
              "rep_value=0.9230769230769231", r'cond_json="[\"C1\",\"C2\",\"C2a\"]"',
              r'refs_json="{\"a\":[46,55],\"f\":[56,65]}"'):
        assert f in fields, f
    assert "session=" not in fields and "alert_id=" not in fields  # alert_id는 tag로만


def test_alert_point_with_session_and_end_fields():
    end = next(json.loads(l) for l in sample_lines("T07_세션변경_evidence.jsonl") if '"event":"end"' in l)
    _, fields, _ = lp(to_point(end, env="p4", session="20261105T100200Z"))
    assert 'session="20261105T100200Z"' in fields and 'reason="session_reset"' in fields
    assert "duration_ms=" in fields and "evidence_sent=" in fields and "evidence_dropped=0i" in fields


@pytest.mark.parametrize("name, key, value", [
    ("S20_L3-20_CONNECTED_high_evidence.jsonl", "victims", 1.0),
    ("S24_L3-24_두UE_UPDATE_evidence.jsonl", "ues_total", 1.0),
    ("SAN08_AN-08_이동등록5UE_RAISE_evidence.jsonl", "reg_w", 5.0),
    ("S01_L3-01-O_불확실뒤공격_CLEAR-RAISE_evidence.jsonl", "held_w", 5.0),  # 판정 보류 경보
])
def test_representative_value_of_first_alert(name, key, value):
    first = next(json.loads(l) for l in sample_lines(name) if l.startswith('{"type":"alert"'))
    assert representative(first) == (key, value)


def test_representative_is_none_when_event_has_no_value():
    clear = next(json.loads(l) for l in sample_lines(T10) if '"event":"clear"' in l)
    assert representative(clear) is None  # 1단계 clear에는 values.ratio가 없다


def test_alert_ue_points_one_per_ue():
    raise_ = json.loads(sample_lines("S20_L3-20_CONNECTED_high_evidence.jsonl")[0])
    [line] = [p.to_line_protocol() for p in alert_ue_points(raise_, "lab")]
    series, rest = line.split(" ", 1)
    assert series == "alert_ue,alert_id=20261105T100800Z-L3-20-1-77,env=lab,ue=1-2-2"
    assert rest.endswith(" 1792209006090000000")  # t_hit
    for f in ('cond="same_stmsi,concurrent,not_accepted"', 'peers="1-1-1"', 's_tmsi="0x0123456789ab"', "seq_from=22i",
              "seq_to=25i", "evidence=true", 'event="raise"', "uid=2i", r'values_json="{\"peer\":\"concurrent\"'):
        assert f in rest, f
    assert alert_ue_points(json.loads(sample_lines(T10)[0]), "lab") == []  # 1단계에는 ues가 없다
    # 같은 경보의 raise·update에 실린 UE가 모두 행이 되고 서로 덮어쓰지 않는다
    lines = sample_lines("S20_L3-20_반복_UPDATE_evidence.jsonl")
    alerts = [json.loads(l) for l in lines if l.startswith('{"type":"alert"')]
    keys = {(lp(p)[0], lp(p)[2]) for a in alerts for p in alert_ue_points(a, "lab")}
    assert len(keys) == sum(len(a["ues"]) for a in alerts) == 3


def test_evidence_kpm1_point():
    series, fields, t = lp(to_point(example("evidence"), env="lab"))
    assert series == "evidence,alert_id=S1-L3-24-1-21,cell=1,env=lab,phase=pre,raw_type=ue_evt,session=S1"
    assert t == 1792209001000 * MS + 12  # ms 안의 ns 자리에 seq
    for f in ("seq=12i", "du_ue_id=3i", "uid=1i", 'msg="RRCSetupRequest"', 'dir="UL"', 'proto="RRC"', "raw_json="):
        assert f in fields, f


def test_evidence_kpm2_point_spreads_counters_as_float():
    pre = json.loads(sample_lines(T10)[1])
    assert pre["phase"] == "pre" and pre["raw"]["type"] == "kpm2" and "ue" not in pre
    series, fields, t = lp(to_point(pre, env="lab"))
    assert ",raw_type=kpm2," in series and ",cell=1," in series
    assert t == pre["raw"]["t_start_ms"] * MS + pre["seq"]
    assert "cc.RRC.ConnEstabAtt.total=0," in fields and "cc.RRC.ConnEstabFailCause.NoReply=0," in fields
    assert "du_ue_id" not in fields and "msg=" not in fields


def test_evidence_without_raw_time_uses_received_time():
    msg = example("evidence", raw={"type": "something_new"})
    _, _, t = lp(to_point(msg, received_ns=1_800_000_000_123_456_789))
    assert t == 1_800_000_000_123 * MS + 12


def test_gap_point():
    series, fields, t = lp(to_point(example("gap"), env="lab", session="S1"))
    assert series == "gap,alert_id=S1-L3-01-V-1-65,cell=1,env=lab"
    assert t == 1792209012000 * MS
    assert fields == 'seq_from=121i,seq_to=122i,session="S1",t_to=1792209012100i'


def test_kpm2_point():
    series, fields, t = lp(to_point(example("kpm2"), env="p4"))
    assert series == "kpm2,agg_ms=3000,cell=1,env=p4,session=20261105T010000Z"
    assert t == 1793840400000 * MS
    for f in ("cc.RRC.ConnEstabAtt.total=21,", "cc.RRC.ConnEstabAtt.mo-Signalling=21,", "cc.RRC.RelWithoutSuspendConfig=0,",
              "si.RRC.ConnMean=4.433,", "si.RRC.ConnMax=6,", "ext.UeCtxMax=7,", "n=30i", "t_end_ms=1793840403000i",
              r'partial_json="[\"cc.RRC.ConnEstabFailCause\"]"'):
        assert f in fields + ",", f
    assert "ReEstabAtt" not in fields and "InactiveConn" not in fields  # null은 빼고 쓴다


def test_kpm_fields_are_all_float_and_skip_unknown():
    fields = kpm_fields({"cc": {"a": 1, "b": None, "c": {"total": 2, "x": None, "y": True}, "d": "?"},
                         "si": {"m": 4}, "ext": None})
    assert fields == {"cc.a": 1.0, "cc.c.total": 2.0, "si.m": 4.0}
    assert all(type(v) is float for v in fields.values())


def test_hello_point_uses_received_time():
    series, fields, t = lp(to_point(example("hello"), env="lab", received_ns=1_800_000_000_000_000_001))
    assert series == "hello,env=lab,session=20261024T013000Z" and t == 1_800_000_000_000_000_001
    for f in ("seq=1i", 'producer="ebpf-analyzer 0.1"', 'node_id="cu-p4"', "period_ms=100i", "ue_evt=true",
              'clock="realtime"', "cells_json="):
        assert f in fields, f


def test_f1_evt_point():
    series, fields, t = lp(to_point(example("f1_evt"), env="lab"))
    assert series == "f1_evt,env=lab,session=20261026T090000Z"
    assert t == 1793005300000 * MS + 3001
    assert fields == r'cells_json="[1]",msg="F1SetupRequest",seq=3001i'


def test_samples_never_overwrite_each_other_in_influx():
    """같은 series·같은 시각이면 InfluxDB가 덮어쓴다. 다른 레코드(중복 키가 다른 것)끼리는 겹치면 안 된다.
    샘플에는 같은 ms의 줄(seq로 가름)과 두 경보에 함께 실린 같은 원본 줄(alert_id tag로 가름)이 있다."""
    seen = {}
    for path in sorted(SAMPLES.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            msg = json.loads(line)
            series, _, t = lp(to_point(msg, env="test"))
            key = dedup_key(msg, "test")
            assert seen.setdefault((series, t), key) == key, f"{path.name}: {line[:120]}"
    assert len(seen) == 1758


# --------------------------------------------------------------------------- 중복 키·환경

def test_dedup_key():
    a = example("alert")
    assert dedup_key(a, "p4") == dedup_key(copy.deepcopy(a), "p4")
    assert dedup_key(a, "p4") != dedup_key(a, "lab")                       # 환경이 다르면 다른 줄
    assert dedup_key(a, "p4") == dedup_key(example("alert", values={}), "p4")  # 키에 없는 필드는 무관
    assert dedup_key(a, "p4") != dedup_key(example("alert", event="clear"), "p4")
    e = example("evidence")
    assert dedup_key(e, "p4") != dedup_key(example("evidence", ue=[1, 3, 2]), "p4")
    k = example("kpm2")
    assert dedup_key(k, "p4") != dedup_key(example("kpm2", agg_ms=5000), "p4")  # 주기를 바꾼 칸은 따로 저장
    assert dedup_key(example("overhead"), "p4") is None  # overhead는 거르지 않음


@pytest.mark.parametrize("value, expected", [
    (None, DEFAULT_ENV), ("", DEFAULT_ENV), ("  ", DEFAULT_ENV), ("p4", "p4"), (" lab ", "lab"),
    ("replay-kpm-only", "replay-kpm-only"), ("a" * 64, "a" * 64),
    ("a" * 65, None), ("../etc", None), ("p4 lab", None), ("-p4", None), ("한글", None),
])
def test_parse_env(value, expected):
    assert parse_env(value) == expected


# --------------------------------------------------------------------------- /ingest 요청 처리

def test_request_stores_sample_and_resend_is_all_duplicates(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines(T10)
    assert c.handle_request(body_of(*lines), "lab", "test") == (200, {"accepted": 667, "rejected": 0, "duplicates": 0})
    assert len(w.points) == 667
    assert c.env_raw_path("lab").read_text(encoding="utf-8").splitlines() == lines  # 받은 그대로 녹화
    assert not c.raw_path.exists() and not c.rejected_path.exists()

    assert c.handle_request(body_of(*lines), "lab", "test") == (200, {"accepted": 0, "rejected": 0, "duplicates": 667})
    assert len(w.points) == 667
    assert len(c.env_raw_path("lab").read_text(encoding="utf-8").splitlines()) == 667
    assert (c.stats.received, c.stats.stored, c.stats.duplicates) == (1334, 667, 667)
    c.close()


def test_duplicates_inside_one_request_and_other_env(tmp_path):
    c = make_collector(tmp_path, FakeWriter())
    line = json.dumps(example("alert"))
    assert c.handle_request(body_of(line, line), "lab", "t")[1] == {"accepted": 1, "rejected": 0, "duplicates": 1}
    assert c.handle_request(body_of(line), "p4", "t")[1] == {"accepted": 1, "rejected": 0, "duplicates": 0}
    c.close()
    assert c.env_raw_path("lab").exists() and c.env_raw_path("p4").exists()


def test_bad_lines_are_rejected_and_the_rest_stored(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    raw_kpm2 = example("kpm2")
    raw_kpm2.pop("agg_ms")  # 100 ms 원본은 /ingest로 오지 않는다
    body = body_of(json.dumps(example("alert")), "this is not json", json.dumps(raw_kpm2), "",
                   json.dumps(example("gap")), json.dumps(example("alert", fmt=2, t=1792209006500)))
    status, payload = c.handle_request(body, "lab", "http 10.0.0.1 X-Env=lab")
    c.close()
    assert (status, payload) == (200, {"accepted": 2, "rejected": 3, "duplicates": 0})
    records = read_jsonl(c.rejected_path)
    assert [r["source"] for r in records] == ["http 10.0.0.1 X-Env=lab"] * 3
    assert "JSON 파싱 실패" in records[0]["reasons"][0]
    assert any("agg_ms" in r for r in records[1]["reasons"])
    assert any("fmt" in r for r in records[2]["reasons"])
    assert len(w.points) == 2


def test_non_utf8_body_is_400_without_side_effects(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    status, payload = c.handle_request(b'{"type":"alert"}\n\xff\xfe\n', "lab", "t")
    assert status == 400 and "UTF-8" in payload["error"]
    assert w.points == [] and c.stats.received == 0 and not (tmp_path / "rec").exists()


def test_influx_outage_is_503_and_nothing_is_committed(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines("S20_L3-20_CONNECTED_high_evidence.jsonl")
    w.fail_with = WriteError("connection refused", retryable=True)
    status, payload = c.handle_request(body_of(*lines), "lab", "t")
    assert status == 503 and "connection refused" in payload["error"]
    assert c.in_outage and c.stats.received == 0 and not c.env_raw_path("lab").exists()

    w.fail_with = None  # 전송기가 같은 묶음을 다시 보낸다
    assert c.handle_request(body_of(*lines), "lab", "t") == (200, {"accepted": 5, "rejected": 0, "duplicates": 0})
    assert not c.in_outage and len(c.env_raw_path("lab").read_text(encoding="utf-8").splitlines()) == 5
    c.close()


def test_data_error_rejects_only_that_line(tmp_path):
    w = FakeWriter()
    w.bad_text = "phase=post"  # InfluxDB가 이 줄만 거부했다고 친다
    c = make_collector(tmp_path, w)
    status, payload = c.handle_request(body_of(*sample_lines(T10)), "lab", "t")
    c.close()
    assert (status, payload) == (200, {"accepted": 657, "rejected": 10, "duplicates": 0})
    assert all("InfluxDB 거부" in r["reasons"][0] for r in read_jsonl(c.rejected_path))
    assert len(c.env_raw_path("lab").read_text(encoding="utf-8").splitlines()) == 657


def test_dry_run_request(tmp_path):
    c = make_collector(tmp_path, None)
    assert c.handle_request(body_of(*sample_lines(T10)), "lab", "t")[1]["accepted"] == 667
    c.close()


# --------------------------------------------------------------------------- 세션 (alert·gap ← evidence.raw.session)

def _session_points(writer):
    return [l for l in writer.points if l.startswith("alert,") and 'session="' in l]


def test_alert_gets_session_from_evidence_in_same_request(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    c.handle_request(body_of(*sample_lines(T10)), "lab", "t")
    alerts = [l for l in w.points if l.startswith("alert,")]
    assert len(alerts) == 2 and all('session="20261105T100100Z"' in l for l in alerts)


def test_request_writes_alert_ue_points(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines("S20_L3-20_반복_UPDATE_evidence.jsonl")
    assert c.handle_request(body_of(*lines), "lab", "t")[1]["accepted"] == len(lines)
    assert sum(l.startswith("alert_ue,") for l in w.points) == 3


def test_session_is_backfilled_when_evidence_comes_in_later_request(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines(T10)
    raise_line, evidence = lines[0], lines[1:22]

    c.handle_request(body_of(raise_line), "lab", "t")
    assert _session_points(w) == []
    c.handle_request(body_of(*evidence), "lab", "t")
    [backfill] = _session_points(w)
    series, fields, t = backfill.split(" ")
    assert fields == 'session="20261105T100100Z"'
    assert backfill.startswith(w.points[0].split(" ")[0] + " ") and t == w.points[0].rsplit(" ", 1)[1]  # 같은 점
    c.handle_request(body_of(*lines[22:]), "lab", "t")
    assert len(_session_points(w)) == 2  # 뒤에 온 clear는 처음부터 세션을 갖는다
    assert c.awaiting_session == {}


def test_backfill_is_retried_when_request_fails(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines(T10)
    c.handle_request(body_of(lines[0]), "lab", "t")
    w.fail_with = WriteError("down", retryable=True)
    assert c.handle_request(body_of(*lines[1:22]), "lab", "t")[0] == 503
    w.fail_with = None
    assert c.handle_request(body_of(*lines[1:22]), "lab", "t")[0] == 200
    assert len(_session_points(w)) == 1


def test_sessions_are_per_env(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    lines = sample_lines(T10)
    c.handle_request(body_of(*lines), "lab", "t")
    c.handle_request(body_of(lines[0]), "p4", "t")  # 같은 alert_id라도 다른 환경이면 세션을 모른다
    assert 'session="' not in w.points[-1]


# --------------------------------------------------------------------------- UDP·파일 입력

def test_udp_or_file_input_uses_default_env_and_dedups(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w, default_env="sample")
    lines = sample_lines("S20_L3-20_CONNECTED_high_evidence.jsonl")
    for line in lines + lines[:2]:
        c.handle(line.encode("utf-8"), "file")
    c.handle(json.dumps(example("overhead")).encode("utf-8"), "udp")
    c.flush()
    c.close()
    assert (c.stats.received, c.stats.stored, c.stats.duplicates) == (8, 6, 2)
    assert c.env_raw_path("sample").read_text(encoding="utf-8").splitlines() == lines
    assert len(c.raw_path.read_text(encoding="utf-8").splitlines()) == 1  # overhead는 원래 녹화 파일
    assert sum(1 for l in w.points if l.startswith("alert,") and 'session="' in l) == 1


def test_time_order_warnings_for_new_records(tmp_path, caplog):
    c = make_collector(tmp_path, FakeWriter())
    c.handle_request(body_of(json.dumps(example("gap", t_to=1792209011000)),
                             json.dumps(example("kpm2", t_end_ms=1793840400000))), "lab", "t")
    assert c.stats.warnings == 2 and c.stats.stored == 2
    assert "t_from이 t_to보다 늦음" in caplog.text


# --------------------------------------------------------------------------- HTTP 서버

@pytest.fixture
def server(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    src = IngestSource("127.0.0.1", 0, max_bytes=50_000, request_timeout_s=5, poll_s=0.05)
    stop = threading.Event()
    t = threading.Thread(target=run, args=(c, [src], 60.0, stop), daemon=True)
    t.start()
    yield src.port, c, w
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()
    c.close()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"null")
    finally:
        conn.close()


NDJSON = {"Content-Type": "application/x-ndjson"}


def test_http_ingest_end_to_end(server):
    port, c, w = server
    lines = sample_lines("S20_L3-20_반복_UPDATE_evidence.jsonl")
    status, payload = request(port, "POST", "/ingest", body_of(*lines), {**NDJSON, "X-Env": "p4"})
    assert (status, payload) == (200, {"accepted": len(lines), "rejected": 0, "duplicates": 0})
    assert request(port, "POST", "/ingest", body_of(*lines), {**NDJSON, "X-Env": "p4"})[1]["duplicates"] == len(lines)
    assert len([l for l in w.points if not l.startswith("alert_ue,")]) == len(lines)  # 레코드마다 점 하나 (+ 걸린 UE 점)
    assert c.env_raw_path("p4").exists()


def test_http_missing_env_is_unknown(server):
    port, c, _ = server
    assert request(port, "POST", "/ingest", body_of(json.dumps(example("alert"))), NDJSON)[0] == 200
    assert c.env_raw_path("unknown").exists()


def test_http_error_responses(server):
    port, _, w = server
    one = body_of(json.dumps(example("alert")))
    assert request(port, "POST", "/ingest", one, {**NDJSON, "X-Env": "../x"})[0] == 400
    assert request(port, "POST", "/ingest", b"\xff\n", NDJSON)[0] == 400
    assert request(port, "POST", "/other", one, NDJSON)[0] == 404
    assert request(port, "POST", "/ingest", b"x" * 50_001, NDJSON)[0] == 413
    assert request(port, "GET", "/healthz") == (200, {"status": "ok"})
    assert request(port, "GET", "/ingest")[0] == 404
    assert w.points == []


def test_http_origin_records_proxy_real_ip(server):
    port, c, _ = server
    bad = body_of("not json")
    assert request(port, "POST", "/ingest", bad, {**NDJSON, "X-Env": "p4", "X-Real-IP": "43.202.191.147"})[0] == 200
    c._flush_files()
    [record] = read_jsonl(c.rejected_path)
    assert record["source"] == "http 127.0.0.1 (X-Real-IP 43.202.191.147) X-Env=p4"


def test_http_without_content_length_is_411(server):
    port, _, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", "/ingest")
    conn.endheaders()
    resp = conn.getresponse()
    assert resp.status == 411
    conn.close()


def test_http_503_when_influx_is_down(server):
    port, _, w = server
    w.fail_with = WriteError("down", retryable=True)
    status, payload = request(port, "POST", "/ingest", body_of(json.dumps(example("alert"))), NDJSON)
    assert status == 503 and "down" in payload["error"]
