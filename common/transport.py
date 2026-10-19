"""JSON Lines 송수신 공통 코드.

주소 형식:
  udp://host:port   데이터그램 하나에 메시지 한 줄
  file://path       한 줄에 메시지 하나. 상대 경로는 실행 위치 기준 (file:///abs/path는 절대 경로)
"""
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Protocol

# IPv4 UDP 데이터그램 최대 페이로드
MAX_UDP_PAYLOAD = 65507


def encode(msg: Any) -> str:
    """메시지를 줄바꿈 없는 JSON 한 줄로. NaN/Infinity는 JSON 표준이 아니므로 거부한다."""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def parse_address(address: str) -> tuple[str, str]:
    scheme, sep, rest = address.partition("://")
    if not sep or scheme not in ("udp", "file") or not rest:
        raise ValueError(f"주소 형식이 잘못됐습니다: {address!r} (udp://host:port 또는 file://path)")
    return scheme, rest


def parse_udp_target(rest: str) -> tuple[str, int]:
    host, sep, port = rest.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ValueError(f"UDP 주소는 host:port 형식이어야 합니다: {rest!r}")
    return host, int(port)


class Sink(Protocol):
    def send(self, line: str) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


class UdpSink:
    def __init__(self, host: str, port: int):
        self.target = (host, port)
        # connect()하지 않은 소켓은 수신 측이 꺼져 있어도 에러 없이 보낸다 (UDP 특성상 유실).
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, line: str) -> None:
        data = line.encode("utf-8")
        if len(data) > MAX_UDP_PAYLOAD:
            raise ValueError(f"메시지가 UDP 최대 크기({MAX_UDP_PAYLOAD}B)를 넘습니다: {len(data)}B")
        self.sock.sendto(data, self.target)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.sock.close()


class FileSink:
    def __init__(self, path: str | Path, append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = self.path.open("a" if append else "w", encoding="utf-8", newline="\n")

    def send(self, line: str) -> None:
        self.fp.write(line + "\n")

    def flush(self) -> None:
        self.fp.flush()

    def close(self) -> None:
        self.fp.close()


def open_sink(address: str, append: bool = False) -> Sink:
    scheme, rest = parse_address(address)
    if scheme == "udp":
        return UdpSink(*parse_udp_target(rest))
    return FileSink(rest, append=append)
