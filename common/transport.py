"""JSON Lines 송수신 공통 코드.

주소 형식:
  udp://host:port   데이터그램 하나에 메시지 한 줄
  file://path       한 줄에 메시지 하나. 상대 경로는 실행 위치 기준 (file:///abs/path는 절대 경로)
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol, TypeVar

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


T = TypeVar("T")


def paced(items: Iterable[T], time_of: Callable[[T], int], base_ns: int, speed: float,
          before_sleep: Callable[[], None] | None = None) -> Iterator[T]:
    """items를 시각(time_of, ns)에 맞춰 내보낸다. base_ns가 지금이 되고, speed배로 빨리 간다 (0이면 기다리지 않음).
    기다리기 직전에 before_sleep을 부른다 (파일 출력 flush 등)."""
    wall0 = time.monotonic()
    for item in items:
        if speed > 0:
            delay = wall0 + (time_of(item) - base_ns) / 1e9 / speed - time.monotonic()
            if delay > 0:
                if before_sleep:
                    before_sleep()
                time.sleep(delay)
        yield item


# --------------------------------------------------------------------------- 수신

class Source(Protocol):
    def lines(self, stop: threading.Event) -> Iterator[tuple[bytes, str]]:
        """(한 줄, 출처) 를 낸다. stop이 설정되면 곧 끝난다."""
        ...

    def close(self) -> None: ...


class UdpSource:
    def __init__(self, host: str, port: int, rcvbuf_bytes: int | None = None, poll_s: float = 0.2):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if rcvbuf_bytes:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf_bytes)
        self.sock.bind((host, port))
        self.sock.settimeout(poll_s)
        self.address = "udp://{}:{}".format(*self.sock.getsockname())

    @property
    def rcvbuf_bytes(self) -> int:
        return self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)

    def lines(self, stop: threading.Event) -> Iterator[tuple[bytes, str]]:
        while not stop.is_set():
            try:
                data, (ip, port) = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                if stop.is_set():
                    return
                raise
            # 규칙은 데이터그램 하나에 한 줄이지만, 여러 줄이 붙어 와도 받아 준다.
            for line in data.split(b"\n"):
                if line.strip():
                    yield line.rstrip(b"\r"), f"udp:{ip}:{port}"

    def close(self) -> None:
        self.sock.close()


class FileTailSource:
    """tail -f처럼 파일에 추가되는 줄을 읽는다.

    from_start=False면 열 때 파일 끝부터 읽는다. follow=False면 파일 끝에서 멈춘다.
    파일이 아직 없으면 생길 때까지 기다리고, 잘리거나(truncate) 새 파일로 바뀌면(rotate) 처음부터 다시 읽는다.
    """

    def __init__(self, path: str | Path, from_start: bool = True, follow: bool = True, poll_s: float = 0.2):
        self.path = Path(path)
        self.from_start = from_start
        self.follow = follow
        self.poll_s = poll_s
        self.address = f"file://{self.path}"

    def lines(self, stop: threading.Event) -> Iterator[tuple[bytes, str]]:
        origin = f"file:{self.path}"
        fp = None
        buf = b""
        seek_end = not self.from_start
        try:
            while not stop.is_set():
                if fp is None:
                    try:
                        fp = self.path.open("rb")
                    except FileNotFoundError:
                        if not self.follow:
                            raise
                        stop.wait(self.poll_s)
                        continue
                    if seek_end:
                        fp.seek(0, os.SEEK_END)
                        seek_end = False  # 다시 열 때(rotate)는 처음부터
                    inode = os.fstat(fp.fileno()).st_ino

                chunk = fp.read(65536)
                if chunk:
                    buf += chunk
                    *complete, buf = buf.split(b"\n")
                    for line in complete:
                        if line.strip():
                            yield line.rstrip(b"\r"), origin
                    continue

                if not self.follow:
                    if buf.strip():  # 마지막 줄에 줄바꿈이 없는 경우
                        yield buf.rstrip(b"\r"), origin
                    return
                try:
                    st = os.stat(self.path)
                    replaced = st.st_ino != inode or st.st_size < fp.tell()
                except FileNotFoundError:
                    replaced = True
                if replaced:
                    fp.close()
                    fp, buf = None, b""
                    continue
                stop.wait(self.poll_s)
        finally:
            if fp is not None:
                fp.close()

    def close(self) -> None:
        pass


def open_source(address: str, *, from_start: bool = True, follow: bool = True,
                udp_rcvbuf_bytes: int | None = None, poll_s: float = 0.2) -> Source:
    scheme, rest = parse_address(address)
    if scheme == "udp":
        return UdpSource(*parse_udp_target(rest), rcvbuf_bytes=udp_rcvbuf_bytes, poll_s=poll_s)
    return FileTailSource(rest, from_start=from_start, follow=follow, poll_s=poll_s)
