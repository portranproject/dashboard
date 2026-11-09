import copy
import json
import threading
from pathlib import Path

import pytest

from collector.collector import Collector, run
from collector.influx_writer import WriteError, to_point
from common.transport import FileTailSource, encode
from mock.generator import NS, generate, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = {}
for block in (REPO_ROOT / "schema" / "SCHEMA.md").read_text(encoding="utf-8").split("```json\n")[1:]:
    msg = json.loads(block.split("```")[0])
    EXAMPLES[msg["type"]] = msg


def example(msg_type, **changes):
    msg = copy.deepcopy(EXAMPLES[msg_type])
    msg.update(changes)
    return msg


# --------------------------------------------------------------------------- InfluxDB 변환 (CLAUDE.md 6절)

def test_metric_point():
    assert to_point(example("metric")).to_line_protocol() == (
        "metric,cell=1,kind=ekpm,name=rrc_msg_id,node=cu,src=ebpf,ue=0x4601 "
        'unit="code",value=0 1763280000123456789'
    )


def test_metric_without_labels_and_integer_value_is_float():
    msg = example("metric", value=3)
    msg.pop("labels")
    line = to_point(msg).to_line_protocol()
    assert line.startswith("metric,kind=ekpm,name=rrc_msg_id,node=cu,src=ebpf ")
    assert "value=3 " in line + " " and "value=3i" not in line  # 정수로 와도 float 필드


def test_detection_point():
    line = to_point(example("detection")).to_line_protocol()
    assert line.startswith(
        "detection,attack_type=RRC_SIGNALING_STORM,node=cu,rule_id=R-RRC-001,ruleset=full,severity=high "
    )
    assert line.endswith(" 1763280000523456789")
    fields = line.split(" ", 1)[1].rsplit(" ", 1)[0]
    assert 'event_id="det-000123"' in fields
    assert 'rule_version="1.0"' in fields
    assert "ts_first_evidence=1763280000123456789i" in fields
    assert "latency_ms=400" in fields
    assert 'cell="1"' in fields
    assert r'ue_list="[\"0x4601\",\"0x4602\"]"' in fields
    assert r'evidence_json="[{\"source\":\"ebpf\",\"metric\":\"count(rrc_msg_id=RRCSetupRequest)\"' in fields


def test_detection_without_cell_and_ue():
    msg = example("detection", target={"node": "du"})
    line = to_point(msg).to_line_protocol()
    assert ",node=du," in line
    assert "cell=" not in line
    assert 'ue_list="[]"' in line


def test_attack_run_point():
    assert to_point(example("attack_run")).to_line_protocol() == (
        'attack_run,scenario=RRC_SIGNALING_STORM params_json="{\\"rate\\":200,\\"fake_ue_count\\":50}",'
        'run_id="run-007",ts_end=1763280060000000000i 1763280000000000000'
    )


def test_overhead_point():
    assert to_point(example("overhead")).to_line_protocol() == (
        "overhead,ebpf_on=true,node=cu cpu_pct=23.4,mem_mb=512 1763280000000000000"
    )


# --------------------------------------------------------------------------- Collector

class FakeWriter:
    def __init__(self):
        self.batches = []
        self.fail_with = None      # 다음 write에서 던질 WriteError
        self.bad_values = set()    # 이 value를 가진 metric은 한 건씩 쓸 때도 거부

    def write(self, points):
        if self.fail_with:
            raise self.fail_with
        lines = [p.to_line_protocol() for p in points]
        if any(f"value={v} " in l for v in self.bad_values for l in lines):
            raise WriteError("HTTP 422: field type conflict", retryable=False)
        self.batches.append(lines)

    @property
    def points(self):
        return [l for b in self.batches for l in b]


def make_collector(tmp_path, writer, batch_size=500, max_pending=100_000):
    return Collector(writer, tmp_path / "rec", batch_size=batch_size, max_pending=max_pending)


def feed(collector, *lines, origin="test"):
    for line in lines:
        collector.handle(line if isinstance(line, bytes) else line.encode("utf-8"), origin)


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_valid_messages_are_recorded_verbatim_and_written(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    # 공백·키 순서가 다른 원본도 "받은 그대로" 녹화돼야 한다
    lines = [encode(example(t)) for t in ("metric", "detection", "attack_run", "overhead")]
    lines[0] = lines[0].replace(",", ", ")
    feed(c, *lines)
    assert w.points == []  # flush 전에는 쓰지 않음
    c.flush()
    c.close()
    assert len(w.points) == 4 and len(w.batches) == 1
    assert c.raw_path.read_text(encoding="utf-8").splitlines() == lines
    assert not c.rejected_path.exists()
    assert (c.stats.received, c.stats.stored, c.stats.rejected) == (4, 4, 0)


@pytest.mark.parametrize("raw, reason", [
    (b'{"type":"metric", broken', "JSON 파싱 실패"),
    (encode(example("metric", value=1)).replace('"value":1', '"value":NaN').encode(), "표준이 아닌 값 NaN"),
    (encode(example("metric", src="snmp")).encode(), "'snmp' is not one of"),
    (b'{"type":"metric","ts":"\xff\xfe"}', "UTF-8"),
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


def test_time_order_problems_are_warned_but_stored(tmp_path, caplog):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    d = example("detection")
    d["ts_first_evidence"] = d["ts_detected"] + 5_000_000
    r = example("attack_run")
    r["ts_start"], r["ts_end"] = r["ts_end"], r["ts_start"]
    feed(c, encode(d), encode(r))
    c.flush()
    assert c.stats.warnings == 2 and c.stats.stored == 2 and c.stats.rejected == 0
    assert "5.0ms" in caplog.text


def test_batches_are_split_by_batch_size(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w, batch_size=3)
    feed(c, *[encode(example("metric", ts=example("metric")["ts"] + i)) for i in range(7)])
    c.flush()
    assert [len(b) for b in w.batches] == [3, 3, 1]


def test_retryable_failure_keeps_messages_until_influx_recovers(tmp_path):
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    feed(c, encode(example("metric")), encode(example("overhead")))
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
    feed(c, encode(example("metric", value=1.0)), encode(example("metric", value=666.0)),
         encode(example("overhead")))
    c.flush()
    c.close()
    assert c.stats.stored == 2 and c.stats.rejected == 1
    [record] = read_jsonl(c.rejected_path)
    assert "InfluxDB 거부" in record["reasons"][0] and '"value":666.0' in record["raw"]


def test_pending_is_capped_while_influx_is_down(tmp_path):
    w = FakeWriter()
    w.fail_with = WriteError("down", retryable=True)
    c = make_collector(tmp_path, w, max_pending=5)
    feed(c, *[encode(example("metric", ts=example("metric")["ts"] + i)) for i in range(8)])
    assert len(c.pending) == 5 and c.stats.dropped == 3
    c.close()
    assert len(c.raw_path.read_text(encoding="utf-8").splitlines()) == 8  # 버린 것도 녹화에는 있다


def test_dry_run_records_without_writer(tmp_path):
    c = make_collector(tmp_path, None)
    feed(c, encode(example("metric")), "garbage")
    c.flush()
    c.close()
    assert (c.stats.stored, c.stats.rejected) == (1, 1)
    assert c.raw_path.exists() and c.rejected_path.exists()


def test_run_reads_mock_file_to_end_and_flushes(tmp_path):
    cfg = load_config()
    msgs = list(generate(cfg, "mixed", 120, seed=4, start_ns=1_795_136_400 * NS))
    src_path = tmp_path / "mock.jsonl"
    src_path.write_text("".join(encode(m) + "\n" for m in msgs) + "this is not json\n", encoding="utf-8")

    w = FakeWriter()
    c = make_collector(tmp_path, w, batch_size=500)
    run(c, [FileTailSource(src_path, follow=False)], flush_interval_s=1.0, stop=threading.Event())
    c.close()
    assert c.stats.stored == len(msgs) and c.stats.rejected == 1
    assert len(w.points) == len(msgs)
    assert c.raw_path.read_text(encoding="utf-8").splitlines() == [encode(m) for m in msgs]


def test_run_stops_on_stop_event_and_flushes(tmp_path):
    src_path = tmp_path / "live.jsonl"
    src_path.write_text(encode(example("metric")) + "\n", encoding="utf-8")
    w = FakeWriter()
    c = make_collector(tmp_path, w)
    stop = threading.Event()
    t = threading.Thread(target=run, args=(c, [FileTailSource(src_path, poll_s=0.05)], 60.0, stop))
    t.start()
    with src_path.open("a", encoding="utf-8") as fp:
        fp.write(encode(example("overhead")) + "\n")
    deadline = threading.Event()
    for _ in range(100):  # 두 줄 다 받을 때까지 최대 5초
        if c.stats.received == 2:
            break
        deadline.wait(0.05)
    stop.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert len(w.points) == 2  # flush 주기(60초)를 기다리지 않고 종료 시 flush
