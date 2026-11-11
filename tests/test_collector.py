"""collector 공통 동작 — UDP·파일 입력, 검증·거부 로그, 녹화, 배치 쓰기, InfluxDB 장애.

/ingest 요청 처리·중복 제거·세션·탐지 엔진 레코드 변환은 tests/test_ingest.py.
"""
import copy
import json
import threading
from pathlib import Path

import pytest

from collector.collector import Collector, run
from collector.influx_writer import WriteError, to_point
from common.transport import FileTailSource, encode

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = {}
for block in (REPO_ROOT / "schema" / "SCHEMA.md").read_text(encoding="utf-8").split("```json\n")[1:]:
    msg = json.loads(block.split("```")[0])
    EXAMPLES[msg["type"]] = msg
T10 = REPO_ROOT / "tests" / "data" / "detection" / "T10_긴공격_evidence.jsonl"


def example(msg_type, **changes):
    msg = copy.deepcopy(EXAMPLES[msg_type])
    msg.update(changes)
    return msg


def overhead(i=0, **changes):
    return example("overhead", ts=example("overhead")["ts"] + i, **changes)


# --------------------------------------------------------------------------- InfluxDB 변환 (overhead)

def test_overhead_point():
    assert to_point(example("overhead")).to_line_protocol() == (
        "overhead,ebpf_on=true,node=cu cpu_pct=23.4,mem_mb=512 1763280000000000000"
    )


def test_overhead_integer_values_are_float():
    line = to_point(overhead(cpu_pct=3, mem_mb=100)).to_line_protocol()
    assert "cpu_pct=3," in line and "mem_mb=100 " in line and "i" not in line.split(" ")[1]


# --------------------------------------------------------------------------- Collector

class FakeWriter:
    def __init__(self):
        self.batches = []
        self.fail_with = None      # 다음 write에서 던질 WriteError
        self.bad_values = set()    # 이 cpu_pct를 가진 overhead는 한 건씩 쓸 때도 거부

    def write(self, points):
        if self.fail_with:
            raise self.fail_with
        lines = [p.to_line_protocol() for p in points]
        if any(f"cpu_pct={v}," in l for v in self.bad_values for l in lines):
            raise WriteError("HTTP 422: field type conflict", retryable=False)
        self.batches.append(lines)

    @property
    def points(self):
        return [l for b in self.batches for l in b]


def make_collector(tmp_path, writer, batch_size=500, max_pending=100_000, **kw):
    return Collector(writer, tmp_path / "rec", batch_size=batch_size, max_pending=max_pending, **kw)


def feed(collector, *lines, origin="test"):
    for line in lines:
        collector.handle(line if isinstance(line, bytes) else line.encode("utf-8"), origin)


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_valid_messages_are_recorded_verbatim_and_written(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w, default_env="lab")
    # 공백·키 순서가 다른 원본도 "받은 그대로" 녹화돼야 한다
    lines = [encode(overhead()).replace(",", ", "), encode(example("alert")), encode(example("kpm2"))]
    feed(c, *lines)
    assert w.points == []  # flush 전에는 쓰지 않음
    c.flush()
    c.close()
    assert len(w.points) == 3 and len(w.batches) == 1
    assert c.raw_path.read_text(encoding="utf-8").splitlines() == lines[:1]          # overhead
    assert c.env_raw_path("lab").read_text(encoding="utf-8").splitlines() == lines[1:]  # 탐지 엔진 레코드는 환경별
    assert not c.rejected_path.exists()
    assert (c.stats.received, c.stats.stored, c.stats.rejected) == (3, 3, 0)


@pytest.mark.parametrize("raw, reason", [
    (b'{"type":"alert", broken', "JSON 파싱 실패"),
    (encode(overhead(cpu_pct=1)).replace('"cpu_pct":1', '"cpu_pct":NaN').encode(), "표준이 아닌 값 NaN"),
    (encode(overhead(node="ru")).encode(), "'ru' is not one of"),
    (encode(example("alert", fmt=2)).encode(), "fmt"),
    (b'{"type":"alert","t":"\xff\xfe"}', "UTF-8"),
    (b"[1, 2, 3]", "is not of type 'object'"),
])
def test_invalid_messages_go_to_rejected_log_with_reason(tmp_path, raw, reason):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    feed(c, raw)
    c.flush()
    c.close()
    assert w.points == [] and not c.raw_path.exists()
    [record] = read_jsonl(c.rejected_path)
    assert record["source"] == "test"
    assert any(reason in r for r in record["reasons"]), record["reasons"]
    assert record["raw"] == raw.decode("utf-8", errors="replace")
    assert c.stats.rejected == 1


def test_rejected_log_accumulates_across_runs(tmp_path):
    for _ in range(2):
        c = make_collector(tmp_path, FakeWriter())
        feed(c, "not json")
        c.close()
    assert len(read_jsonl(tmp_path / "rec" / "rejected.jsonl")) == 2


def test_batches_are_split_by_batch_size(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w, batch_size=3)
    feed(c, *[encode(overhead(i)) for i in range(7)])
    c.flush()
    assert [len(b) for b in w.batches] == [3, 3, 1]


def test_retryable_failure_keeps_messages_until_influx_recovers(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    feed(c, encode(overhead()), encode(example("alert")))
    w.fail_with = WriteError("connection refused", retryable=True)
    c.flush()
    assert c.in_outage and len(c.pending) == 2 and c.stats.stored == 0
    w.fail_with = None
    c.flush()
    assert not c.in_outage and c.pending == [] and c.stats.stored == 2


def test_data_error_isolates_bad_message(tmp_path):
    w = FakeWriter()
    w.bad_values = {"666"}
    c = make_collector(tmp_path, w)
    feed(c, encode(overhead(0, cpu_pct=1.0)), encode(overhead(1, cpu_pct=666.0)), encode(example("alert")))
    c.flush()
    c.close()
    assert c.stats.stored == 2 and c.stats.rejected == 1
    [record] = read_jsonl(c.rejected_path)
    assert "InfluxDB 거부" in record["reasons"][0] and '"cpu_pct":666.0' in record["raw"]


def test_pending_is_capped_while_influx_is_down(tmp_path):
    w = FakeWriter()
    w.fail_with = WriteError("down", retryable=True)
    c = make_collector(tmp_path, w, max_pending=5)
    feed(c, *[encode(overhead(i)) for i in range(8)])
    assert len(c.pending) == 5 and c.stats.dropped == 3
    c.close()
    assert len(c.raw_path.read_text(encoding="utf-8").splitlines()) == 8  # 버린 것도 녹화에는 있다


def test_dry_run_records_without_writer(tmp_path):
    c = make_collector(tmp_path, None)
    feed(c, encode(overhead()), "garbage")
    c.flush()
    c.close()
    assert (c.stats.stored, c.stats.rejected) == (1, 1)
    assert c.raw_path.exists() and c.rejected_path.exists()


def test_run_reads_sample_file_to_end_and_flushes(tmp_path):
    lines = T10.read_text(encoding="utf-8").splitlines()
    src_path = tmp_path / "sample.jsonl"
    src_path.write_text("".join(l + "\n" for l in lines) + "this is not json\n", encoding="utf-8")

    w = FakeWriter()
    c = make_collector(tmp_path, w, batch_size=500, default_env="sample")
    run(c, [FileTailSource(src_path, follow=False)], flush_interval_s=1.0, stop=threading.Event())
    c.close()
    assert c.stats.stored == len(lines) and c.stats.rejected == 1
    # 줄마다 점 하나 + 경보(raise)를 세션 없이 먼저 쓴 뒤 첫 근거에서 알게 된 세션을 덧붙이는 점 하나
    assert len(w.points) == len(lines) + 1
    assert sum(1 for p in w.points if p.startswith("alert,") and p.split(" ")[1].startswith('session="')) == 1
    assert c.env_raw_path("sample").read_text(encoding="utf-8").splitlines() == lines


def test_run_stops_on_stop_event_and_flushes(tmp_path):
    src_path = tmp_path / "live.jsonl"
    src_path.write_text(encode(overhead()) + "\n", encoding="utf-8")
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    stop = threading.Event()
    t = threading.Thread(target=run, args=(c, [FileTailSource(src_path, poll_s=0.05)], 60.0, stop))
    t.start()
    with src_path.open("a", encoding="utf-8") as fp:
        fp.write(encode(overhead(1)) + "\n")
    deadline = threading.Event()
    for _ in range(100):  # 두 줄 다 받을 때까지 최대 5초
        if c.stats.received == 2:
            break
        deadline.wait(0.05)
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert len(w.points) == 2  # flush 주기(60초)를 기다리지 않고 종료 시 flush
