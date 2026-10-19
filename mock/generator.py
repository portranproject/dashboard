"""mock 생성기: 평상시·공격 구간 지표, 탐지 이벤트, 정답(attack_run), 수집 오버헤드 메시지를 만든다.

    python -m mock.generator --scenario mixed --duration 600 --seed 42 --out udp://127.0.0.1:9999
    python -m mock.generator --scenario RRC_SIGNALING_STORM --duration 120 --out file://recordings/mock.jsonl
    python -m mock.generator --speed 10

숫자는 전부 mock/scenarios.yaml에 있다. --seed와 --start가 같으면 출력이 같다.
메시지는 시뮬레이션 시각 순으로 나가며, --speed가 시뮬레이션 1초를 실제 몇 분의 1초로 보낼지 정한다.
"""
from __future__ import annotations

import argparse
import heapq
import logging
import math
import os
import random
import secrets
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml

from common.config import load_env
from common.schema import get_validator, validation_errors
from common.transport import encode, open_sink

NS = 1_000_000_000
MS = 1_000_000
RULESETS = ("full", "kpm_only")
SCENARIO_MODES = ("mixed", "normal")
DEFAULT_CONFIG = Path(__file__).with_name("scenarios.yaml")

log = logging.getLogger("mock")


# --------------------------------------------------------------------------- 설정

def load_config(path: str | Path = DEFAULT_CONFIG) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    check_config(cfg)
    return cfg


def check_config(cfg: dict) -> None:
    """설정 실수를 생성 전에 잡는다. 메시지 형식 자체는 스키마 검증이 따로 잡는다."""
    def fail(msg: str) -> None:
        raise ValueError(f"scenarios.yaml: {msg}")

    def check_range(where: str, r: Any) -> None:
        if not (isinstance(r, list) and len(r) == 2 and r[0] <= r[1]):
            fail(f"{where}는 [최소, 최대] 형식이어야 합니다: {r!r}")

    names = [m["name"] for m in cfg["metrics"]]
    if len(names) != len(set(names)):
        fail("metrics에 같은 이름이 있습니다")
    known_types = get_validator().schema["$defs"]["attack_type"]["enum"]
    check_range("schedule.gap_s", cfg["schedule"]["gap_s"])
    check_range("false_positive.excess", cfg["false_positive"]["excess"])

    for attack_type, attack in cfg["attacks"].items():
        where = f"attacks.{attack_type}"
        if attack_type not in known_types:
            fail(f"{where}: 스키마에 없는 공격 유형입니다 (스키마: {known_types})")
        check_range(f"{where}.duration_s", attack["duration_s"])
        for metric, effect in attack["effects"].items():
            if metric not in names:
                fail(f"{where}.effects: metrics에 없는 지표입니다: {metric}")
            if ("set" in effect) == ("add" in effect):
                fail(f"{where}.effects.{metric}: set과 add 중 하나만 써야 합니다")
        if set(attack["rulesets"]) != set(RULESETS):
            fail(f"{where}.rulesets에는 {RULESETS}가 모두 있어야 합니다")
        for ruleset, rs in attack["rulesets"].items():
            rs_where = f"{where}.rulesets.{ruleset}"
            check_range(f"{rs_where}.delay_ms", rs["delay_ms"])
            check_range(f"{rs_where}.latency_ms", rs["latency_ms"])
            if not rs["evidence"]:
                fail(f"{rs_where}.evidence가 비어 있습니다")
            for ev in rs["evidence"]:
                check_range(f"{rs_where}.evidence.value", ev["value"])
                if not _satisfies(ev["op"], ev["value"][0], ev["threshold"]) or not _satisfies(
                    ev["op"], ev["value"][1], ev["threshold"]
                ):
                    fail(f"{rs_where}.evidence({ev['metric']}): value 범위가 {ev['op']} {ev['threshold']}를 만족하지 않습니다")


def _satisfies(op: str, value: float, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    raise ValueError(f"mock은 >, >=, <, <= 연산자만 지원합니다: {op!r}")


def _rng(seed: int, stream: str) -> random.Random:
    # 용도별로 난수열을 나눠서, 예를 들어 지표를 하나 추가해도 공격 일정은 바뀌지 않게 한다.
    return random.Random(f"{seed}:{stream}")


# --------------------------------------------------------------------------- 공격 일정

@dataclass(frozen=True)
class Run:
    run_id: str
    attack_type: str
    ts_start: int
    ts_end: int


def scenario_pool(cfg: dict, scenario: str) -> list[str]:
    if scenario == "normal":
        return []
    if scenario == "mixed":
        return list(cfg["attacks"])
    if scenario not in cfg["attacks"]:
        raise ValueError(f"알 수 없는 시나리오: {scenario} (가능: {[*SCENARIO_MODES, *cfg['attacks']]})")
    return [scenario]


def schedule_runs(cfg: dict, scenario: str, duration_s: int, start_ns: int, seed: int) -> list[Run]:
    pool = scenario_pool(cfg, scenario)
    if not pool:
        return []
    sched = cfg["schedule"]
    rng = _rng(seed, "schedule")
    runs: list[Run] = []
    bag: list[str] = []
    t = float(sched["warmup_s"])
    while True:
        if not bag:
            bag = pool[:]
            rng.shuffle(bag)
        attack_type = bag.pop()
        start = t + rng.uniform(0, sched["start_jitter_ms"]) / 1000
        end = start + rng.uniform(*cfg["attacks"][attack_type]["duration_s"])
        gap = rng.uniform(*sched["gap_s"])
        if end + sched["gap_s"][0] > duration_s:
            return runs
        runs.append(
            Run(
                run_id=f"run-s{seed}-{len(runs) + 1:03d}",
                attack_type=attack_type,
                ts_start=start_ns + round(start * NS),
                ts_end=start_ns + round(end * NS),
            )
        )
        t = end + gap


def attack_run_message(cfg: dict, run: Run, seed: int) -> dict:
    params = dict(cfg["attacks"][run.attack_type]["params"])
    # mock 데이터임을 evaluator·리포트가 알 수 있도록 표시한다.
    params.update(generator="mock", seed=seed)
    return {
        "type": "attack_run",
        "run_id": run.run_id,
        "scenario": run.attack_type,
        "ts_start": run.ts_start,
        "ts_end": run.ts_end,
        "params": params,
    }


# --------------------------------------------------------------------------- 탐지 이벤트

def plan_detections(cfg: dict, runs: list[Run], duration_s: int, start_ns: int, seed: int) -> list[dict]:
    """공격별 탐지(TP 후보)와 공격 없는 구간의 오탐을 만든다. event_id는 탐지 시각 순으로 붙인다."""
    end_ns = start_ns + duration_s * NS
    detections: list[dict] = []
    for ruleset in RULESETS:
        # 공격마다 난수열을 따로 둬서, 한 공격의 탐지 여부가 다른 공격의 결과를 바꾸지 않게 한다.
        for run in runs:
            detections += _run_detections(cfg, run, ruleset, _rng(seed, f"detect:{ruleset}:{run.run_id}"))
        detections += _false_positives(cfg, runs, ruleset, duration_s, start_ns, _rng(seed, f"fp:{ruleset}"))

    detections = [d for d in detections if d["ts_detected"] < end_ns]
    detections.sort(key=lambda d: (d["ts_detected"], RULESETS.index(d["ruleset"])))
    for i, d in enumerate(detections, 1):
        d["event_id"] = f"det-s{seed}-{i:06d}"
    return detections


def _run_detections(cfg: dict, run: Run, ruleset: str, rng: random.Random) -> list[dict]:
    rs = cfg["attacks"][run.attack_type]["rulesets"][ruleset]
    if rng.random() >= rs["detect_prob"]:
        return []
    ts = run.ts_start + round(rng.uniform(*rs["delay_ms"]) * MS)
    out = []
    while ts <= run.ts_end or not out:
        latency = round(rng.uniform(*rs["latency_ms"]) * MS)
        out.append(_detection(cfg, run.attack_type, ruleset, ts, max(run.ts_start, ts - latency), rng, False))
        if not rs["repeat_interval_s"]:
            break
        ts += round(rs["repeat_interval_s"] * NS)
    return out


def _false_positives(
    cfg: dict, runs: list[Run], ruleset: str, duration_s: int, start_ns: int, rng: random.Random
) -> list[dict]:
    fp = cfg["false_positive"]
    per_hour = fp["per_hour"][ruleset]
    if per_hour <= 0:
        return []
    quiet_ns = round(fp["exclude_after_attack_s"] * NS)
    attack_types = list(cfg["attacks"])
    out = []
    t = 0.0
    while True:
        t += rng.expovariate(per_hour / 3600)
        if t >= duration_s:
            return out
        ts = start_ns + round(t * NS)
        attack_type = rng.choice(attack_types)
        latency = round(rng.uniform(*cfg["attacks"][attack_type]["rulesets"][ruleset]["latency_ms"]) * MS)
        if any(r.ts_start <= ts <= r.ts_end + quiet_ns for r in runs):
            continue
        out.append(_detection(cfg, attack_type, ruleset, ts, ts - latency, rng, True))


def _detection(
    cfg: dict, attack_type: str, ruleset: str, ts_detected: int, ts_first_evidence: int,
    rng: random.Random, false_positive: bool,
) -> dict:
    attack = cfg["attacks"][attack_type]
    rs = attack["rulesets"][ruleset]
    evidence = []
    for ev in rs["evidence"]:
        if false_positive:
            value = _just_past(ev["op"], ev["threshold"], rng.uniform(*cfg["false_positive"]["excess"]))
        else:
            value = rng.uniform(*ev["value"])
        evidence.append({
            "source": ev["source"], "metric": ev["metric"], "op": ev["op"],
            "value": round(value, 3), "threshold": ev["threshold"], "window_ms": ev["window_ms"],
        })
    return {
        "type": "detection",
        "event_id": "",  # plan_detections가 시각 순으로 채운다
        "ts_detected": ts_detected,
        "ts_first_evidence": ts_first_evidence,
        "attack_type": attack_type,
        "severity": rs["severity"],
        "ruleset": ruleset,
        "rule_id": rs["rule_id"],
        "rule_version": rs["rule_version"],
        "target": dict(attack["target"]),
        "evidence": evidence,
    }


def _just_past(op: str, threshold: float, excess: float) -> float:
    """오탐 근거 값: 임계값을 excess 비율만큼 살짝 넘긴 값."""
    step = abs(threshold) * excess or excess
    return threshold + step if op in (">", ">=") else threshold - step


# --------------------------------------------------------------------------- 주기 메시지 (지표, 오버헤드)

def tick_messages(cfg: dict, runs: list[Run], duration_s: int, start_ns: int, seed: int) -> Iterator[dict]:
    metric_rng = _rng(seed, "metrics")
    overhead_rng = _rng(seed, "overhead")
    phi = cfg["noise_persistence"]
    innovation = math.sqrt(1 - phi * phi)
    tick_ns = round(cfg["tick_s"] * NS)
    ov = cfg["overhead"]

    # 시계열마다 노이즈 상태(평균에서 벗어난 정도)를 유지한다: AR(1)
    series = []
    for m in cfg["metrics"]:
        for cell in cfg["topology"]["cells"]:
            for ue in cfg["topology"]["ues"] if m.get("per_ue") else [None]:
                labels = {"cell": cell} if ue is None else {"cell": cell, "ue": ue}
                series.append({"m": m, "labels": labels, "dev": 0.0})

    for i in range(round(duration_s / cfg["tick_s"])):
        ts = start_ns + i * tick_ns
        run = next((r for r in runs if r.ts_start <= ts < r.ts_end), None)
        attack = cfg["attacks"][run.attack_type] if run else None

        for s in series:
            m = s["m"]
            mean, sigma = m["baseline"], m["noise"]
            effect = attack["effects"].get(m["name"]) if attack and s["labels"]["cell"] == attack["target"]["cell"] else None
            if effect:
                mean = effect["set"] if "set" in effect else mean + effect["add"]
                sigma = effect.get("noise", sigma)
            s["dev"] = phi * s["dev"] + sigma * innovation * metric_rng.gauss(0, 1)
            # 항상 float로 낸다. InfluxDB는 같은 필드에 정수·실수가 섞이면 쓰기를 거부한다.
            value = float(min(max(mean + s["dev"], m.get("min", -math.inf)), m.get("max", math.inf)))
            yield {
                "type": "metric", "ts": ts, "src": m["src"], "node": m["node"], "kind": m["kind"],
                "name": m["name"], "value": float(round(value)) if m.get("integer") else round(value, 3),
                "unit": m["unit"], "labels": dict(s["labels"]),
            }

        if (i * cfg["tick_s"]) % ov["interval_s"] == 0:
            ebpf_on = (i * cfg["tick_s"] // ov["toggle_s"]) % 2 == 0
            for node, base in ov["nodes"].items():
                cpu = base["cpu_pct"] + (ov["ebpf_cost"]["cpu_pct"] if ebpf_on else 0)
                mem = base["mem_mb"] + (ov["ebpf_cost"]["mem_mb"] if ebpf_on else 0)
                yield {
                    "type": "overhead", "ts": ts, "node": node, "ebpf_on": ebpf_on,
                    "cpu_pct": round(max(0.0, cpu + overhead_rng.gauss(0, ov["noise"]["cpu_pct"])), 2),
                    "mem_mb": round(max(0.0, mem + overhead_rng.gauss(0, ov["noise"]["mem_mb"])), 1),
                }


# --------------------------------------------------------------------------- 전체 흐름

def emit_ns(msg: dict) -> int:
    """메시지가 실제로 나가는 시각 (attack_run은 공격 시작 시점에 낸다)."""
    return msg.get("ts") or msg.get("ts_detected") or msg["ts_start"]


def generate(cfg: dict, scenario: str, duration_s: int, seed: int, start_ns: int) -> Iterator[dict]:
    """모든 메시지를 emit_ns 순으로 낸다."""
    runs = schedule_runs(cfg, scenario, duration_s, start_ns, seed)
    events = [attack_run_message(cfg, r, seed) for r in runs]
    events += plan_detections(cfg, runs, duration_s, start_ns, seed)
    events.sort(key=emit_ns)
    return heapq.merge(tick_messages(cfg, runs, duration_s, start_ns, seed), events, key=emit_ns)


def send_all(messages: Iterable[dict], out: str, start_ns: int, speed: float, progress_s: int = 60) -> Counter:
    """메시지를 검증하고 보낸다. speed > 0이면 시뮬레이션 시각에 맞춰 기다린다 (0이면 기다리지 않음)."""
    validator = get_validator()
    counts: Counter = Counter()
    sink = open_sink(out)
    wall0 = time.monotonic()
    next_progress = progress_s
    try:
        for msg in messages:
            if not validator.is_valid(msg):
                raise RuntimeError(f"mock이 스키마에 맞지 않는 메시지를 만들었습니다: {validation_errors(msg)}\n{msg}")
            offset_s = (emit_ns(msg) - start_ns) / NS
            if speed > 0:
                delay = wall0 + offset_s / speed - time.monotonic()
                if delay > 0:
                    sink.flush()
                    time.sleep(delay)
            if offset_s >= next_progress:
                log.info("시뮬레이션 %ds 경과, 보낸 메시지 %d건", next_progress, sum(counts.values()))
                next_progress += progress_s
            sink.send(encode(msg))
            counts[msg["type"]] += 1
            if msg["type"] == "detection":
                counts[f"detection:{msg['ruleset']}"] += 1
    finally:
        sink.close()
    return counts


def parse_start(value: str) -> int:
    if value == "now":
        return time.time_ns() // NS * NS  # 초 단위로 맞춰 tick이 정각에 오도록
    # 시간대가 없으면 로컬 시각으로 본다 (evaluator의 --from/--to와 같은 규칙)
    return round(datetime.fromisoformat(value).timestamp()) * NS


def default_out() -> str:
    load_env()
    host = os.environ.get("COLLECTOR_UDP_HOST", "127.0.0.1")
    port = os.environ.get("COLLECTOR_UDP_PORT", "9999")
    return f"udp://{host}:{port}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mock.generator", description=__doc__.split("\n")[0])
    parser.add_argument("--scenario", default="mixed",
                        help="mixed(기본, 공격 유형 섞음) | normal(공격 없음) | 공격 유형 이름 하나")
    parser.add_argument("--duration", type=int, default=600, help="시뮬레이션 길이(초), 기본 600")
    parser.add_argument("--seed", type=int, default=None, help="난수 시드. 생략하면 무작위로 정하고 로그에 출력")
    parser.add_argument("--out", default=None,
                        help="udp://host:port 또는 file://path (기본: .env의 COLLECTOR_UDP_HOST:PORT)")
    parser.add_argument("--speed", type=float, default=1.0, help="배속. 10이면 10배 빠르게, 0이면 기다리지 않고 바로 출력")
    parser.add_argument("--start", default="now",
                        help="첫 메시지 시각. now(기본) 또는 2026-11-20T10:00:00 (시간대 없으면 로컬)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="설정 파일 (기본 mock/scenarios.yaml)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [mock] %(message)s", datefmt="%H:%M:%S")
    if args.duration <= 0 or args.speed < 0:
        parser.error("--duration은 양수, --speed는 0 이상이어야 합니다")

    cfg = load_config(args.config)
    try:
        scenario_pool(cfg, args.scenario)
    except ValueError as e:
        parser.error(str(e))
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    start_ns = parse_start(args.start)
    out = args.out or default_out()

    runs = schedule_runs(cfg, args.scenario, args.duration, start_ns, seed)
    log.info("scenario=%s duration=%ds seed=%d speed=%s start=%s out=%s",
             args.scenario, args.duration, seed, args.speed,
             datetime.fromtimestamp(start_ns / NS).isoformat(), out)
    for r in runs:
        log.info("  %s %-20s %+7.1fs ~ %+7.1fs", r.run_id, r.attack_type,
                 (r.ts_start - start_ns) / NS, (r.ts_end - start_ns) / NS)

    try:
        counts = send_all(generate(cfg, args.scenario, args.duration, seed, start_ns), out, start_ns, args.speed)
    except KeyboardInterrupt:
        log.info("중단됨 (seed=%d)", seed)
        return 130
    log.info("완료 seed=%d: %s", seed, ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
