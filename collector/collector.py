"""collector: 수신 → 스키마 검증 → raw 녹화 → InfluxDB 배치 쓰기.

    python -m collector.collector                                          # UDP (.env의 COLLECTOR_UDP_HOST:PORT)
    python -m collector.collector --in http://127.0.0.1:8088               # 탐지 엔진 전송기 수집 (POST /ingest)
    python -m collector.collector --in file://recordings/mock.jsonl --once # 파일을 끝까지 읽고 종료
    python -m collector.collector --in udp://0.0.0.0:9999 --in file://agent.jsonl   # 여러 입력 동시에
    python -m collector.collector --dry-run                                # InfluxDB 없이 검증·녹화만

검증에 실패한 메시지는 버리지 않고 recordings/rejected.jsonl에 사유와 함께 남긴다.
검증을 통과한 메시지는 받은 그대로 녹화한다(replay용).
  - 옛 메시지(metric·detection·attack_run·overhead): recordings/raw-<날짜시각>.jsonl
  - 탐지 엔진 레코드(alert·evidence·gap·kpm2·hello·f1_evt): recordings/raw-<날짜시각>-<환경>.jsonl
    환경은 /ingest의 X-Env 헤더, UDP·파일 입력은 --env. 다시 보낸 줄(같은 중복 키)은 한 번만 저장한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from common.config import env_int, influx_settings, load_env
from common.schema import validation_errors
from common.transport import UdpSource, open_source, parse_address

from .influx_writer import NEW_RECORD_TYPES, InfluxWriter, WriteError, session_point, to_point
from .ingest import DEFAULT_ENV, BoundedDict, IngestRequest, IngestSource, dedup_key, parse_env

log = logging.getLogger("collector")

# 시각 앞뒤가 뒤바뀐 메시지를 로그에 자세히 남기는 최대 건수 (이후로는 건수만 센다)
MAX_WARNING_DETAILS = 5
# 경보 → 세션 표와 '세션을 기다리는 경보' 표의 최대 경보 수 (가장 오래 안 쓴 것부터 버림)
MAX_TRACKED_ALERTS = 10_000


class Writer(Protocol):
    def write(self, points: list) -> None: ...


def _reject_constant(name: str):
    raise ValueError(f"JSON 표준이 아닌 값 {name}")


@dataclass
class Stats:
    received: int = 0
    stored: int = 0
    rejected: int = 0
    dropped: int = 0
    warnings: int = 0
    duplicates: int = 0

    def minus(self, other: "Stats") -> "Stats":
        return Stats(**{k: getattr(self, k) - getattr(other, k) for k in self.__dataclass_fields__})


@dataclass
class _Pending:
    line: str
    origin: str
    points: list


@dataclass
class _Accepted:
    """/ingest 요청 안에서 검증·중복 검사를 통과한 줄. 저장에 성공해야 녹화·중복 키에 반영한다."""
    line: str
    msg: dict
    key: bytes | None
    points: list


@dataclass
class _Staged:
    """세션 표 변경 중 저장에 성공한 뒤에만 반영할 것."""
    awaiting: list[tuple[tuple[str, str], dict]] = field(default_factory=list)  # 세션을 모르고 쓴 alert·gap
    resolved: set[tuple[str, str]] = field(default_factory=set)                # 세션을 채워 넣은 (env, alert_id)


@dataclass
class Collector:
    writer: Writer | None  # None이면 dry-run (InfluxDB에 쓰지 않음)
    recordings_dir: Path
    batch_size: int
    max_pending: int
    default_env: str = DEFAULT_ENV  # UDP·파일 입력으로 온 탐지 엔진 레코드의 환경
    dedup_max_keys: int = 200_000
    started_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.recordings_dir = Path(self.recordings_dir)
        self.raw_path = self.recordings_dir / f"raw-{self.started_at:%Y%m%d-%H%M%S}.jsonl"
        self.rejected_path = self.recordings_dir / "rejected.jsonl"
        self.stats = Stats()
        self._last_logged = Stats()
        self.pending: list[_Pending] = []
        self.in_outage = False
        self._raw_fp = None
        self._rejected_fp = None
        self._env_fps: dict[str, object] = {}
        # 다시 보낸 줄을 거르는 키 (27_ §3). 메모리에만 있어 재시작하면 비지만,
        # 같은 줄은 InfluxDB에서 같은 series·시각에 덮어써지므로 저장 결과는 같다.
        self.seen = BoundedDict(self.dedup_max_keys)
        # alert에는 session이 없다. 같은 alert_id의 첫 evidence의 raw.session이 그 경보의 세션이다(27_ §7).
        self.alert_sessions = BoundedDict(MAX_TRACKED_ALERTS)    # (env, alert_id) → session
        self.awaiting_session = BoundedDict(MAX_TRACKED_ALERTS)  # (env, alert_id) → 세션 없이 쓴 alert·gap 목록

    def env_raw_path(self, env: str) -> Path:
        return self.recordings_dir / f"raw-{self.started_at:%Y%m%d-%H%M%S}-{env}.jsonl"

    # ------------------------------------------------------------------ 메시지 처리 (UDP·파일)

    def _parse(self, data: bytes) -> tuple[str, dict | None, list[str]]:
        try:
            line = data.decode("utf-8")
        except UnicodeDecodeError as e:
            return data.decode("utf-8", errors="replace"), None, [f"UTF-8 아님: {e}"]
        try:
            msg = json.loads(line, parse_constant=_reject_constant)
        except ValueError as e:
            return line, None, [f"JSON 파싱 실패: {e}"]
        errors = validation_errors(msg)
        return line, (None if errors else msg), errors

    def handle(self, data: bytes, origin: str, env: str | None = None) -> None:
        self.stats.received += 1
        line, msg, errors = self._parse(data)
        if msg is None:
            self._reject(line, origin, errors)
            return
        env = env or self.default_env
        key = dedup_key(msg, env)
        if key is not None and key in self.seen:
            self.stats.duplicates += 1
            return

        staged = _Staged()
        points = self._points_for(msg, env, time.time_ns(), staged)
        self._apply(staged)
        self._check_times(msg, origin)
        self._write_raw(line, msg, env)
        if key is not None:
            self.seen.put(key, None)
        if self.writer is None:
            self.stats.stored += 1
            return
        self.pending.append(_Pending(line, origin, points))
        overflow = len(self.pending) - self.max_pending
        if overflow > 0:
            # raw 녹화에는 남아 있으므로 InfluxDB 복구 후 replay로 다시 넣을 수 있다.
            del self.pending[:overflow]
            self.stats.dropped += overflow

    # ------------------------------------------------------------------ /ingest 요청

    def handle_request(self, body: bytes, env: str, origin: str) -> tuple[int, dict]:
        """탐지 엔진 전송기의 요청 하나를 처리하고 (HTTP 상태, 응답 본문)을 돌려준다 (collector/ingest.py 머리말).
        InfluxDB에 쓰기를 마친 뒤에 녹화·중복 키·통계에 반영한다. 일시 장애면 아무것도 반영하지 않고 503
        (전송기가 같은 묶음을 다시 보낸다)."""
        try:
            body.decode("utf-8")
        except UnicodeDecodeError as e:
            return 400, {"error": f"본문이 UTF-8이 아닙니다: {e}"}
        received_ns = time.time_ns()
        parsed = [self._parse(raw) for raw in body.split(b"\n") if raw.strip()]

        # 경보 레코드 순서는 raise → 그 경보의 pre 증거라, 같은 요청의 증거에서 세션을 먼저 알아 둔다
        for _, msg, _ in parsed:
            if msg is not None and msg["type"] == "evidence":
                self._learn_session(msg, env)

        staged = _Staged()
        accepted: list[_Accepted] = []
        rejected: list[tuple[str, list[str]]] = []
        duplicates = 0
        batch_keys: set[bytes] = set()
        for line, msg, errors in parsed:
            if msg is None:
                rejected.append((line, errors))
                continue
            key = dedup_key(msg, env)
            if key is not None:
                if key in self.seen or key in batch_keys:
                    duplicates += 1
                    continue
                batch_keys.add(key)
            accepted.append(_Accepted(line, msg, key, self._points_for(msg, env, received_ns, staged)))

        failed: list[tuple[_Accepted, str]] = []
        if self.writer is not None and accepted:
            try:
                failed = self._write_now(accepted)
            except WriteError as e:
                if not self.in_outage:
                    log.error("InfluxDB 쓰기 실패, /ingest 요청에 503으로 답합니다(전송기가 다시 보냄): %s", e)
                self.in_outage = True
                return 503, {"error": f"저장소 일시 장애: {e}"}
            if self.in_outage:
                log.info("InfluxDB 쓰기 복구")
                self.in_outage = False

        self.stats.received += len(parsed)
        self.stats.duplicates += duplicates
        for line, errors in rejected:
            self._reject(line, origin, errors)
        failed_ids = {id(a) for a, _ in failed}
        for a, error in failed:
            self._reject(a.line, origin, [f"InfluxDB 거부: {error}"])
        for a in accepted:
            if id(a) in failed_ids:
                continue
            self._check_times(a.msg, origin)
            self._write_raw(a.line, a.msg, env)
            if a.key is not None:
                self.seen.put(a.key, None)
            self.stats.stored += 1
        failed_msgs = {id(a.msg) for a, _ in failed}
        staged.awaiting = [(k, m) for k, m in staged.awaiting if id(m) not in failed_msgs]
        self._apply(staged)
        self._flush_files()
        return 200, {"accepted": len(accepted) - len(failed), "rejected": len(rejected) + len(failed),
                     "duplicates": duplicates}

    def _write_now(self, accepted: list[_Accepted]) -> list[tuple[_Accepted, str]]:
        """요청의 점을 바로 쓴다. 데이터 문제(4xx)로 거부된 줄만 돌려주고, 일시 장애면 WriteError를 그대로 던진다."""
        failed = []
        for i in range(0, len(accepted), self.batch_size):
            chunk = accepted[i:i + self.batch_size]
            try:
                self.writer.write([p for a in chunk for p in a.points])
            except WriteError as e:
                if e.retryable:
                    raise
                for a in chunk:
                    try:
                        self.writer.write(a.points)
                    except WriteError as one:
                        if one.retryable:
                            raise
                        failed.append((a, str(one)))
        return failed

    # ------------------------------------------------------------------ 세션 (alert·gap ← evidence.raw.session)

    def _learn_session(self, msg: dict, env: str) -> str | None:
        session = msg["raw"].get("session")
        if not isinstance(session, str) or not session:
            return None
        key = (env, msg["alert_id"])
        if key not in self.alert_sessions:
            self.alert_sessions.put(key, session)
        return self.alert_sessions[key]

    def _points_for(self, msg: dict, env: str, received_ns: int, staged: _Staged) -> list:
        t = msg["type"]
        if t == "evidence":
            points = [to_point(msg, env, received_ns=received_ns)]
            session = self._learn_session(msg, env)
            key = (env, msg["alert_id"])
            if session and key in self.awaiting_session and key not in staged.resolved:
                # 세션을 모른 채 먼저 쓴 alert·gap 점에 session 필드를 더한다
                points += [session_point(m, env, session) for m in self.awaiting_session[key]]
                staged.resolved.add(key)
            return points
        if t in ("alert", "gap"):
            key = (env, msg["alert_id"])
            session = self.alert_sessions.get(key)
            if session is None:
                staged.awaiting.append((key, msg))
            return [to_point(msg, env, session=session)]
        return [to_point(msg, env, received_ns=received_ns)]

    def _apply(self, staged: _Staged) -> None:
        for key in staged.resolved:
            self.awaiting_session.pop(key, None)
        for key, msg in staged.awaiting:
            if key in self.awaiting_session:
                self.awaiting_session[key].append(msg)
            else:
                self.awaiting_session.put(key, [msg])

    # ------------------------------------------------------------------ 검사·녹화

    def _check_times(self, msg: dict, origin: str) -> None:
        """스키마로 표현할 수 없는 시각 순서 검사. 노드 간 시계가 어긋나도 데이터를 잃지 않도록 거부하지 않고 경고만 한다."""
        t = msg["type"]
        if t == "detection" and msg["ts_first_evidence"] > msg["ts_detected"]:
            problem = f"ts_first_evidence가 ts_detected보다 {(msg['ts_first_evidence'] - msg['ts_detected']) / 1e6:.1f}ms 늦음"
        elif t == "attack_run" and msg["ts_start"] > msg["ts_end"]:
            problem = "ts_start가 ts_end보다 늦음"
        elif t == "gap" and msg["t_from"] > msg["t_to"]:
            problem = "t_from이 t_to보다 늦음"
        elif t == "kpm2" and msg["t_start_ms"] >= msg["t_end_ms"]:
            problem = "t_start_ms가 t_end_ms보다 늦거나 같음"
        else:
            return
        self.stats.warnings += 1
        if self.stats.warnings <= MAX_WARNING_DETAILS:
            ident = msg.get("event_id") or msg.get("run_id") or msg.get("alert_id") or msg.get("session")
            log.warning("시각 순서 경고 (%s, %s): %s — 저장은 함", origin, ident, problem)

    def _write_raw(self, line: str, msg: dict, env: str) -> None:
        if msg["type"] in NEW_RECORD_TYPES:
            fp = self._env_fps.get(env)
            if fp is None:
                self.recordings_dir.mkdir(parents=True, exist_ok=True)
                fp = self._env_fps[env] = self.env_raw_path(env).open("a", encoding="utf-8", newline="\n")
        else:
            if self._raw_fp is None:
                self.recordings_dir.mkdir(parents=True, exist_ok=True)
                self._raw_fp = self.raw_path.open("a", encoding="utf-8", newline="\n")
            fp = self._raw_fp
        fp.write(line + "\n")

    def _reject(self, line: str, origin: str, reasons: list[str]) -> None:
        self.stats.rejected += 1
        if self._rejected_fp is None:
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self._rejected_fp = self.rejected_path.open("a", encoding="utf-8", newline="\n")
        now = datetime.now()
        record = {"received_at": now.isoformat(timespec="milliseconds"), "source": origin,
                  "reasons": reasons, "raw": line}
        self._rejected_fp.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _files(self) -> list:
        return [fp for fp in (self._raw_fp, self._rejected_fp, *self._env_fps.values()) if fp is not None]

    def _flush_files(self) -> None:
        for fp in self._files():
            fp.flush()

    # ------------------------------------------------------------------ InfluxDB

    def flush(self) -> None:
        self._flush_files()
        while self.pending:
            chunk = self.pending[: self.batch_size]
            try:
                self.writer.write([p for entry in chunk for p in entry.points])
            except WriteError as e:
                if e.retryable:
                    if not self.in_outage:
                        log.error("InfluxDB 쓰기 실패, %d건 보관하고 다시 시도합니다: %s", len(self.pending), e)
                    self.in_outage = True
                    return
                self._write_one_by_one(chunk)
            else:
                self.stats.stored += len(chunk)
            del self.pending[: len(chunk)]
        if self.in_outage:
            log.info("InfluxDB 쓰기 복구")
            self.in_outage = False

    def _write_one_by_one(self, chunk: list[_Pending]) -> None:
        """배치가 데이터 문제(4xx)로 거부되면 한 건씩 써서 문제 메시지만 거부 로그로 보낸다."""
        for p in chunk:
            try:
                self.writer.write(p.points)
            except WriteError as e:
                # 한 건씩 쓰는 도중의 일시 장애는 드물어서, 그 건도 거부 로그에 남기고 넘어간다.
                self._reject(p.line, p.origin, [f"InfluxDB 거부: {e}"])
            else:
                self.stats.stored += 1

    # ------------------------------------------------------------------ 로그

    def log_stats(self, final: bool = False) -> None:
        d = self.stats.minus(self._last_logged)
        self._last_logged = Stats(**vars(self.stats))
        s = self.stats
        stored = "통과" if self.writer is None else "저장"
        extra = ""
        if s.duplicates:
            extra += f" 중복 {s.duplicates:,}"
        if s.warnings:
            extra += f" 경고 {s.warnings:,}"
        if s.dropped:
            extra += f" 버림 {s.dropped:,}"
        if self.in_outage:
            extra += " (InfluxDB 장애)"
        if final:
            log.info("종료 — 누적 수신 %s %s %s 거부 %s | 못 쓴 것 %d%s",
                     f"{s.received:,}", stored, f"{s.stored:,}", f"{s.rejected:,}", len(self.pending), extra)
        else:
            log.info("수신 %d %s %d 거부 %d | 누적 수신 %s %s %s 거부 %s | 대기 %d%s",
                     d.received, stored, d.stored, d.rejected,
                     f"{s.received:,}", stored, f"{s.stored:,}", f"{s.rejected:,}", len(self.pending), extra)

    def close(self) -> None:
        for fp in self._files():
            fp.close()


_DONE = object()


def _dispatch(collector: Collector, item) -> None:
    if isinstance(item, IngestRequest):
        try:
            status, payload = collector.handle_request(item.body, item.env, item.origin)
        except Exception as e:  # 처리 스레드가 답을 못 받고 멈춰 있지 않도록 어떤 경우에도 답한다
            log.exception("/ingest 요청 처리 중 오류 (%s)", item.origin)
            status, payload = 503, {"error": f"collector 내부 오류: {type(e).__name__}"}
        item.complete(status, payload)
    else:
        collector.handle(*item)


def run(collector: Collector, sources: list, flush_interval_s: float, stop: threading.Event,
        log_interval_s: float = 1.0) -> None:
    """입력마다 스레드가 줄(HTTP 입력은 요청)을 읽어 큐에 넣고, 이 함수가 처리·배치 쓰기·로그를 맡는다.
    모든 입력이 끝나거나(파일 --once) stop이 설정되면 남은 것을 처리하고 flush한 뒤 돌아온다."""
    q: queue.Queue = queue.Queue()

    def pump(src) -> None:
        try:
            for item in src.lines(stop):
                q.put(item)
        except Exception as e:
            log.error("입력 %s 오류: %s", getattr(src, "address", src), e)
        finally:
            q.put(_DONE)

    for src in sources:
        threading.Thread(target=pump, args=(src,), daemon=True).start()

    active = len(sources)
    next_flush = time.monotonic() + flush_interval_s
    next_log = time.monotonic() + log_interval_s
    try:
        while active:
            timeout = max(0.0, min(next_flush, next_log) - time.monotonic())
            try:
                item = q.get(timeout=timeout)
            except queue.Empty:
                item = None
            if item is _DONE:
                active -= 1
            elif item is not None:
                _dispatch(collector, item)

            now = time.monotonic()
            # 장애 중에는 배치가 차도 바로 다시 쓰지 않고 flush 주기에 맞춰 재시도한다.
            batch_full = len(collector.pending) >= collector.batch_size and not collector.in_outage
            if batch_full or now >= next_flush:
                collector.flush()
                next_flush = now + flush_interval_s
            if now >= next_log:
                collector.log_stats()
                next_log = max(next_log + log_interval_s, now)
    finally:
        stop.set()
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item is not _DONE:
                _dispatch(collector, item)
        collector.flush()
        for src in sources:
            src.close()


def parse_http_address(rest: str) -> tuple[str, int]:
    host, sep, port = rest.rstrip("/").rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ValueError(f"HTTP 입력은 http://host:port 형식이어야 합니다: http://{rest}")
    return host, int(port)


def main(argv: list[str] | None = None) -> int:
    load_env()
    default_in = f"udp://{os.environ['COLLECTOR_UDP_HOST']}:{os.environ['COLLECTOR_UDP_PORT']}"
    parser = argparse.ArgumentParser(prog="python -m collector.collector", description=__doc__.split("\n")[0])
    parser.add_argument("--in", dest="inputs", action="append", metavar="ADDRESS",
                        help=f"udp://host:port, file://path, http://host:port(POST /ingest). "
                             f"여러 번 줄 수 있음 (기본 {default_in})")
    parser.add_argument("--once", action="store_true", help="파일 입력을 끝까지 읽고 종료 (UDP·HTTP 입력과 같이 못 씀)")
    parser.add_argument("--from-end", action="store_true", help="파일 입력을 처음이 아니라 현재 끝부터 읽음")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"UDP·파일로 받은 탐지 엔진 레코드의 환경 (HTTP는 X-Env 헤더, 기본 {DEFAULT_ENV})")
    parser.add_argument("--dry-run", action="store_true", help="InfluxDB에 쓰지 않고 검증·녹화만")
    parser.add_argument("--recordings", default=os.environ["RECORDINGS_DIR"], help="raw 녹화·거부 로그 폴더")
    args = parser.parse_args(argv)
    inputs = args.inputs or [default_in]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [collector] %(message)s", datefmt="%H:%M:%S")
    env = parse_env(args.env)
    if env is None:
        parser.error("--env는 영숫자로 시작하고 영숫자·._-만 쓴 64자 이하여야 합니다")
    schemes = []
    for address in inputs:
        try:
            if address.startswith("http://"):
                parse_http_address(address.removeprefix("http://"))
                schemes.append("http")
            else:
                schemes.append(parse_address(address)[0])
        except ValueError as e:
            parser.error(str(e))
    if args.once and ("udp" in schemes or "http" in schemes):
        parser.error("--once는 파일 입력에만 쓸 수 있습니다")

    writer = None
    if not args.dry_run:
        settings = influx_settings()
        writer = InfluxWriter(settings, timeout_ms=env_int("COLLECTOR_INFLUX_TIMEOUT_MS"))
        try:
            writer.check()
        except RuntimeError as e:
            log.error("%s", e)
            return 1
        log.info("InfluxDB %s bucket=%s", settings.url, settings.bucket)
    else:
        log.info("dry-run: InfluxDB에 쓰지 않습니다")

    sources = []
    try:
        for address in inputs:
            if address.startswith("http://"):
                host, port = parse_http_address(address.removeprefix("http://"))
                src = IngestSource(host, port, max_bytes=env_int("COLLECTOR_HTTP_MAX_BYTES"),
                                   request_timeout_s=env_int("COLLECTOR_HTTP_TIMEOUT_MS") / 1000)
                sources.append(src)
                log.info("입력 %s (요청 상한 %dKB)", src.address, src.server.max_bytes // 1024)
                continue
            src = open_source(address, from_start=not args.from_end, follow=not args.once,
                              udp_rcvbuf_bytes=env_int("COLLECTOR_UDP_RCVBUF_BYTES"),
                              poll_s=env_int("COLLECTOR_FILE_POLL_MS") / 1000)
            sources.append(src)
            if isinstance(src, UdpSource):
                log.info("입력 %s (수신 버퍼 %dKB)", src.address, src.rcvbuf_bytes // 1024)
            else:
                log.info("입력 %s%s", src.address, " (끝까지 읽고 종료)" if args.once else "")
    except OSError as e:
        log.error("입력을 열 수 없습니다: %s", e)
        for src in sources:
            src.close()
        return 1

    collector = Collector(writer, Path(args.recordings), batch_size=env_int("COLLECTOR_BATCH_SIZE"),
                          max_pending=env_int("COLLECTOR_MAX_PENDING"), default_env=env,
                          dedup_max_keys=env_int("COLLECTOR_DEDUP_MAX_KEYS"))
    log.info("녹화 %s (탐지 엔진 레코드는 %s), 거부 로그 %s",
             collector.raw_path, collector.env_raw_path("<환경>").name, collector.rejected_path)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        run(collector, sources, env_int("COLLECTOR_FLUSH_INTERVAL_MS") / 1000, stop)
    except KeyboardInterrupt:
        pass  # run()의 finally에서 남은 배치를 flush했다
    finally:
        collector.log_stats(final=True)
        collector.close()
        if writer is not None:
            writer.close()
    if collector.pending:
        log.warning("InfluxDB에 못 쓴 %d건은 raw 녹화(%s)에 있습니다. 복구 후 replay로 다시 넣으세요.",
                    len(collector.pending), collector.raw_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
