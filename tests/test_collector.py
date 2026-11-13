"""collector 공통 동작 — UDP·파일 입력, 검증·거부 로그, 녹화, 배치 쓰기, InfluxDB 장애. overhead 변환.

/ingest 요청 처리·중복 제거·세션·탐지 엔진 레코드 변환은 tests/test_ingest.py.
"""
import copy
import json
import threading
from pathlib import Path

import pytest

from collector.collector import Collector, run
from collector.influx_writer import WriteError, overhead_link_points, to_point
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


def overhead(i=0, busy=0.03, link=False, **changes):
    """i번째 3초 구간의 overhead(SCHEMA.md 6절 예시 기준). 공통 동작 시험에는 link 없이 = 줄 하나에 점 하나."""
    msg = example("overhead", **changes)
    msg["seq"] += i
    msg["t_start_ms"] += 3000 * i
    msg["t_end_ms"] += 3000 * i
    msg["cpu"]["node_busy_cores"] = busy
    if not link:
        msg.pop("link", None)
    return msg


# --------------------------------------------------------------------------- InfluxDB 변환 (overhead)

def test_overhead_point():
    assert to_point(example("overhead"), env="p4").to_line_protocol() == (
        "overhead,env=p4,node=cu,session=20261113T043024Z "
        "cpu_count=4i,mem_total_bytes=8153268224i,mem_used_bytes=4623908864i,node_busy_cores=0.03,"
        'process_cores=0,process_rss_bytes=323219456i,process_scope="self",seq=37i,t_end_ms=1794544264000i '
        "1794544261000000000"
    )


def test_overhead_cores_are_always_float_and_nulls_are_dropped():
    msg = overhead(busy=2)  # 정수 2로 와도 실수로(0.03과 같은 필드라 타입이 섞이면 InfluxDB가 거부)
    msg["cpu"]["process_cores"] = None
    msg["memory"]["process_rss_bytes"] = None
    msg.pop("node_id")
    series, fields = to_point(msg, env="p4").to_line_protocol().split(" ")[:2]
    assert series == "overhead,env=p4,session=20261113T043024Z"  # node_id가 없으면 node tag도 없음
    assert "node_busy_cores=2," in fields and "node_busy_cores=2i" not in fields
    assert "process_cores" not in fields and "process_rss_bytes" not in fields


def test_overhead_link_points():
    msg = example("overhead")
    msg["link"].append({"interface_name": "br-6afe1528cfa6", "role": "n2", "ingress": {}, "egress": {
        "sctp_packet_count": 12, "wire_byte_count": None}})
    msg["link"].append({"role": "f1"})  # interface_name 없는 칸은 건너뜀(스키마가 이미 거부)
    lines = [p.to_line_protocol() for p in overhead_link_points(msg, "p4")]
    assert lines == [
        "overhead_link,env=p4,iface=ens5,node=cu,role=f1,session=20261113T043024Z egress_sctp_packets=0i,"
        "egress_wire_bytes=0i,ingress_sctp_packets=0i,ingress_wire_bytes=0i,seq=37i,t_end_ms=1794544264000i "
        "1794544261000000000",
        "overhead_link,env=p4,iface=br-6afe1528cfa6,node=cu,role=n2,session=20261113T043024Z "
        "egress_sctp_packets=12i,seq=37i,t_end_ms=1794544264000i 1794544261000000000",
    ]
    assert overhead_link_points(example("alert"), "p4") == []


# --------------------------------------------------------------------------- Collector

class FakeWriter:
    def __init__(self):
        self.batches = []
        self.fail_with = None      # 다음 write에서 던질 WriteError
        self.bad_values = set()    # 이 node_busy_cores를 가진 overhead는 한 건씩 쓸 때도 거부

    def write(self, points):
        if self.fail_with:
            raise self.fail_with
        lines = [p.to_line_protocol() for p in points]
        if any(f"node_busy_cores={v}," in l for v in self.bad_values for l in lines):
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
    lines = [encode(overhead(link=True)).replace(",", ", "), encode(example("alert")), encode(example("kpm2"))]
    feed(c, *lines)
    assert w.points == []  # flush 전에는 쓰지 않음
    c.flush()
    c.close()
    assert len(w.points) == 4 and len(w.batches) == 1  # overhead는 링크 한 칸 = 점 하나 더
    assert c.env_raw_path("lab").read_text(encoding="utf-8").splitlines() == lines  # overhead도 환경별 녹화
    assert not c.rejected_path.exists()
    assert (c.stats.received, c.stats.stored, c.stats.rejected) == (3, 3, 0)


@pytest.mark.parametrize("raw, reason", [
    (b'{"type":"alert", broken', "JSON 파싱 실패"),
    (encode(overhead(busy=1)).replace('"node_busy_cores":1', '"node_busy_cores":NaN').encode(), "표준이 아닌 값 NaN"),
    (encode(overhead(ver=2)).encode(), "1 was expected"),
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
    assert w.points == [] and not c.env_raw_path("unknown").exists()
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
    feed(c, encode(overhead(0, busy=1.0)), encode(overhead(1, busy=666.0)), encode(example("alert")))
    c.flush()
    c.close()
    assert c.stats.stored == 2 and c.stats.rejected == 1
    [record] = read_jsonl(c.rejected_path)
    assert "InfluxDB 거부" in record["reasons"][0] and '"node_busy_cores":666.0' in record["raw"]


def test_pending_is_capped_while_influx_is_down(tmp_path):
    w = FakeWriter()
    w.fail_with = WriteError("down", retryable=True)
    c = make_collector(tmp_path, w, max_pending=5)
    feed(c, *[encode(overhead(i)) for i in range(8)])
    assert len(c.pending) == 5 and c.stats.dropped == 3
    c.close()
    assert len(c.env_raw_path("unknown").read_text(encoding="utf-8").splitlines()) == 8  # 버린 것도 녹화에는 있다


def test_dry_run_records_without_writer(tmp_path):
    c = make_collector(tmp_path, None)
    feed(c, encode(overhead()), "garbage")
    c.flush()
    c.close()
    assert (c.stats.stored, c.stats.rejected) == (1, 1)
    assert c.env_raw_path("unknown").exists() and c.rejected_path.exists()


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
