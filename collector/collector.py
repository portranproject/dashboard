"""collector: 수신 → 스키마 검증 → raw 녹화 → InfluxDB 배치 쓰기.

    python -m collector.collector                                          # UDP (.env의 COLLECTOR_UDP_HOST:PORT)
    python -m collector.collector --in file://recordings/mock.jsonl --once # 파일을 끝까지 읽고 종료
    python -m collector.collector --in udp://0.0.0.0:9999 --in file://agent.jsonl   # 여러 입력 동시에
    python -m collector.collector --dry-run                                # InfluxDB 없이 검증·녹화만

검증에 실패한 메시지는 버리지 않고 recordings/rejected.jsonl에 사유와 함께 남긴다.
검증을 통과한 메시지는 받은 그대로 recordings/raw-<날짜시각>.jsonl에 녹화한다(replay용).
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

from .influx_writer import InfluxWriter, WriteError, to_point

log = logging.getLogger("collector")

# 시각 앞뒤가 뒤바뀐 메시지를 로그에 자세히 남기는 최대 건수 (이후로는 건수만 센다)
MAX_WARNING_DETAILS = 5


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

    def minus(self, other: "Stats") -> "Stats":
        return Stats(**{k: getattr(self, k) - getattr(other, k) for k in self.__dataclass_fields__})


@dataclass
class _Pending:
    line: str
    origin: str
    point: object


@dataclass
class Collector:
    writer: Writer | None  # None이면 dry-run (InfluxDB에 쓰지 않음)
    recordings_dir: Path
    batch_size: int
    max_pending: int
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

    # ------------------------------------------------------------------ 메시지 처리

    def handle(self, data: bytes, origin: str) -> None:
        self.stats.received += 1
        try:
            line = data.decode("utf-8")
        except UnicodeDecodeError as e:
            self._reject(data.decode("utf-8", errors="replace"), origin, [f"UTF-8 아님: {e}"])
            return
        try:
            msg = json.loads(line, parse_constant=_reject_constant)
        except ValueError as e:
            self._reject(line, origin, [f"JSON 파싱 실패: {e}"])
            return
        errors = validation_errors(msg)
        if errors:
            self._reject(line, origin, errors)
            return

        self._check_times(msg, origin)
        self._write_raw(line)
        if self.writer is None:
            self.stats.stored += 1
            return
        self.pending.append(_Pending(line, origin, to_point(msg)))
        overflow = len(self.pending) - self.max_pending
        if overflow > 0:
            # raw 녹화에는 남아 있으므로 InfluxDB 복구 후 replay로 다시 넣을 수 있다.
            del self.pending[:overflow]
            self.stats.dropped += overflow

    def _check_times(self, msg: dict, origin: str) -> None:
        """스키마로 표현할 수 없는 시각 순서 검사. 노드 간 시계가 어긋나도 데이터를 잃지 않도록 거부하지 않고 경고만 한다."""
        if msg["type"] == "detection" and msg["ts_first_evidence"] > msg["ts_detected"]:
            problem = f"ts_first_evidence가 ts_detected보다 {(msg['ts_first_evidence'] - msg['ts_detected']) / 1e6:.1f}ms 늦음"
        elif msg["type"] == "attack_run" and msg["ts_start"] > msg["ts_end"]:
            problem = "ts_start가 ts_end보다 늦음"
        else:
            return
        self.stats.warnings += 1
        if self.stats.warnings <= MAX_WARNING_DETAILS:
            ident = msg.get("event_id") or msg.get("run_id")
            log.warning("시각 순서 경고 (%s, %s): %s — 저장은 함", origin, ident, problem)

    def _write_raw(self, line: str) -> None:
        if self._raw_fp is None:
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self._raw_fp = self.raw_path.open("a", encoding="utf-8", newline="\n")
        self._raw_fp.write(line + "\n")

    def _reject(self, line: str, origin: str, reasons: list[str]) -> None:
        self.stats.rejected += 1
        if self._rejected_fp is None:
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self._rejected_fp = self.rejected_path.open("a", encoding="utf-8", newline="\n")
        now = datetime.now()
        record = {"received_at": now.isoformat(timespec="milliseconds"), "source": origin,
                  "reasons": reasons, "raw": line}
        self._rejected_fp.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ InfluxDB

    def flush(self) -> None:
        for fp in (self._raw_fp, self._rejected_fp):
            if fp is not None:
                fp.flush()
        while self.pending:
            chunk = self.pending[: self.batch_size]
            try:
                self.writer.write([p.point for p in chunk])
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
                self.writer.write([p.point])
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
        for fp in (self._raw_fp, self._rejected_fp):
            if fp is not None:
                fp.close()


_DONE = object()


def run(collector: Collector, sources: list, flush_interval_s: float, stop: threading.Event,
        log_interval_s: float = 1.0) -> None:
    """입력마다 스레드가 줄을 읽어 큐에 넣고, 이 함수가 처리·배치 쓰기·로그를 맡는다.
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
                collector.handle(*item)

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
                collector.handle(*item)
        collector.flush()
        for src in sources:
            src.close()


def main(argv: list[str] | None = None) -> int:
    load_env()
    default_in = f"udp://{os.environ['COLLECTOR_UDP_HOST']}:{os.environ['COLLECTOR_UDP_PORT']}"
    parser = argparse.ArgumentParser(prog="python -m collector.collector", description=__doc__.split("\n")[0])
    parser.add_argument("--in", dest="inputs", action="append", metavar="ADDRESS",
                        help=f"udp://host:port 또는 file://path. 여러 번 줄 수 있음 (기본 {default_in})")
    parser.add_argument("--once", action="store_true", help="파일 입력을 끝까지 읽고 종료 (UDP 입력과 같이 못 씀)")
    parser.add_argument("--from-end", action="store_true", help="파일 입력을 처음이 아니라 현재 끝부터 읽음")
    parser.add_argument("--dry-run", action="store_true", help="InfluxDB에 쓰지 않고 검증·녹화만")
    parser.add_argument("--recordings", default=os.environ["RECORDINGS_DIR"], help="raw 녹화·거부 로그 폴더")
    args = parser.parse_args(argv)
    inputs = args.inputs or [default_in]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [collector] %(message)s", datefmt="%H:%M:%S")
    try:
        schemes = [parse_address(a)[0] for a in inputs]
    except ValueError as e:
        parser.error(str(e))
    if args.once and "udp" in schemes:
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
        return 1

    collector = Collector(writer, Path(args.recordings), batch_size=env_int("COLLECTOR_BATCH_SIZE"),
                          max_pending=env_int("COLLECTOR_MAX_PENDING"))
    log.info("녹화 %s, 거부 로그 %s", collector.raw_path, collector.rejected_path)

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
