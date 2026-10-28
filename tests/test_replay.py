import copy
import json
import socket
import time

import pytest

from common.schema import TIME_FIELDS, get_validator, message_time
from common.transport import encode
from mock.generator import NS, generate, load_config
from replay.replay import load, main, mark_replay, retime

START = 1_795_136_400 * NS  # 2026-11-20T10:00:00+09:00


@pytest.fixture(scope="module")
def msgs():
    return list(generate(load_config(), "mixed", 300, seed=2, start_ns=START))


def write_recording(path, messages, extra_lines=()):
    lines = [encode(m) for m in messages] + list(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_sorts_by_time_and_skips_bad_lines(tmp_path, msgs):
    shuffled = msgs[::-1]  # 도착 순서가 뒤섞인 녹화
    bad = ['{"type":"metric", broken', encode({"type": "metric", "ts": 1}), '{"type":"overhead","ts":NaN}', ""]
    loaded, skipped = load(write_recording(tmp_path / "raw.jsonl", shuffled, bad))
    assert skipped == 3
    assert [message_time(m) for m in loaded] == sorted(message_time(m) for m in msgs)
    assert len(loaded) == len(msgs)


def test_retime_moves_first_message_and_keeps_every_interval(msgs):
    target = START + 7 * 24 * 3600 * NS + 123
    moved, delta = retime(msgs, target)
    assert message_time(moved[0]) == target and delta == target - START
    for a, b in zip(msgs, moved):
        for name in TIME_FIELDS[a["type"]]:
            assert b[name] - a[name] == delta  # ts_first_evidence, ts_end도 같이 옮겨 간격 유지
        assert {k: v for k, v in a.items() if k not in TIME_FIELDS[a["type"]]} == \
               {k: v for k, v in b.items() if k not in TIME_FIELDS[b["type"]]}
    assert msgs[0]["ts"] == START  # 원본은 바뀌지 않는다


def test_retime_none_keeps_original_times(msgs):
    assert retime(msgs, None) == (msgs, 0)


def test_mark_replay_only_touches_attack_run_params(msgs):
    run = next(m for m in msgs if m["type"] == "attack_run")
    original = copy.deepcopy(run)
    marked = mark_replay(run, "raw-x.jsonl", 90 * NS)
    assert marked["params"]["replay"] == {"file": "raw-x.jsonl", "shift_s": 90.0}
    assert marked["params"]["generator"] == "mock"  # 원본 표시는 그대로
    assert run == original
    metric = next(m for m in msgs if m["type"] == "metric")
    assert mark_replay(metric, "raw-x.jsonl", 0) is metric
    assert get_validator().is_valid(marked)


def test_cli_replays_file_to_file_with_retime(tmp_path, msgs):
    src = write_recording(tmp_path / "raw.jsonl", msgs)
    out = tmp_path / "out.jsonl"
    rc = main([str(src), "--speed", "0", "--retime", "2026-12-04T14:00:00", "--out", f"file://{out}"])
    assert rc == 0
    sent = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(sent) == len(msgs)
    validator = get_validator()
    assert all(validator.is_valid(m) for m in sent)
    from datetime import datetime
    assert message_time(sent[0]) == round(datetime.fromisoformat("2026-12-04T14:00:00").timestamp()) * NS
    runs = [m for m in sent if m["type"] == "attack_run"]
    assert runs and all(r["params"]["replay"]["file"] == "raw.jsonl" for r in runs)


def test_cli_retime_now_puts_data_at_current_time(tmp_path, msgs):
    src = write_recording(tmp_path / "raw.jsonl", msgs[:50])
    out = tmp_path / "out.jsonl"
    before = time.time_ns()
    assert main([str(src), "--speed", "0", "--out", f"file://{out}"]) == 0  # --retime 기본 now
    first = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert before <= message_time(first) <= time.time_ns()


def test_cli_sends_over_udp(tmp_path, msgs):
    src = write_recording(tmp_path / "raw.jsonl", msgs[:200])
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(2)
    port = rx.getsockname()[1]
    try:
        assert main([str(src), "--speed", "0", "--retime", "none", "--out", f"udp://127.0.0.1:{port}"]) == 0
        got = [json.loads(rx.recv(65535)) for _ in range(200)]
    finally:
        rx.close()
    assert [message_time(m) for m in got] == [message_time(m) for m in msgs[:200]]


def test_cli_errors(tmp_path):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "nope.jsonl")])
    empty = tmp_path / "empty.jsonl"
    empty.write_text("not json\n", encoding="utf-8")
    assert main([str(empty), "--speed", "0", "--out", f"file://{tmp_path / 'o.jsonl'}"]) == 1
    with pytest.raises(SystemExit):
        main([str(empty), "--retime", "tomorrow"])
