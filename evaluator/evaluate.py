"""evaluator: 탐지율·오탐·지연 계산 (CLAUDE.md 10절).

    python -m evaluator.evaluate --from 2026-11-20T10:00:00 --to 2026-11-20T12:00:00 --grace-sec 5

매칭: detection의 attack_type이 attack_run의 scenario와 같고 ts_detected가 [ts_start, ts_end + grace] 안이면 그 run에 매칭.
  run에 매칭된 detection이 1개 이상 → TP, 없으면 FN (여러 개여도 TP 1건). 어떤 run에도 매칭되지 않은 detection → FP.
시나리오 × 룰셋별로 탐지율, precision, fp_per_hour, 지연 p50/p95를 계산해
InfluxDB `eval_result`와 reports/eval-<날짜시각>.md·.csv에 남긴다.

평가 구간 [--from, --to):
  - run: ts_start가 구간 안인 것을 센다.
  - detection: ts_detected가 구간 안인 것을 센다 (precision, 오탐).
  - 매칭에는 구간 시작 전 EVAL_LOOKBACK_SEC 안에 시작한 run과, 구간 끝 뒤 grace까지의 detection도 쓴다.
    (구간 경계에 걸친 공격 때문에 오탐·미탐이 잘못 세지지 않도록)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from common.config import env_int, influx_settings, load_env

NS = 1_000_000_000
RULESETS = ("full", "kpm_only")
DATA_SOURCES = ("auto", "mock", "real", "replay")

log = logging.getLogger("evaluator")


# --------------------------------------------------------------------------- 데이터

@dataclass(frozen=True)
class AttackRun:
    run_id: str
    scenario: str
    ts_start: int
    ts_end: int
    params: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class Detection:
    event_id: str
    attack_type: str
    ruleset: str
    ts_detected: int
    ts_first_evidence: int


@dataclass
class ResultRow:
    """시나리오 × 룰셋 하나의 결과. 계산할 수 없는 값(분모 0)은 None."""
    scenario: str
    ruleset: str
    runs: int = 0
    tp: int = 0
    fn: int = 0
    detection_rate: float | None = None
    detections: int = 0
    matched: int = 0
    fp_count: int = 0
    precision: float | None = None
    fp_per_hour: float | None = None
    latency_p50_ms: float | None = None   # ts_detected - ts_first_evidence (run별 첫 매칭 탐지)
    latency_p95_ms: float | None = None
    onset_p50_ms: float | None = None     # ts_detected - ts_start (run별 첫 매칭 탐지)
    onset_p95_ms: float | None = None


@dataclass
class RunDetail:
    """run 하나의 룰셋별 결과 (리포트용)."""
    run: AttackRun
    first: dict[str, Detection | None]
    matched: dict[str, int]


@dataclass
class Evaluation:
    window_from: int
    window_to: int
    grace_ns: int
    rows: list[ResultRow]
    run_details: list[RunDetail]
    non_attack_hours: float
    data_source: str


# --------------------------------------------------------------------------- 계산 (순수 함수)

def percentile(values: list[float], p: float) -> float | None:
    """선형 보간 백분위수 (numpy 기본 방식과 같음). 값이 없으면 None."""
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def match(runs: Iterable[AttackRun], detections: Iterable[Detection], grace_ns: int) -> dict[str, list[Detection]]:
    """run_id → 그 run에 매칭된 detection 목록 (ts_detected 순). 한 detection이 여러 run에 매칭될 수 있다."""
    runs = list(runs)
    out: dict[str, list[Detection]] = {r.run_id: [] for r in runs}
    for d in sorted(detections, key=lambda d: d.ts_detected):
        for r in runs:
            if d.attack_type == r.scenario and r.ts_start <= d.ts_detected <= r.ts_end + grace_ns:
                out[r.run_id].append(d)
    return out


def non_attack_hours(window_from: int, window_to: int, runs: Iterable[AttackRun]) -> float:
    """평가 구간에서 어떤 공격도 진행 중이 아니던 시간(시간 단위). 공격 구간은 [ts_start, ts_end]."""
    spans = sorted((max(r.ts_start, window_from), min(r.ts_end, window_to)) for r in runs)
    attacked, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if s >= e:
            continue
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                attacked += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        attacked += cur_e - cur_s
    return (window_to - window_from - attacked) / NS / 3600


def evaluate(runs: list[AttackRun], detections: list[Detection], window_from: int, window_to: int,
             grace_ns: int, data_source: str = "unknown") -> Evaluation:
    """runs·detections는 구간 주변까지 넉넉히 가져온 것. 세는 대상은 모듈 설명의 규칙대로 고른다."""
    matches = match(runs, detections, grace_ns)
    matched_ids = {id(d) for ds in matches.values() for d in ds}
    counted_runs = [r for r in runs if window_from <= r.ts_start < window_to]
    counted_dets = [d for d in detections if window_from <= d.ts_detected < window_to]
    quiet_hours = non_attack_hours(window_from, window_to, runs)

    scenarios = sorted({r.scenario for r in counted_runs} | {d.attack_type for d in counted_dets})
    rows: list[ResultRow] = []
    for scenario in scenarios:
        s_runs = [r for r in counted_runs if r.scenario == scenario]
        for ruleset in RULESETS:
            row = ResultRow(scenario, ruleset, runs=len(s_runs))
            latency, onset = [], []
            for r in s_runs:
                first = next((d for d in matches[r.run_id] if d.ruleset == ruleset), None)
                if first is None:
                    row.fn += 1
                    continue
                row.tp += 1
                latency.append((first.ts_detected - first.ts_first_evidence) / 1e6)
                onset.append((first.ts_detected - r.ts_start) / 1e6)
            dets = [d for d in counted_dets if d.attack_type == scenario and d.ruleset == ruleset]
            row.detections = len(dets)
            row.matched = sum(1 for d in dets if id(d) in matched_ids)
            row.fp_count = row.detections - row.matched
            row.detection_rate = row.tp / row.runs if row.runs else None
            row.precision = row.matched / row.detections if row.detections else None
            row.fp_per_hour = row.fp_count / quiet_hours if quiet_hours > 0 else None
            row.latency_p50_ms, row.latency_p95_ms = percentile(latency, 50), percentile(latency, 95)
            row.onset_p50_ms, row.onset_p95_ms = percentile(onset, 50), percentile(onset, 95)
            rows.append(row)

    details = []
    for r in counted_runs:
        firsts = {rs: next((d for d in matches[r.run_id] if d.ruleset == rs), None) for rs in RULESETS}
        counts = {rs: sum(1 for d in matches[r.run_id] if d.ruleset == rs) for rs in RULESETS}
        details.append(RunDetail(r, firsts, counts))
    return Evaluation(window_from, window_to, grace_ns, rows, details, quiet_hours, data_source)


def detect_data_source(runs: Iterable[AttackRun]) -> str:
    """attack_run.params로 판단한다: mock 표시가 있으면 mock (녹화를 재생한 mock도 숫자는 mock이므로 mock),
    replay 표시만 있으면 replay, 둘 다 없으면 real. 공격 기록이 없으면 판단할 수 없다."""
    runs = list(runs)
    if not runs:
        return "unknown"
    if any(r.params.get("generator") == "mock" for r in runs):
        return "mock"
    return "replay" if any("replay" in r.params for r in runs) else "real"


# --------------------------------------------------------------------------- InfluxDB

def fetch(query_api, bucket: str, org: str, start_ns: int, stop_ns: int) -> tuple[list[AttackRun], list[Detection]]:
    def pivoted(measurement: str, fields: list[str]) -> list[dict]:
        flux = f"""
from(bucket: "{bucket}")
  |> range(start: time(v: {start_ns}), stop: time(v: {stop_ns}))
  |> filter(fn: (r) => r._measurement == "{measurement}" and contains(value: r._field, set: {json.dumps(fields)}))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> map(fn: (r) => ({{r with time_ns: int(v: r._time)}}))
"""
        # influxdb-client는 _time을 마이크로초까지만 담은 datetime으로 주므로, 정수 ns(time_ns)를 따로 받는다
        return [rec.values for table in query_api.query(flux, org=org) for rec in table.records]

    runs = [
        AttackRun(v["run_id"], v["scenario"], v["time_ns"], int(v["ts_end"]), json.loads(v.get("params_json") or "{}"))
        for v in pivoted("attack_run", ["run_id", "ts_end", "params_json"])
    ]
    detections = [
        Detection(v["event_id"], v["attack_type"], v["ruleset"], v["time_ns"], int(v["ts_first_evidence"]))
        for v in pivoted("detection", ["event_id", "ts_first_evidence"])
    ]
    return runs, detections


def write_results(write_api, bucket: str, org: str, ev: Evaluation, eval_id: str, eval_ns: int) -> int:
    from influxdb_client import Point, WritePrecision

    points = []
    for row in ev.rows:
        p = (Point("eval_result").time(eval_ns, WritePrecision.NS)
             .tag("scenario", row.scenario).tag("ruleset", row.ruleset).tag("data_source", ev.data_source)
             .field("eval_id", eval_id)
             .field("window_from", ev.window_from).field("window_to", ev.window_to)
             .field("grace_sec", ev.grace_ns / NS)
             .field("runs", row.runs).field("tp", row.tp).field("fn", row.fn)
             .field("detections", row.detections).field("fp_count", row.fp_count))
        for name in ("detection_rate", "precision", "fp_per_hour", "latency_p50_ms", "latency_p95_ms",
                     "onset_p50_ms", "onset_p95_ms"):
            value = getattr(row, name)
            if value is not None:  # 계산할 수 없는 값(분모 0)은 쓰지 않는다
                p.field(name, float(value))
        points.append(p)
    write_api.write(bucket=bucket, org=org, record=points, write_precision=WritePrecision.NS)
    return len(points)


# --------------------------------------------------------------------------- 리포트

SOURCE_LABEL = {
    "mock": "mock — 성능 결과 아님 (mock 생성기가 정한 탐지율·지연을 다시 계산한 것)",
    "replay": "replay — 녹화 데이터 재생",
    "real": "실제 테스트베드",
    "unknown": "알 수 없음 (공격 기록 없음)",
}


def _fmt(value: Any, pct: bool = False, digits: int = 1) -> str:
    if value is None:
        return "—"
    if pct:
        return f"{value * 100:.1f}%"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _time(ns: int) -> str:
    return datetime.fromtimestamp(ns / NS).isoformat(sep=" ", timespec="seconds")


def write_reports(ev: Evaluation, eval_id: str, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{eval_id}.csv"
    md_path = out_dir / f"{eval_id}.md"

    columns = list(ResultRow.__dataclass_fields__)
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["eval_id", "data_source", "window_from", "window_to", "grace_sec", *columns])
        for row in ev.rows:
            values = asdict(row)
            w.writerow([eval_id, ev.data_source, _time(ev.window_from), _time(ev.window_to), ev.grace_ns / NS,
                        *("" if values[c] is None else values[c] for c in columns)])

    lines = [f"# 탐지 성능 평가 {eval_id}", ""]
    if ev.data_source == "mock":
        lines += ["> ⚠ **mock 데이터로 계산한 결과다. 성능 결과가 아니다.** (CLAUDE.md 12절 7항)", ""]
    lines += [
        "| 항목 | 값 |", "|---|---|",
        f"| 데이터 출처 | {SOURCE_LABEL.get(ev.data_source, ev.data_source)} |",
        f"| 평가 구간 | {_time(ev.window_from)} ~ {_time(ev.window_to)} |",
        f"| grace | {ev.grace_ns / NS:g}초 |",
        f"| 공격 run 수 | {len(ev.run_details)} |",
        f"| 공격 없던 시간 | {ev.non_attack_hours:.2f}시간 |",
        "",
        "## 시나리오 × 룰셋",
        "",
        "| 시나리오 | 룰셋 | run | TP | FN | 탐지율 | 탐지 수 | 매칭 | 오탐 | precision | 오탐/시간 | 지연 p50 (ms) | 지연 p95 (ms) | 시작→탐지 p50 (ms) | 시작→탐지 p95 (ms) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in ev.rows:
        lines.append(
            f"| {r.scenario} | {r.ruleset} | {r.runs} | {r.tp} | {r.fn} | {_fmt(r.detection_rate, pct=True)} | "
            f"{r.detections} | {r.matched} | {r.fp_count} | {_fmt(r.precision, pct=True)} | {_fmt(r.fp_per_hour, digits=2)} | "
            f"{_fmt(r.latency_p50_ms)} | {_fmt(r.latency_p95_ms)} | {_fmt(r.onset_p50_ms)} | {_fmt(r.onset_p95_ms)} |")
    lines += [
        "",
        "- 지연 = `ts_detected - ts_first_evidence`, 시작→탐지 = `ts_detected - ts_start`. 둘 다 run마다 첫 매칭 탐지 기준.",
        "- 탐지율 = TP / run, precision = 매칭된 탐지 / 전체 탐지, 오탐/시간 = 오탐 / 공격 없던 시간. 분모가 0이면 —.",
        "",
        "## run별",
        "",
        "| run_id | 시나리오 | 시작 | 끝 | full | kpm_only |",
        "|---|---|---|---|---|---|",
    ]
    for d in ev.run_details:
        cells = []
        for rs in RULESETS:
            first = d.first[rs]
            if first is None:
                cells.append("미탐")
            else:
                cells.append(f"탐지 {d.matched[rs]}건, 첫 탐지 +{(first.ts_detected - d.run.ts_start) / 1e6:.0f}ms")
        lines.append(f"| {d.run.run_id} | {d.run.scenario} | {_time(d.run.ts_start)} | {_time(d.run.ts_end)} | "
                     f"{cells[0]} | {cells[1]} |")
    lines += ["", "매칭 규칙: CLAUDE.md 10절. 같은 공격 유형이고 `ts_detected`가 `[ts_start, ts_end + grace]` 안이면 매칭.", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, csv_path


# --------------------------------------------------------------------------- CLI

def parse_time(value: str) -> int:
    if value == "now":
        return time.time_ns()
    # 시간대가 없으면 로컬 시각으로 본다 (mock의 --start와 같은 규칙)
    return round(datetime.fromisoformat(value).timestamp() * 1_000_000) * 1000


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(prog="python -m evaluator.evaluate", description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="start", required=True, help="평가 시작. 예: 2026-11-20T10:00:00 (시간대 없으면 로컬)")
    parser.add_argument("--to", dest="stop", default="now", help="평가 끝 (기본 now)")
    parser.add_argument("--grace-sec", type=float, default=float(os.environ["EVAL_GRACE_SEC"]),
                        help=f"공격 종료 후 탐지를 인정하는 시간 (기본 .env의 EVAL_GRACE_SEC={os.environ['EVAL_GRACE_SEC']})")
    parser.add_argument("--source", choices=DATA_SOURCES, default="auto",
                        help="리포트에 적을 데이터 출처. auto면 attack_run의 mock·replay 표시로 판단")
    parser.add_argument("--reports-dir", default=os.environ["REPORTS_DIR"], help="리포트 폴더 (기본 .env의 REPORTS_DIR)")
    parser.add_argument("--no-write", action="store_true", help="InfluxDB eval_result에 쓰지 않음 (리포트만)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [evaluator] %(message)s", datefmt="%H:%M:%S")

    try:
        window_from, window_to = parse_time(args.start), parse_time(args.stop)
    except ValueError as e:
        parser.error(f"시각 형식이 잘못됐습니다: {e}")
    if window_from >= window_to:
        parser.error("--from은 --to보다 앞이어야 합니다")
    grace_ns = round(args.grace_sec * NS)
    lookback_ns = env_int("EVAL_LOOKBACK_SEC") * NS

    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    s = influx_settings()
    with InfluxDBClient(url=s.url, token=s.token, org=s.org) as client:
        if not client.ping():
            log.error("InfluxDB에 접속할 수 없습니다: %s (docker compose up -d 했는지 확인)", s.url)
            return 1
        query_api = client.query_api()
        # run은 구간 시작 전 lookback부터, detection은 그 run들이 끝난 뒤 grace까지 가져온다
        runs, _ = fetch(query_api, s.bucket, s.org, window_from - lookback_ns, window_to)
        stop = max([window_to] + [r.ts_end + grace_ns + 1 for r in runs])
        _, detections = fetch(query_api, s.bucket, s.org, window_from - lookback_ns, stop)

        counted = [r for r in runs if window_from <= r.ts_start < window_to]
        source = detect_data_source(counted) if args.source == "auto" else args.source
        ev = evaluate(runs, detections, window_from, window_to, grace_ns, source)
        eval_ns = time.time_ns()
        eval_id = f"eval-{datetime.fromtimestamp(eval_ns / NS):%Y%m%d-%H%M%S}"
        md_path, csv_path = write_reports(ev, eval_id, Path(args.reports_dir))
        written = 0
        if not args.no_write:
            written = write_results(client.write_api(write_options=SYNCHRONOUS), s.bucket, s.org, ev, eval_id, eval_ns)

    log.info("평가 %s: 구간 %s ~ %s, run %d개, 탐지 %d건, 데이터 출처 %s",
             eval_id, _time(window_from), _time(window_to), len(counted),
             sum(r.detections for r in ev.rows), source)
    if source == "mock":
        log.warning("mock 데이터로 계산한 결과입니다. 성능 결과가 아닙니다.")
    for r in ev.rows:
        log.info("  %-20s %-8s 탐지율 %6s  precision %6s  오탐 %3d  지연 p50 %6s ms  p95 %6s ms",
                 r.scenario, r.ruleset, _fmt(r.detection_rate, pct=True), _fmt(r.precision, pct=True),
                 r.fp_count, _fmt(r.latency_p50_ms, digits=0), _fmt(r.latency_p95_ms, digits=0))
    log.info("리포트 %s, %s%s", md_path, csv_path, f" / eval_result {written}건 저장" if written else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
