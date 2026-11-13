"""replay — 탐지 엔진 레코드를 시각을 옮겨 /ingest로 다시 보내기 (CLAUDE.md 11절, replay/replay.py)."""
import http.server
import json
import threading
from pathlib import Path

import pytest

from collector.collector import Collector, run as run_collector
from collector.ingest import IngestSource
from common.schema import validation_errors
from common.transport import encode
from replay.replay import (FileSink, IngestSink, SendError, align_ms, kst, load, main, parse_time, plan, record_time,
                           replay_tag, run, select_window, shift_record)

SAMPLES = Path(__file__).resolve().parent / "data" / "detection"
T10 = SAMPLES / "T10_긴공격_evidence.jsonl"         # 1단계: raise → pre 21 → active → clear → post
S24 = SAMPLES / "S24_L3-24_두UE_UPDATE_evidence.jsonl"  # 3단계: raise → pre(KPM1) → update …
KPM2 = {"type": "kpm2", "ver": 1, "agg_ms": 3000, "session": "S9", "cell_id": 1, "t_start_ms": 1792209003000,
        "t_end_ms": 1792209006000, "n": 30, "cc": {"RRC.ConnEstabAtt": {"total": 1}}, "partial": []}
HELLO = {"type": "hello", "ver": 1, "session": "S9", "seq": 1}
F1 = {"type": "f1_evt", "ver": 1, "session": "S9", "seq": 5, "t_ms": 1792209004000, "msg": "F1SetupRequest", "cells": [1]}
OVERHEAD = {"type": "overhead", "ver": 1, "session": "S9", "seq": 6, "node_id": "cu", "t_start_ms": 1792209003000,
            "t_end_ms": 1792209006000, "cpu": {"count": 4, "node_busy_cores": 0.5, "process_cores": 0.1},
            "memory": {"total_bytes": 8, "used_bytes": 4, "process_rss_bytes": 1}, "link": []}


def records(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def write(path, lines):
    path.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- 읽기·시각 옮기기

def test_load_keeps_file_order_and_skips_bad_and_old_messages(tmp_path):
    good = [*T10.read_text(encoding="utf-8").splitlines()[:4], encode(OVERHEAD)]  # overhead(v0.5)도 재생한다
    old = encode({"type": "overhead", "ts": 1763280000000000000, "node": "cu", "ebpf_on": True, "cpu_pct": 1, "mem_mb": 1})
    path = write(tmp_path / "x.jsonl", [good[0], "not json", old, *good[1:], '{"type":"alert"}', ""])
    loaded, skipped = load(path)
    assert [encode(m) for m in loaded] == [encode(json.loads(l)) for l in good]
    assert skipped == 3


def test_record_time():
    alert, pre = records(T10)[:2]
    assert record_time(alert) == alert["t"]
    assert record_time(pre) == pre["raw"]["t_start_ms"]
    assert record_time(records(S24)[1]) == records(S24)[1]["raw"]["t_ms"]
    assert record_time(KPM2) == KPM2["t_end_ms"]  # 묶은 칸은 칸이 닫힌 뒤에 나간다
    assert record_time(F1) == F1["t_ms"]
    assert record_time(OVERHEAD) == OVERHEAD["t_end_ms"]  # 구간이 닫힌 뒤에 나간다
    assert record_time(HELLO) is None


def test_shift_record_moves_every_time_and_tags_ids():
    raise_, pre = records(S24)[:2]
    moved = shift_record(raise_, 60_000, "~rX")
    assert moved["t"] == raise_["t"] + 60_000 and moved["alert_id"] == raise_["alert_id"] + "~rX"
    assert [u["t_hit"] for u in moved["ues"]] == [u["t_hit"] + 60_000 for u in raise_["ues"]]
    moved_pre = shift_record(pre, 60_000, "~rX")
    assert moved_pre["raw"]["t_ms"] == pre["raw"]["t_ms"] + 60_000
    assert moved_pre["raw"]["session"] == pre["raw"]["session"] + "~rX" and moved_pre["alert_id"].endswith("~rX")
    k = shift_record(KPM2, 3000, "~rX")
    assert (k["t_start_ms"], k["t_end_ms"], k["session"]) == (1792209006000, 1792209009000, "S9~rX")
    assert shift_record(HELLO, 3000, "~rX")["session"] == "S9~rX"
    assert shift_record(F1, 3000, "")["t_ms"] == F1["t_ms"] + 3000
    o = shift_record(OVERHEAD, 3000, "~rX")
    assert (o["t_start_ms"], o["t_end_ms"], o["session"]) == (1792209006000, 1792209009000, "S9~rX")
    assert validation_errors(o) == []
    assert raise_["t"] == records(S24)[0]["t"]  # 원본은 그대로
    for m in (moved, moved_pre, k):
        assert validation_errors(m) == []


def test_align_ms():
    assert align_ms(records(T10)) == 3000  # kpm2 묶음이 없으면 기본 3초
    assert align_ms([KPM2, {**KPM2, "agg_ms": 5000}]) == 15000


# --------------------------------------------------------------------------- 재생 순서·시각

def test_plan_retimes_to_start_keeps_order_and_never_goes_back():
    recs = records(T10)
    start = 1_800_000_000_123
    planned = plan([("T10", recs)], start, gap_ms=10_000, tag="~rX")
    assert [p.msg["type"] for p in planned] == [m["type"] for m in recs]  # 파일 순서 그대로
    sends = [p.send_ms for p in planned]
    assert sends == sorted(sends)                                  # 거꾸로 가지 않음
    delta = planned[0].msg["t"] - recs[0]["t"]
    assert delta % 3000 == 0                                       # 3초 칸 경계 유지
    first_data = min(record_time(m) for m in recs) + delta
    assert start <= first_data < start + 3000
    # pre 근거(경보 2.1초 전 데이터)는 raise 뒤에 바로 나간다
    assert planned[1].msg["phase"] == "pre" and planned[1].send_ms == planned[0].send_ms
    assert all(p.msg.get("alert_id", "").endswith("~rX") for p in planned)


def test_plan_plays_files_one_after_another():
    planned = plan([("a", records(S24)), ("b", records(T10))], 1_800_000_000_000, gap_ms=30_000, tag="~rX")
    a = [p for p in planned if p.source == "a"]
    b = [p for p in planned if p.source == "b"]
    assert b[0].send_ms >= a[-1].send_ms + 30_000


def test_plan_without_retime_keeps_records_as_they_were():
    recs = records(S24)
    planned = plan([("a", recs)], None, gap_ms=0, tag="")
    assert [p.msg for p in planned] == recs


def test_replay_tag():
    assert replay_tag(None) == ""
    assert replay_tag(1_800_000_000_000) == "~r20270115T080000Z"


# --------------------------------------------------------------------------- 구간 (--from/--to)

def test_parse_time_without_zone_is_korean_time():
    """Grafana 화면 시각(한국)을 그대로 적는다. 서버·컨테이너 시계(UTC)와 상관없이 같은 값."""
    utc_ms = 1_794_378_480_000  # 2026-11-11 06:28:00 UTC = 15:28 KST
    assert parse_time("2026-11-11T15:28") == parse_time("2026-11-11 15:28:00") == utc_ms
    assert parse_time("2026-11-11T06:28:00Z") == parse_time("2026-11-11T15:28:00+09:00") == utc_ms
    assert kst(utc_ms) == "2026-11-11 15:28:00"


def test_select_window_keeps_whole_alerts():
    recs = records(T10)  # raise → pre(경보 2.1초 전 데이터) … → clear → post(clear 뒤 데이터)
    raise_t = recs[0]["t"]
    # 경보가 구간 안에서 시작했으면 구간 밖 레코드(pre 근거, clear·post)까지 통째로
    assert select_window(recs, raise_t, raise_t + 1) == recs
    assert select_window(recs, None, raise_t + 1) == recs
    # 구간 전에 시작한 경보는 구간 안의 근거·clear가 있어도 모두 뺀다(앞이 잘린 경보를 만들지 않음)
    assert select_window(recs, raise_t + 1, None) == []
    assert select_window(recs, None, None) is recs


def test_select_window_by_data_time_and_hello_takes_next_time():
    kpm_early = {**KPM2, "t_start_ms": 1792209000000, "t_end_ms": 1792209003000}
    recs = [kpm_early, HELLO, KPM2, F1]  # 나가는 시각: 003000, (다음 줄) 006000, 006000, 004000
    assert select_window(recs, 1792209005000, 1792209007000) == [HELLO, KPM2]
    assert select_window(recs, 1792209003000, 1792209005000) == [kpm_early, F1]
    assert select_window(recs, None, 1792209003000) == []  # to는 그 시각 전까지
    assert select_window([KPM2, HELLO], 1792209006000, None) == [KPM2, HELLO]  # 뒤에 줄이 없으면 앞 줄 시각


def test_cli_window_in_korean_time(tmp_path):
    """녹화 두 경보 중 구간 안에서 시작한 것만, 앞뒤 근거까지 통째로 보낸다."""
    s24, t10 = records(S24), records(T10)
    assert s24[0]["t"] + 1000 < t10[0]["t"]  # S24 경보가 먼저 시작, 근거는 T10 시작 뒤까지 섞여 있음
    rec = write(tmp_path / "raw-p4.jsonl", [encode(m) for m in s24 + t10])
    out = tmp_path / "out.jsonl"
    common = ["--retime", "none", "--speed", "0", "--out", f"file://{out}"]
    # kst()는 초까지라 T10 시작(…06.4초)보다 조금 앞, S24 시작(…01.1초)보다는 뒤
    assert main([str(rec), "--from", kst(t10[0]["t"]), *common]) == 0
    assert [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()] == t10
    assert main([str(rec), "--to", kst(s24[0]["t"]), *common]) == 1  # 두 경보 모두 그 뒤에 시작


# --------------------------------------------------------------------------- collector로 보내기

class FakeWriter:
    def __init__(self):
        self.points = []

    def write(self, points):
        self.points += [p.to_line_protocol() for p in points]


@pytest.fixture
def collector(tmp_path):
    c = Collector(FakeWriter(), tmp_path / "rec", batch_size=500, max_pending=100_000)
    src = IngestSource("127.0.0.1", 0, max_bytes=20_000, request_timeout_s=10, poll_s=0.05)
    stop = threading.Event()
    t = threading.Thread(target=run_collector, args=(c, [src], 60.0, stop), daemon=True)
    t.start()
    yield c, f"http://127.0.0.1:{src.port}/ingest"
    stop.set()
    t.join(timeout=5)
    c.close()


def test_each_retimed_replay_is_stored_separately(collector, monkeypatch):
    c, url = collector
    monkeypatch.setenv("COLLECTOR_HTTP_MAX_BYTES", "20000")
    for when in ("2026-12-01T10:00:00", "2026-12-01T11:00:00"):
        assert main([str(T10), "--out", url, "--env", "replay", "--speed", "0", "--retime", when]) == 0
    assert c.stats.stored == 2 * 667 and c.stats.duplicates == 0 and c.stats.rejected == 0
    lines = c.env_raw_path("replay").read_text(encoding="utf-8").splitlines()
    assert len({json.loads(l).get("alert_id") for l in lines if '"type":"alert"' in l}) == 2  # 재생마다 다른 경보


def test_replay_without_retime_is_deduplicated(collector, monkeypatch):
    c, url = collector
    monkeypatch.setenv("COLLECTOR_HTTP_MAX_BYTES", "20000")
    for _ in range(2):
        assert main([str(S24), "--out", url, "--env", "lab", "--speed", "0", "--retime", "none"]) == 0
    n = len(records(S24))
    assert (c.stats.stored, c.stats.duplicates) == (n, n)


def test_ingest_sink_splits_on_413_and_counts(collector):
    c, url = collector  # collector 요청 상한 20,000B
    sink = IngestSink(url, "replay", max_bytes=1_000_000)
    for p in plan([("T10", records(T10))], 1_800_000_000_000, 0, "~rY"):
        sink.send(encode(p.msg))
    sink.close()
    assert sink.totals["accepted"] == 667 and sink.totals["requests"] > 2  # 413을 받아 나눠 보냄
    assert c.stats.stored == 667


def test_ingest_sink_retries_503_then_gives_up_on_other_errors(monkeypatch):
    replies = [503, 503, 200, 404]

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            code = replies.pop(0)
            body = json.dumps({"accepted": 1, "rejected": 0, "duplicates": 0} if code == 200 else {"error": "x"}).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr("replay.replay.time.sleep", lambda s: None)
    try:
        sink = IngestSink(f"http://127.0.0.1:{server.server_port}/ingest", "replay")
        sink.send(encode(HELLO))
        sink.flush()
        assert sink.totals["accepted"] == 1 and replies == [404]
        sink.send(encode(HELLO))
        with pytest.raises(SendError, match="HTTP 404"):
            sink.flush()
    finally:
        server.shutdown()


def test_file_output_is_valid_and_paced_run_counts(tmp_path):
    out = tmp_path / "retimed.jsonl"
    sink = FileSink(out)
    counts = run(plan([("S24", records(S24))], 1_800_000_000_000, 0, "~rZ"), sink, speed=0)
    sink.close()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert sum(counts.values()) == len(lines) == len(records(S24))
    assert all(validation_errors(json.loads(l)) == [] for l in lines)


@pytest.mark.parametrize("argv, message", [
    (["--env", "a b"], "--env"),
    (["--out", "udp://127.0.0.1:9999"], "--out"),
    (["--retime", "yesterday"], "--retime"),
    (["--speed", "-1"], "--speed"),
    (["--from", "3pm"], "--from"),
    (["--from", "2026-11-11T15:10", "--to", "2026-11-11T15:08"], "--from은 --to보다 앞"),
])
def test_cli_errors(argv, message, capsys):
    with pytest.raises(SystemExit):
        main([str(S24), *argv])
    assert message in capsys.readouterr().err
