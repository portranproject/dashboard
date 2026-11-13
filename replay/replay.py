"""replay: 탐지 엔진 레코드(녹화·샘플)를 시각을 옮겨 /ingest로 다시 보낸다. 개발·시연 데이터, 발표 시연 백업용 (CLAUDE.md 11절).

    python -m replay.replay tests/data/detection/T10_긴공격_evidence.jsonl                 # 로컬 collector, env replay
    python -m replay.replay recordings/raw-20261109-072830-p4.jsonl --env replay --speed 2
    python -m replay.replay tests/data/detection/*.jsonl --speed 0 --gap-sec 30            # 여러 파일을 30초 간격으로 이어서
    python -m replay.replay a.jsonl --out https://3.39.170.31/ingest --ca certs/ingest.crt  # AWS로 (443이 열린 곳에서)
    python -m replay.replay a.jsonl --out file://recordings/retimed.jsonl --speed 0         # 파일로
    python -m replay.replay recordings/raw-20261111-060000-p4.jsonl --from 2026-11-11T15:08 --to 2026-11-11T15:14  # 구간만

--retime now(기본): 첫 파일의 첫 레코드를 지금으로 옮긴다. 이동량은 kpm2 칸 길이(agg_ms)의 배수로 맞춰 3초 칸 경계가 그대로다.
  같은 파일을 여러 번 재생해도 따로 저장되도록 session·alert_id 끝에 재생 표시(~r<재생 시작 시각>)를 붙인다.
--retime none: 시각·ID를 원본 그대로 보낸다(InfluxDB 장애 뒤 녹화를 다시 넣을 때 — 이미 있는 줄은 중복으로 걸러진다).
--from/--to: 원본 데이터 시각이 [from, to)인 것만 보낸다. 경보는 통째로 — 구간 안에서 시작한(raise) 경보는 근거·clear까지
  구간 밖이어도 모두 보내고, 구간 전에 시작한 경보는 뺀다(앞뒤가 잘린 경보를 만들지 않게).
시각을 적을 때 시간대가 없으면 한국 시각(KST)이다 — Grafana 화면의 시각 그대로 쓰면 된다(서버·컨테이너 시계는 UTC).

레코드는 파일 순서대로 보내되 보내는 시각이 거꾸로 가지 않게 한다(예: 경보 raise 직후에 그 경보의 pre 근거).
여러 파일은 하나씩 이어서 재생한다(--gap-sec 간격). 수집 오버헤드(overhead)도 kpm2처럼 시각을 옮겨 재생한다.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common.config import env_int, load_env
from common.schema import validation_errors
from common.transport import encode
from collector.ingest import parse_env

MS_PER_S = 1000
MAX_SKIP_DETAILS = 5
NEW_RECORD_TYPES = ("alert", "evidence", "gap", "kpm2", "hello", "f1_evt", "overhead")
DEFAULT_ALIGN_MS = 3000  # 27_ §4.1 상시 kpm2 기본 칸 길이
KST = timezone(timedelta(hours=9), "KST")  # 시간대 없이 적은 시각의 기준(Grafana 화면 시각). 서머타임 없음
ALERT_PATH_TYPES = ("alert", "evidence", "gap")

log = logging.getLogger("replay")


def _reject_constant(name: str):
    raise ValueError(f"JSON 표준이 아닌 값 {name}")


# --------------------------------------------------------------------------- 읽기·시각

def load(path: Path) -> tuple[list[dict], int]:
    """파일 순서 그대로 읽는다. 읽을 수 없거나 스키마에 맞지 않는 줄은 건너뛰고 그 수를 돌려준다."""
    records, skipped = [], 0
    with path.open(encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, 1):
            if not line.strip():
                continue
            try:
                msg = json.loads(line, parse_constant=_reject_constant)
                errors = validation_errors(msg)
                if not errors and msg["type"] not in NEW_RECORD_TYPES:
                    errors = [f"{msg['type']}는 재생하지 않음"]
            except ValueError as e:
                errors = [f"JSON 파싱 실패: {e}"]
            if errors:
                skipped += 1
                if skipped <= MAX_SKIP_DETAILS:
                    log.warning("%s:%d 건너뜀: %s", path.name, lineno, errors[0])
                continue
            records.append(msg)
    return records, skipped


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def record_time(msg: dict) -> int | None:
    """레코드가 나가는 시각(ms). 경보·재시작은 그 시각, 근거는 원본 줄 시각, 묶은 kpm2·overhead는 구간이 닫히는 끝, gap은 끊김이 끝난 때.
    hello처럼 시각이 없으면 None(앞 레코드와 같이 나감)."""
    t = msg["type"]
    if t == "alert":
        return msg["t"]
    if t == "evidence":
        raw = msg["raw"]
        return _int(raw.get("t_ms")) or _int(raw.get("t_start_ms"))
    if t == "gap":
        return msg["t_to"]
    if t in ("kpm2", "overhead"):
        return msg["t_end_ms"]
    if t == "f1_evt":
        return msg["t_ms"]
    return None


def kst(ms: int) -> str:
    return datetime.fromtimestamp(ms / MS_PER_S, KST).strftime("%Y-%m-%d %H:%M:%S")


def select_window(records: list[dict], from_ms: int | None, to_ms: int | None) -> list[dict]:
    """원본 데이터 시각이 [from_ms, to_ms)인 레코드만, 파일 순서 그대로.
    경보 경로(alert·evidence·gap)는 경보 단위로 고른다: 그 경보가 시작한 시각(파일에서 그 alert_id의 첫 alert 시각,
    alert가 없으면 첫 레코드 시각)이 구간 안이면 구간 밖 레코드(pre 근거, 늦은 clear·post 근거)까지 모두, 아니면 모두 뺀다.
    hello처럼 시각이 없는 줄은 다음 줄의 시각을 쓴다(27_ §4.3 — 뒤에 줄이 없으면 앞 줄)."""
    if from_ms is None and to_ms is None:
        return records

    def inside(t: int | None) -> bool:
        return t is not None and (from_ms is None or t >= from_ms) and (to_ms is None or t < to_ms)

    times = [record_time(m) for m in records]
    following = None
    for i in reversed(range(len(records))):
        if times[i] is None:
            times[i] = following
        else:
            following = times[i]
    previous = None
    for i, t in enumerate(times):
        times[i] = t if t is not None else previous
        previous = times[i]

    alert_start: dict[str, int | None] = {}
    first_seen: dict[str, int | None] = {}
    for msg, t in zip(records, times):
        if msg["type"] in ALERT_PATH_TYPES:
            first_seen.setdefault(msg["alert_id"], t)
            if msg["type"] == "alert":
                alert_start.setdefault(msg["alert_id"], t)
    return [msg for msg, t in zip(records, times)
            if inside(alert_start.get(msg["alert_id"], first_seen[msg["alert_id"]])
                      if msg["type"] in ALERT_PATH_TYPES else t)]


def align_ms(records: list[dict]) -> int:
    """이동량을 맞출 단위: 파일에 있는 kpm2 agg_ms들의 최소공배수(없으면 3초). 칸 경계 k·agg_ms가 그대로 남는다."""
    unit = 1
    for msg in records:
        if msg["type"] == "kpm2":
            unit = math.lcm(unit, msg["agg_ms"])
    return unit if unit > 1 else DEFAULT_ALIGN_MS


def shift_record(msg: dict, delta_ms: int, tag: str) -> dict:
    """모든 시각 필드를 delta_ms만큼 옮기고, tag가 있으면 session·alert_id 끝에 붙인 사본."""
    m = copy.deepcopy(msg)

    def shift(obj: dict, *keys: str) -> None:
        for key in keys:
            if _int(obj.get(key)) is not None:
                obj[key] += delta_ms

    def retag(obj: dict, key: str) -> None:
        if tag and isinstance(obj.get(key), str) and obj[key]:
            obj[key] += tag

    t = m["type"]
    if t == "alert":
        shift(m, "t")
        for ue in m.get("ues") or []:
            if isinstance(ue, dict):
                shift(ue, "t_hit")
        retag(m, "alert_id")
    elif t == "evidence":
        shift(m["raw"], "t_ms", "t_start_ms", "t_end_ms")
        retag(m, "alert_id")
        retag(m["raw"], "session")
    elif t == "gap":
        shift(m, "t_from", "t_to")
        retag(m, "alert_id")
    elif t in ("kpm2", "overhead"):
        shift(m, "t_start_ms", "t_end_ms")
        retag(m, "session")
    elif t == "f1_evt":
        shift(m, "t_ms")
        retag(m, "session")
    elif t == "hello":
        retag(m, "session")
    return m


@dataclass
class Planned:
    send_ms: int  # 보낼 시각(옮긴 뒤, 데이터 시각 기준)
    msg: dict
    source: str


def plan(files: list[tuple[str, list[dict]]], start_ms: int | None, gap_ms: int, tag: str) -> list[Planned]:
    """파일들을 이어서 재생할 순서·시각을 정한다.
    start_ms가 None이면 원본 시각 그대로(파일 순서대로 이어 보냄). 아니면 첫 파일은 start_ms에서, 다음 파일은
    앞 파일이 끝난 뒤 gap_ms 지나서 시작하도록 파일마다 옮긴다."""
    out: list[Planned] = []
    cursor = start_ms
    for source, records in files:
        times = [t for t in (record_time(m) for m in records) if t is not None]
        if not times:
            continue
        delta = 0
        if cursor is not None:
            unit = align_ms(records)
            delta = math.ceil((cursor - min(times)) / unit) * unit  # 칸 경계를 지키면서 cursor 뒤로
        last = None
        for msg in records:
            t = record_time(msg)
            send = (t + delta) if t is not None else (last if last is not None else min(times) + delta)
            if last is not None and send < last:
                send = last  # 파일 순서를 지키고 시각이 거꾸로 가지 않게
            last = send
            out.append(Planned(send, shift_record(msg, delta, tag) if cursor is not None else msg, source))
        if cursor is not None:
            cursor = last + gap_ms
    return out


# --------------------------------------------------------------------------- 보내기

class SendError(RuntimeError):
    pass


@dataclass
class IngestSink:
    """탐지 엔진 전송기처럼 묶어서 POST /ingest (27_ §3). 413이면 반으로 나눠, 503·연결 실패면 간격을 늘려 다시."""
    url: str
    env: str
    ca_file: str | None = None
    max_lines: int = 500
    max_bytes: int = 1_048_576
    timeout_s: float = 60.0
    max_retries: int = 8
    totals: Counter = field(default_factory=Counter)
    _buf: list[str] = field(default_factory=list)
    _buf_bytes: int = 0

    def __post_init__(self):
        self._ctx = ssl.create_default_context(cafile=self.ca_file) if self.url.startswith("https://") else None

    def send(self, line: str) -> None:
        size = len(line.encode("utf-8")) + 1
        if self._buf and (len(self._buf) >= self.max_lines or self._buf_bytes + size > self.max_bytes):
            self.flush()
        self._buf.append(line)
        self._buf_bytes += size

    def flush(self) -> None:
        if self._buf:
            lines, self._buf, self._buf_bytes = self._buf, [], 0
            self._post(lines)

    def close(self) -> None:
        self.flush()

    def _post(self, lines: list[str]) -> None:
        body = ("\n".join(lines) + "\n").encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Content-Type": "application/x-ndjson", "X-Env": self.env, "User-Agent": "portran-replay/1"})
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s, context=self._ctx) as resp:
                    result = json.load(resp)
                self.totals.update({k: result.get(k, 0) for k in ("accepted", "rejected", "duplicates")})
                self.totals["requests"] += 1
                if result.get("rejected"):
                    log.warning("거부 %d줄 — collector의 recordings/rejected.jsonl에 사유", result["rejected"])
                return
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:300]
                if e.code == 413 and len(lines) > 1:
                    half = len(lines) // 2
                    self._post(lines[:half])
                    self._post(lines[half:])
                    return
                if e.code != 503:
                    raise SendError(f"HTTP {e.code}: {detail}") from None
                reason = f"HTTP 503: {detail}"
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                reason = str(getattr(e, "reason", e))
            if attempt == self.max_retries:
                raise SendError(f"{self.max_retries}번 다시 보내도 실패: {reason}")
            log.warning("보내기 실패(%s), %.0f초 뒤 다시", reason, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30.0)


@dataclass
class FileSink:
    path: Path
    totals: Counter = field(default_factory=Counter)

    def __post_init__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open("w", encoding="utf-8", newline="\n")

    def send(self, line: str) -> None:
        self._fp.write(line + "\n")
        self.totals["written"] += 1

    def flush(self) -> None:
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


def open_sink(out: str, env: str, ca_file: str | None, max_bytes: int):
    if out.startswith(("http://", "https://")):
        return IngestSink(out, env, ca_file=ca_file, max_bytes=max_bytes)
    if out.startswith("file://"):
        return FileSink(Path(out.removeprefix("file://")))
    raise ValueError(f"--out은 http(s)://…/ingest 또는 file://path 형식이어야 합니다: {out}")


def run(planned: list[Planned], sink, speed: float) -> Counter:
    """정해진 시각에 맞춰 보낸다(speed배, 0이면 기다리지 않음). 기다리기 전에 모은 줄을 보낸다."""
    counts: Counter = Counter()
    if not planned:
        return counts
    base = planned[0].send_ms
    wall0 = time.monotonic()
    next_progress = 60
    for p in planned:
        if speed > 0:
            delay = wall0 + (p.send_ms - base) / MS_PER_S / speed - time.monotonic()
            if delay > 0:
                sink.flush()
                time.sleep(delay)
        if (p.send_ms - base) / MS_PER_S >= next_progress:
            log.info("%d초 지점, 보낸 레코드 %d건", next_progress, sum(counts.values()))
            next_progress += 60
        sink.send(encode(p.msg))
        counts[p.msg["type"]] += 1
    sink.flush()
    return counts


# --------------------------------------------------------------------------- CLI

def parse_time(value: str) -> int:
    """ISO 시각(2026-11-11T15:08, 2026-11-11 15:08:30, …+09:00, …Z) → epoch ms. 시간대가 없으면 한국 시각(KST)."""
    text = value.strip()
    if text[-1:] in ("Z", "z"):  # Python 3.10의 fromisoformat은 Z를 못 읽는다(3.11부터 읽음)
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return round(dt.timestamp() * MS_PER_S)


def parse_retime(value: str) -> int | None:
    if value == "none":
        return None
    if value == "now":
        return time.time_ns() // 1_000_000
    return parse_time(value)


def replay_tag(start_ms: int | None) -> str:
    if start_ms is None:
        return ""
    return "~r" + datetime.fromtimestamp(start_ms / MS_PER_S, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    load_env()
    host = os.environ.get("COLLECTOR_HTTP_HOST", "127.0.0.1")
    default_out = f"http://{host}:{os.environ['COLLECTOR_HTTP_PORT']}/ingest"
    parser = argparse.ArgumentParser(prog="python -m replay.replay", description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", type=Path, help="녹화(recordings/raw-*-<환경>.jsonl)나 탐지 쪽 샘플")
    parser.add_argument("--out", default=default_out, help=f"http(s)://…/ingest 또는 file://path (기본 {default_out})")
    parser.add_argument("--env", default="replay", help="X-Env (기본 replay — 실측 p4와 섞이지 않게)")
    parser.add_argument("--ca", help="https일 때 서버 인증서(PEM). 예: certs/ingest.crt")
    parser.add_argument("--speed", type=float, default=1.0, help="배속. 0이면 기다리지 않고 바로 보냄 (기본 1)")
    parser.add_argument("--retime", default="now",
                        help="now(기본) | none | 2026-11-20T10:00:00 — 첫 레코드를 둘 시각(시간대 없으면 한국 시각)")
    parser.add_argument("--from", dest="from_time", metavar="시각",
                        help="원본 데이터 시각이 이때부터인 것만 (예: 2026-11-11T15:08, 시간대 없으면 한국 시각). 경보는 통째로")
    parser.add_argument("--to", dest="to_time", metavar="시각", help="원본 데이터 시각이 이때 전까지인 것만 (--from과 같은 형식)")
    parser.add_argument("--gap-sec", type=float, default=10.0, help="여러 파일을 이어 재생할 때 사이 간격 (기본 10초)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [replay] %(message)s", datefmt="%H:%M:%S")
    for handler in logging.getLogger().handlers:  # 로그 앞 시각도 한국 시각(컨테이너 시계는 UTC)
        if handler.formatter:
            handler.formatter.converter = lambda ts: datetime.fromtimestamp(ts, KST).timetuple()
    if args.speed < 0:
        parser.error("--speed는 0 이상이어야 합니다")
    if parse_env(args.env) != args.env:
        parser.error("--env는 영숫자로 시작하고 영숫자·._-만 쓴 64자 이하여야 합니다")
    missing = [str(f) for f in args.files if not f.exists()]
    if missing:
        parser.error(f"파일이 없습니다: {', '.join(missing)}")
    try:
        start_ms = parse_retime(args.retime)
    except ValueError:
        parser.error(f"--retime은 now, none 또는 2026-11-20T10:00:00 형식이어야 합니다: {args.retime}")
    window = {}
    for name, value in (("from", args.from_time), ("to", args.to_time)):
        try:
            window[name] = parse_time(value) if value else None
        except ValueError:
            parser.error(f"--{name}은 2026-11-11T15:08:00 형식이어야 합니다: {value}")
    if window["from"] is not None and window["to"] is not None and window["from"] >= window["to"]:
        parser.error("--from은 --to보다 앞이어야 합니다")
    try:
        sink = open_sink(args.out, args.env, args.ca, env_int("COLLECTOR_HTTP_MAX_BYTES"))
    except (ValueError, OSError, ssl.SSLError) as e:
        parser.error(str(e))

    files = []
    for path in args.files:
        records, skipped = load(path)
        times = [t for t in (record_time(m) for m in records) if t is not None]
        span = f" | 데이터 시각 {kst(min(times))} ~ {kst(max(times))} (한국 시각)" if times else ""
        log.info("%s: %d건 (건너뜀 %d) %s%s", path.name, len(records), skipped,
                 ", ".join(f"{k}={v}" for k, v in sorted(Counter(m["type"] for m in records).items())), span)
        if window["from"] is not None or window["to"] is not None:
            total = len(records)
            records = select_window(records, window["from"], window["to"])
            alerts = len({m["alert_id"] for m in records if m["type"] in ALERT_PATH_TYPES})
            log.info("  구간 %s ~ %s: %d건 중 %d건 (경보 %d개)", kst(window["from"]) if window["from"] is not None else "처음",
                     kst(window["to"]) if window["to"] is not None else "끝", total, len(records), alerts)
        files.append((path.name, records))
    tag = replay_tag(start_ms)
    planned = plan(files, start_ms, round(args.gap_sec * MS_PER_S), tag)
    if not planned:
        log.error("보낼 레코드가 없습니다%s", " — --from/--to는 한국 시각이고 원본 데이터 시각 기준입니다(위 데이터 시각 참고)"
                  if window["from"] is not None or window["to"] is not None else "")
        return 1
    span_s = (planned[-1].send_ms - planned[0].send_ms) / MS_PER_S
    first = kst(planned[0].send_ms) + " (한국 시각)"
    log.info("%d건, 데이터 시각 %s부터 %.0f초, speed=%s, out=%s, X-Env=%s%s", len(planned), first, span_s,
             args.speed, args.out, args.env, f", 재생 표시 {tag}" if tag else "")

    try:
        counts = run(planned, sink, args.speed)
        sink.close()
    except KeyboardInterrupt:
        log.info("중단됨")
        return 130
    except SendError as e:
        log.error("보내기 실패: %s", e)
        return 1
    log.info("완료: 보냄 %s | 응답 %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
             ", ".join(f"{k}={v}" for k, v in sorted(sink.totals.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
