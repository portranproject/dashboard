import json
import socket

import pytest

from common.transport import FileSink, encode, open_sink, parse_address, parse_udp_target


def test_encode_is_one_compact_line():
    line = encode({"type": "metric", "labels": {"ue": "0x4601"}, "text": "줄\n바꿈"})
    assert "\n" not in line
    assert line == '{"type":"metric","labels":{"ue":"0x4601"},"text":"줄\\n바꿈"}'


def test_encode_rejects_nan():
    with pytest.raises(ValueError):
        encode({"value": float("nan")})


@pytest.mark.parametrize("address, expected", [
    ("udp://127.0.0.1:9999", ("udp", "127.0.0.1:9999")),
    ("file://recordings/mock.jsonl", ("file", "recordings/mock.jsonl")),
    ("file:///tmp/a.jsonl", ("file", "/tmp/a.jsonl")),
])
def test_parse_address(address, expected):
    assert parse_address(address) == expected


@pytest.mark.parametrize("address", ["127.0.0.1:9999", "tcp://x:1", "udp://", "file://"])
def test_parse_address_rejects(address):
    with pytest.raises(ValueError):
        parse_address(address)


@pytest.mark.parametrize("target", ["localhost", "host:abc", ":9999"])
def test_parse_udp_target_rejects(target):
    with pytest.raises(ValueError):
        parse_udp_target(target)


def test_file_sink_overwrites_and_appends(tmp_path):
    path = tmp_path / "sub" / "out.jsonl"
    for append, expected in ((False, ["a"]), (False, ["b"]), (True, ["b", "c"])):
        sink = FileSink(path, append=append)
        sink.send(expected[-1])
        sink.close()
        assert path.read_text(encoding="utf-8").splitlines() == expected


def test_udp_sink_sends_one_datagram_per_message():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2)
    port = receiver.getsockname()[1]
    sink = open_sink(f"udp://127.0.0.1:{port}")
    try:
        for i in range(3):
            sink.send(encode({"i": i}))
        got = [json.loads(receiver.recv(65535)) for _ in range(3)]
    finally:
        sink.close()
        receiver.close()
    assert got == [{"i": 0}, {"i": 1}, {"i": 2}]


# --------------------------------------------------------------------------- 수신

import threading
import time

from common.transport import FileTailSource, UdpSource, open_source


class Collect:
    """source.lines()를 별도 스레드에서 돌려 받은 줄을 모은다."""

    def __init__(self, source):
        self.source, self.got, self.stop = source, [], threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        for line, origin in self.source.lines(self.stop):
            self.got.append((line, origin))

    def wait_for(self, n, timeout=5):
        end = time.monotonic() + timeout
        while len(self.got) < n and time.monotonic() < end:
            time.sleep(0.02)
        return [line for line, _ in self.got]

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        self.source.close()


def test_file_tail_once_reads_all_including_last_line_without_newline(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_bytes(b'{"a":1}\n\n{"b":2}\r\n{"c":3}')
    lines = [line for line, _ in FileTailSource(path, follow=False).lines(threading.Event())]
    assert lines == [b'{"a":1}', b'{"b":2}', b'{"c":3}']


def test_file_tail_follows_appends_and_waits_for_partial_lines(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_bytes(b"1\n")
    c = Collect(FileTailSource(path, poll_s=0.02))
    try:
        assert c.wait_for(1) == [b"1"]
        with path.open("ab") as fp:
            fp.write(b"2\n3")       # 3은 아직 줄이 안 끝남
            fp.flush()
            assert c.wait_for(2) == [b"1", b"2"]
            time.sleep(0.1)
            assert len(c.got) == 2
            fp.write(b"3\n")
        assert c.wait_for(3) == [b"1", b"2", b"33"]
    finally:
        c.close()


def test_file_tail_from_end_skips_existing_lines(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_bytes(b"old\n")
    c = Collect(FileTailSource(path, from_start=False, poll_s=0.02))
    try:
        time.sleep(0.1)
        with path.open("ab") as fp:
            fp.write(b"new\n")
        assert c.wait_for(1) == [b"new"]
    finally:
        c.close()


def test_file_tail_waits_for_file_and_handles_truncation(tmp_path):
    path = tmp_path / "later.jsonl"
    c = Collect(FileTailSource(path, poll_s=0.02))
    try:
        time.sleep(0.1)
        path.write_bytes(b"first-long-line\n")
        assert c.wait_for(1) == [b"first-long-line"]
        path.write_bytes(b"x\n")  # 덮어쓰기(크기가 줄어듦) → 처음부터 다시
        assert c.wait_for(2) == [b"first-long-line", b"x"]
    finally:
        c.close()


def test_udp_source_receives_and_splits_lines():
    src = open_source("udp://127.0.0.1:0", poll_s=0.05)
    assert isinstance(src, UdpSource)
    port = int(src.address.rsplit(":", 1)[1])
    c = Collect(src)
    try:
        sink = open_sink(f"udp://127.0.0.1:{port}")
        sink.send('{"a":1}')
        sink.send('{"b":2}\n{"c":3}')
        sink.close()
        assert c.wait_for(3) == [b'{"a":1}', b'{"b":2}', b'{"c":3}']
        assert c.got[0][1].startswith("udp:127.0.0.1:")
    finally:
        c.close()


def test_paced_waits_for_message_times_and_speed():
    from common.transport import paced

    items = [0, 50_000_000, 100_000_000]  # 0, 0.05, 0.1초
    t0 = time.monotonic()
    assert list(paced(items, lambda x: x, 0, speed=1)) == items
    assert time.monotonic() - t0 >= 0.09
    t0 = time.monotonic()
    list(paced(items, lambda x: x, 0, speed=10))
    assert time.monotonic() - t0 < 0.05
    flushes = []
    t0 = time.monotonic()
    list(paced(items, lambda x: x, 0, speed=0, before_sleep=lambda: flushes.append(1)))
    assert time.monotonic() - t0 < 0.05 and flushes == []
