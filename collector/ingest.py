"""탐지 엔진 전송기의 HTTP 수집 엔드포인트 `POST /ingest`와 중복 제거 키.

약속은 reference/detection/27_ §3 (11/02 합의, 대시보드 2차 답변서 D1~D3):
  - 본문: JSON Lines 여러 줄(`Content-Type: application/x-ndjson`), 요청 하나 최대 COLLECTOR_HTTP_MAX_BYTES
  - 헤더 `X-Env`: 환경(p4·lab·replay-kpm-only 등). 없으면 `unknown`. 모든 중복 키 앞에 붙인다
  - 응답: 원본 녹화와 InfluxDB 저장이 끝난 뒤에 답한다
      200 {"accepted", "rejected", "duplicates"}  줄 단위 오류는 rejected로 세고 나머지는 저장
      400 본문 전체를 읽을 수 없음(UTF-8 아님, 길이 불일치, X-Env 형식 오류) — 전송기는 다시 보내지 않음
      413 요청이 상한을 넘음 — 전송기가 반으로 나눠 다시 보냄
      503 InfluxDB 일시 장애·처리 지연 — 전송기가 간격을 늘려 다시 보냄
  - TLS는 앞단(Caddy)이 맡는다. 이 서버는 평문 HTTP로 서버 안(127.0.0.1)에서만 받는다.

HTTP 처리 스레드는 요청을 collector 메인 루프의 큐에 넣고 결과를 기다리기만 한다.
그래서 Collector의 상태(중복 키, 녹화 파일, 세션 표)는 메인 루프 한 스레드만 만진다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import re
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Hashable, Iterator

log = logging.getLogger("collector.ingest")

INGEST_PATH = "/ingest"
HEALTH_PATH = "/healthz"
DEFAULT_ENV = "unknown"
# 환경 값은 녹화 파일 이름에도 들어가므로 글자를 제한한다
ENV_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def parse_env(value: str | None) -> str | None:
    """X-Env 헤더 값. 없거나 비면 unknown, 형식이 틀리면 None."""
    if value is None or not value.strip():
        return DEFAULT_ENV
    value = value.strip()
    return value if ENV_PATTERN.match(value) else None


def dedup_key(msg: dict, env: str) -> bytes | None:
    """다시 보낸 줄을 거르는 키 (27_ §3 '중복 제거 키', 모두 앞에 환경). 옛 메시지는 None(거르지 않음).
    메모리를 아끼려고 16바이트 해시로 줄인다."""
    t = msg["type"]
    if t == "alert":
        parts = [msg["alert_id"], msg["event"], msg["t"]]
    elif t == "evidence":
        parts = [msg["alert_id"], msg["phase"], msg["seq"], msg.get("ue")]
    elif t == "gap":
        parts = [msg["alert_id"], msg["t_from"]]
    elif t == "kpm2":
        parts = [msg["session"], msg["cell_id"], msg["agg_ms"], msg["t_start_ms"]]
    elif t in ("hello", "f1_evt"):
        parts = [msg["session"], msg["seq"]]
    else:
        return None
    text = json.dumps([env, t, *parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()


class BoundedDict(OrderedDict):
    """가장 오래 쓰지 않은 항목부터 버리는 크기 제한 dict. 중복 키·세션 표가 끝없이 커지지 않게 한다."""

    def __init__(self, max_items: int):
        super().__init__()
        self.max_items = max_items

    def put(self, key: Hashable, value: Any) -> None:
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.max_items:
            self.popitem(last=False)


class IngestRequest:
    """HTTP 처리 스레드 → collector 메인 루프로 넘기는 요청 하나. 메인 루프가 complete()로 답을 채운다."""

    def __init__(self, body: bytes, env: str, origin: str):
        self.body = body
        self.env = env
        self.origin = origin
        self.status: int | None = None
        self.payload: dict | None = None
        self._done = threading.Event()

    def complete(self, status: int, payload: dict) -> None:
        self.status, self.payload = status, payload
        self._done.set()

    def wait(self, timeout_s: float) -> bool:
        return self._done.wait(timeout_s)


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"
    protocol_version = "HTTP/1.1"  # 전송기가 연결을 다시 쓸 수 있게
    server_version = "portran-collector"

    def setup(self) -> None:
        self.timeout = self.server.socket_timeout_s  # 느리게 보내는 연결이 처리 스레드를 오래 잡지 않게
        super().setup()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 (BaseHTTPRequestHandler 시그니처)
        log.debug("%s %s", self.address_string(), format % args)

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == HEALTH_PATH:
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"error": f"없는 경로: {self.path}"})

    def do_POST(self) -> None:
        if self.path != INGEST_PATH:
            self.close_connection = True  # 본문을 읽지 않았으므로 연결을 다시 쓰지 않는다
            self._reply(404, {"error": f"없는 경로: {self.path} (POST {INGEST_PATH})"})
            return
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self.close_connection = True
            self._reply(411, {"error": "Content-Length가 필요합니다"})
            return
        try:
            length = int(length_header)
            if length < 0:
                raise ValueError
        except ValueError:
            self.close_connection = True
            self._reply(400, {"error": f"Content-Length가 잘못됐습니다: {length_header!r}"})
            return
        if length > self.server.max_bytes:
            self.close_connection = True
            self._reply(413, {"error": f"요청이 상한 {self.server.max_bytes}B를 넘습니다: {length}B"})
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self.close_connection = True
            self._reply(400, {"error": f"본문이 Content-Length보다 짧습니다: {len(body)}/{length}B"})
            return
        env = parse_env(self.headers.get("X-Env"))
        if env is None:
            self._reply(400, {"error": "X-Env는 영숫자로 시작하고 영숫자·._-만 쓴 64자 이하여야 합니다"})
            return

        request = IngestRequest(body, env, origin=f"http {self.client_address[0]} X-Env={env}")
        if self.server.stopping.is_set():
            self._reply(503, {"error": "collector가 종료 중입니다"})
            return
        self.server.requests.put(request)
        if not request.wait(self.server.request_timeout_s):
            self._reply(503, {"error": "처리가 늦어지고 있습니다. 잠시 뒤 다시 보내세요"})
            return
        self._reply(request.status, request.payload)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, max_bytes: int, request_timeout_s: float, socket_timeout_s: float):
        super().__init__(address, _Handler)
        self.max_bytes = max_bytes
        self.request_timeout_s = request_timeout_s
        self.socket_timeout_s = socket_timeout_s
        self.requests: queue.Queue[IngestRequest] = queue.Queue()
        self.stopping = threading.Event()


class IngestSource:
    """collector 입력 하나(`--in http://host:port`). lines()가 (bytes, origin) 대신 IngestRequest를 내놓는다."""

    def __init__(self, host: str, port: int, max_bytes: int, request_timeout_s: float = 30.0,
                 socket_timeout_s: float = 30.0, poll_s: float = 0.2):
        self.server = _Server((host, port), max_bytes, request_timeout_s, socket_timeout_s)
        self.poll_s = poll_s
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}{INGEST_PATH}"

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def lines(self, stop: threading.Event) -> Iterator[IngestRequest]:
        self._thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": self.poll_s},
                                        daemon=True)
        self._thread.start()
        while not stop.is_set():
            try:
                yield self.server.requests.get(timeout=self.poll_s)
            except queue.Empty:
                continue

    def close(self) -> None:
        self.server.stopping.set()
        if self._thread is not None:
            self.server.shutdown()
        self.server.server_close()
        # 메인 루프로 넘어가지 못한 요청은 다시 보내도록 503으로 답한다
        while True:
            try:
                self.server.requests.get_nowait().complete(503, {"error": "collector가 종료 중입니다"})
            except queue.Empty:
                break
