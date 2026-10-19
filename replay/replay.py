"""replay: 녹화 파일(collector의 raw-*.jsonl)을 다시 보낸다. 발표 시연 백업용 (CLAUDE.md 11절).

    python -m replay.replay recordings/raw-xxxx.jsonl --speed 1 --out udp://127.0.0.1:9999 --retime now

--retime now (기본): 원본 시간 간격은 그대로 두고, 첫 메시지 시각을 지금으로 옮겨 보낸다 (실시간 대시보드에 바로 보이도록).
--retime none: 원본 시각 그대로. --retime 2026-11-20T10:00:00: 첫 메시지를 그 시각으로 옮긴다.
메시지는 시각 순으로 정렬해 보낸다. attack_run.params에는 재생 표시(replay)를 넣어 evaluator·대시보드가 알 수 있게 한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from common.config import load_env
from common.schema import count_key, message_time, shift_times, validation_errors
from common.transport import encode, open_sink, paced

NS = 1_000_000_000
MAX_SKIP_DETAILS = 5

log = logging.getLogger("replay")


def _reject_constant(name: str):
    raise ValueError(f"JSON 표준이 아닌 값 {name}")


def load(path: Path) -> tuple[list[dict], int]:
    """녹화 파일을 읽어 시각 순으로 정렬한다. 읽을 수 없거나 스키마에 맞지 않는 줄은 건너뛰고 그 수를 돌려준다."""
    messages, skipped = [], 0
    with path.open(encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, 1):
            if not line.strip():
                continue
            try:
                msg = json.loads(line, parse_constant=_reject_constant)
                errors = validation_errors(msg)
            except ValueError as e:
                errors = [f"JSON 파싱 실패: {e}"]
            if errors:
                skipped += 1
                if skipped <= MAX_SKIP_DETAILS:
                    log.warning("%s:%d 건너뜀: %s", path.name, lineno, errors[0])
                continue
            messages.append(msg)
    messages.sort(key=message_time)  # 녹화는 도착 순서라 시각이 조금씩 뒤섞일 수 있다
    return messages, skipped


def retime(messages: list[dict], start_ns: int | None) -> tuple[list[dict], int]:
    """첫 메시지가 start_ns가 되도록 모든 시각을 같은 만큼 옮긴다 (None이면 그대로). (옮긴 메시지, 이동량 ns)."""
    if start_ns is None or not messages:
        return messages, 0
    delta = start_ns - message_time(messages[0])
    return [shift_times(m, delta) for m in messages], delta


def mark_replay(msg: dict, source: str, delta_ns: int) -> dict:
    """attack_run.params에 재생 표시를 넣는다. 원본 params(예: mock의 generator)는 그대로 둔다."""
    if msg["type"] != "attack_run":
        return msg
    params = dict(msg["params"])
    params["replay"] = {"file": source, "shift_s": round(delta_ns / NS, 3)}
    return {**msg, "params": params}


def parse_retime(value: str) -> int | None:
    if value == "none":
        return None
    if value == "now":
        return time.time_ns()
    # 시간대가 없으면 로컬 시각 (mock의 --start, evaluator의 --from과 같은 규칙)
    return round(datetime.fromisoformat(value).timestamp() * 1_000_000) * 1000


def main(argv: list[str] | None = None) -> int:
    load_env()
    default_out = f"udp://{os.environ['COLLECTOR_UDP_HOST']}:{os.environ['COLLECTOR_UDP_PORT']}"
    parser = argparse.ArgumentParser(prog="python -m replay.replay", description=__doc__.split("\n")[0])
    parser.add_argument("file", type=Path, help="녹화 파일 (예: recordings/raw-20261120-100000.jsonl)")
    parser.add_argument("--speed", type=float, default=1.0, help="배속. 0이면 기다리지 않고 바로 보냄 (기본 1)")
    parser.add_argument("--out", default=default_out, help=f"udp://host:port 또는 file://path (기본 {default_out})")
    parser.add_argument("--retime", default="now",
                        help="now(기본) | none | 2026-11-20T10:00:00 — 첫 메시지를 둘 시각")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [replay] %(message)s", datefmt="%H:%M:%S")
    if args.speed < 0:
        parser.error("--speed는 0 이상이어야 합니다")
    if not args.file.exists():
        parser.error(f"파일이 없습니다: {args.file}")
    try:
        start_ns = parse_retime(args.retime)
    except ValueError:
        parser.error(f"--retime은 now, none 또는 2026-11-20T10:00:00 형식이어야 합니다: {args.retime}")

    messages, skipped = load(args.file)
    if not messages:
        log.error("보낼 메시지가 없습니다: %s (건너뜀 %d줄)", args.file, skipped)
        return 1
    span_s = (message_time(messages[-1]) - message_time(messages[0])) / NS
    messages, delta = retime(messages, start_ns)
    messages = [mark_replay(m, args.file.name, delta) for m in messages]
    first = message_time(messages[0])
    log.info("%s: %d건 (건너뜀 %d), 길이 %.0f초, %s", args.file, len(messages), skipped, span_s,
             ", ".join(f"{k}={v}" for k, v in sorted(Counter(count_key(m) for m in messages).items())))
    log.info("시각 %s부터 (이동 %+.0f초), speed=%s, out=%s",
             datetime.fromtimestamp(first / NS).isoformat(timespec="seconds"), delta / NS, args.speed, args.out)
    if args.speed > 1 and start_ns is not None:
        log.info("speed가 1보다 크면 메시지 시각이 실제 시각보다 앞서 나간다 (원본 간격을 유지하므로)")

    counts: Counter = Counter()
    sink = open_sink(args.out)
    next_progress = 60
    try:
        for msg in paced(messages, message_time, first, args.speed, before_sleep=sink.flush):
            if (message_time(msg) - first) / NS >= next_progress:
                log.info("%d초 경과, 보낸 메시지 %d건", next_progress, sum(counts.values()))
                next_progress += 60
            sink.send(encode(msg))
            counts[count_key(msg)] += 1
    except KeyboardInterrupt:
        log.info("중단됨: %d / %d건 보냄", sum(counts.values()), len(messages))
        return 130
    finally:
        sink.close()
    log.info("완료: %s", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
