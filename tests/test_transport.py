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
