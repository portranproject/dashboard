"""mock 생성기: eKPM·표준 KPM 지표, 탐지 이벤트, 정답(attack_run), 수집 오버헤드 메시지를 만든다.

    python -m mock.generator --scenario mixed --duration 600 --seed 42 --out udp://127.0.0.1:9999
    python -m mock.generator --scenario RRC_SIGNALING_STORM --duration 120 --out file://recordings/mock.jsonl
    python -m mock.generator --speed 10

지표는 TeleRAN 논문의 Table I(eKPM)·Table II(표준 KPM) 기준이다. UE들의 RRC/NAS 절차를 흉내 내고,
같은 절차에서 eKPM(메시지 처리마다)과 KPM(tick마다 집계)을 함께 뽑는다.
숫자는 전부 mock/scenarios.yaml에 있다. --seed와 --start가 같으면 출력이 같다.
메시지는 시뮬레이션 시각 순으로 나가며, --speed가 시뮬레이션 1초를 실제 몇 분의 1초로 보낼지 정한다.
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import logging
import os
import random
import secrets
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import yaml

from common.config import load_env
from common.schema import count_key, get_validator, message_time, validation_errors
from common.transport import encode, open_sink, paced

NS = 1_000_000_000
MS = 1_000_000
RULESETS = ("full", "kpm_only")
SCENARIO_MODES = ("mixed", "normal")
SUBSCRIBER_PROCEDURES = ("registration", "service", "release", "suspend", "resume", "reestablish")
STEP_KEYS = {"after_ms", "rrc", "nas", "set", "new_rnti", "new_s_tmsi", "report", "spoof_c_rnti", "count", "free_rnti"}
INJECT_WHO = ("new", "attacker", "connected")
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

    codes, ekpm, kpm = cfg["codes"], cfg["ekpm"], cfg["kpm"]
    counters = {name for name, k in kpm.items() if k["type"] == "CC"}
    for name in codes:
        if name not in ekpm:
            fail(f"codes.{name}: ekpm에 없는 지표입니다")
    for name, k in kpm.items():
        if k["type"] not in ("CC", "SI"):
            fail(f"kpm.{name}.type은 CC 또는 SI여야 합니다")
        if k["type"] == "SI" and (k["state"] not in codes["ue_rrc_state"] or k["stat"] not in ("mean", "max")):
            fail(f"kpm.{name}: state는 codes.ue_rrc_state의 이름, stat은 mean 또는 max여야 합니다")

    def check_set(where: str, values: dict) -> None:
        for key, value in values.items():
            if key not in codes or value not in codes[key]:
                fail(f"{where}: {key}={value}는 codes에 없습니다")

    for proc_name, steps in cfg["procedures"].items():
        for i, step in enumerate(steps):
            where = f"procedures.{proc_name}[{i}]"
            if set(step) - STEP_KEYS:
                fail(f"{where}: 모르는 항목 {sorted(set(step) - STEP_KEYS)}")
            check_range(f"{where}.after_ms", step.get("after_ms"))
            if "rrc" in step and step["rrc"] not in codes["rrc_msg_id"]:
                fail(f"{where}: codes.rrc_msg_id에 없는 메시지 {step['rrc']}")
            if "nas" in step and step["nas"] not in codes["nas_msg_id"]:
                fail(f"{where}: codes.nas_msg_id에 없는 메시지 {step['nas']}")
            check_set(where, step.get("set", {}))
            for key in step.get("report", []):
                if key not in ekpm:
                    fail(f"{where}.report: ekpm에 없는 지표 {key}")
            for name in step.get("count", []):
                if name not in counters:
                    fail(f"{where}.count: kpm의 CC 카운터가 아닙니다: {name}")
    for name in SUBSCRIBER_PROCEDURES:
        if name not in cfg["procedures"]:
            fail(f"procedures.{name}이 필요합니다 (정상 UE가 씀)")

    sub = cfg["subscribers"]
    for key in ("first_registration_s", "connected_s", "idle_s"):
        check_range(f"subscribers.{key}", sub[key])
    check_range("schedule.gap_s", cfg["schedule"]["gap_s"])
    check_range("false_positive.excess", cfg["false_positive"]["excess"])

    known_types = get_validator().schema["$defs"]["attack_type"]["enum"]
    for attack_type, attack in cfg["attacks"].items():
        where = f"attacks.{attack_type}"
        if attack_type not in known_types:
            fail(f"{where}: 스키마에 없는 공격 유형입니다 (스키마: {known_types})")
        check_range(f"{where}.duration_s", attack["duration_s"])
        check_set(f"{where}.override", attack.get("override", {}))
        for inj in attack["inject"]:
            if inj["procedure"] not in cfg["procedures"]:
                fail(f"{where}.inject: procedures에 없는 절차 {inj['procedure']}")
            if inj["who"] not in INJECT_WHO:
                fail(f"{where}.inject.who는 {INJECT_WHO} 중 하나여야 합니다")
            if ("rate_per_s" in inj) == ("interval_s" in inj):
                fail(f"{where}.inject: rate_per_s와 interval_s 중 하나만 써야 합니다")
            check_range(f"{where}.inject.first_at_ms", inj["first_at_ms"])
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
                if not all(_satisfies(ev["op"], v, ev["threshold"]) for v in ev["value"]):
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
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    raise ValueError(f"알 수 없는 연산자: {op!r}")


def _rng(seed: int, stream: str) -> random.Random:
    # 용도별로 난수열을 나눠서, 예를 들어 공격 하나를 바꿔도 정상 UE의 행동이나 공격 일정은 바뀌지 않게 한다.
    return random.Random(f"{seed}:{stream}")


def _ns(seconds: float) -> int:
    return round(seconds * NS)


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
        runs.append(Run(f"run-s{seed}-{len(runs) + 1:03d}", attack_type, start_ns + _ns(start), start_ns + _ns(end)))
        t = end + gap


def attack_run_message(cfg: dict, run: Run, seed: int) -> dict:
    attack = cfg["attacks"][run.attack_type]
    # mock이 실제로 한 일을 남기고, mock 데이터임을 evaluator·리포트가 알 수 있도록 표시한다.
    params: dict[str, Any] = {"inject": attack["inject"]}
    if "override" in attack:
        params["override"] = attack["override"]
    params.update(generator="mock", seed=seed)
    return {
        "type": "attack_run",
        "run_id": run.run_id,
        "scenario": run.attack_type,
        "ts_start": run.ts_start,
        "ts_end": run.ts_end,
        "params": params,
    }


# --------------------------------------------------------------------------- UE 절차 시뮬레이션 (eKPM, KPM)

@dataclass(eq=False)
class UE:
    """UE 하나(정상 가입자, 공격자, 가짜 UE)의 상태. 지표 라벨은 현재 C-RNTI다."""
    kind: str
    rng: random.Random
    rnti: int | None = None
    state: dict[str, Any] = field(default_factory=dict)  # eKPM 이름 → codes의 이름 또는 식별자 값
    sent: dict[str, Any] = field(default_factory=dict)   # 현재 C-RNTI 라벨로 마지막에 낸 값
    busy: bool = False

    @property
    def label(self) -> str:
        return f"0x{self.rnti:04x}"


class _Occupancy:
    """특정 RRC 상태에 있는 UE 수를 시간 가중 평균·최대로 tick마다 모은다 (KPM SI)."""

    def __init__(self, start_ns: int, tick_ns: int, n_ticks: int):
        self.start, self.tick, self.n = start_ns, tick_ns, n_ticks
        self.count, self.last = 0, start_ns
        self.area = [0.0] * n_ticks
        self.peak = [0] * n_ticks

    def change(self, t: int, delta: int) -> None:
        self.advance(t)
        self.count += delta
        i = (t - self.start) // self.tick
        if 0 <= i < self.n:
            self.peak[i] = max(self.peak[i], self.count)

    def advance(self, t: int) -> None:
        while self.last < t:
            i = (self.last - self.start) // self.tick
            if i >= self.n:
                break
            seg_end = min(t, self.start + (i + 1) * self.tick)
            self.area[i] += self.count * (seg_end - self.last)
            self.peak[i] = max(self.peak[i], self.count)
            self.last = seg_end
        self.last = max(self.last, t)


class Simulator:
    def __init__(self, cfg: dict, runs: list[Run], duration_s: int, start_ns: int, seed: int):
        self.cfg, self.runs, self.seed = cfg, runs, seed
        self.start_ns = start_ns
        self.end_ns = start_ns + duration_s * NS
        self.tick_ns = _ns(cfg["tick_s"])
        self.n_ticks = round(duration_s / cfg["tick_s"])
        self.codes = cfg["codes"]
        self._events: list = []
        self._seq = itertools.count()
        pool = cfg["rnti_pool"]
        self._free_rnti = deque(range(pool["first"], pool["first"] + pool["size"]))
        self.ekpm: list[dict] = []
        self.counts = {n: [0] * self.n_ticks for n, k in cfg["kpm"].items() if k["type"] == "CC"}
        si_states = {k["state"] for k in cfg["kpm"].values() if k["type"] == "SI"}
        self.occupancy = {s: _Occupancy(start_ns, self.tick_ns, self.n_ticks) for s in si_states}
        self.involved: dict[str, list[tuple[int, str]]] = {r.run_id: [] for r in runs}
        self._involved_seen: set[tuple[str, str]] = set()
        self.subscribers: list[UE] = []

    def at(self, t: int, fn: Callable, *args) -> None:
        heapq.heappush(self._events, (t, next(self._seq), fn, args))

    def run(self) -> "Simulator":
        self._schedule_subscribers()
        self._schedule_attacks()
        while self._events and self._events[0][0] < self.end_ns:
            t, _, fn, args = heapq.heappop(self._events)
            fn(t, *args)
        for occ in self.occupancy.values():
            occ.advance(self.end_ns)
        return self

    # ------------------------------------------------------------------ 절차 실행

    def start_procedure(self, t: int, ue: UE, name: str, on_done: Callable | None = None, run: Run | None = None) -> None:
        ue.busy = True
        steps = self.cfg["procedures"][name]
        self.at(t + round(ue.rng.uniform(*steps[0]["after_ms"]) * MS), self._step, ue, steps, 0, on_done, run)

    def _step(self, t: int, ue: UE, steps: list[dict], i: int, on_done: Callable | None, run: Run | None) -> None:
        self._apply(t, ue, steps[i], run)
        if i + 1 < len(steps):
            delay = round(ue.rng.uniform(*steps[i + 1]["after_ms"]) * MS)
            self.at(t + delay, self._step, ue, steps, i + 1, on_done, run)
            return
        ue.busy = False
        if on_done:
            on_done(t, ue)

    def _apply(self, t: int, ue: UE, step: dict, run: Run | None) -> None:
        if step.get("new_rnti"):
            if not self._free_rnti:
                raise ValueError("rnti_pool이 모자랍니다. scenarios.yaml의 rnti_pool.size를 늘리세요")
            ue.rnti = self._free_rnti.popleft()
            ue.sent = {}
            ue.state["ue_c_rnti"] = ue.rnti
            self._emit(t, ue, "ue_c_rnti", ue.rnti)
        if run is not None:
            self._involve(run, t, ue)
        if step.get("new_s_tmsi"):
            ue.state["ue_s_tmsi"] = ue.rng.getrandbits(self.cfg["subscribers"]["s_tmsi_bits"])
            self._emit(t, ue, "ue_s_tmsi", ue.state["ue_s_tmsi"])
        if "rrc" in step:
            self._emit(t, ue, "rrc_msg_id", self.codes["rrc_msg_id"][step["rrc"]])
        if "nas" in step:
            self._emit(t, ue, "nas_msg_id", self.codes["nas_msg_id"][step["nas"]])

        values = dict(step.get("set", {}))
        tamper = self._active_override(t, values)
        if tamper:
            tamper_run, override = tamper
            values.update({k: v for k, v in override.items() if k in values})
            self._involve(tamper_run, t, ue)
        for key, value in values.items():
            old = ue.state.get(key)
            ue.state[key] = value
            if key == "ue_rrc_state":
                for s, occ in self.occupancy.items():
                    if old == s:
                        occ.change(t, -1)
                    if value == s:
                        occ.change(t, +1)
            if ue.sent.get(key) != value:
                self._emit(t, ue, key, self.codes[key][value])
        for key in step.get("report", []):
            if key in ue.state:
                value = ue.state[key]
                self._emit(t, ue, key, self.codes[key][value] if key in self.codes else value)
        if step.get("spoof_c_rnti"):
            pool = self.cfg["rnti_pool"]
            fake = pool["first"] + (ue.rnti - pool["first"] + ue.rng.randrange(1, pool["size"])) % pool["size"]
            self._emit(t, ue, "ue_c_rnti", fake)
        for name in step.get("count", []):
            i = (t - self.start_ns) // self.tick_ns
            if 0 <= i < self.n_ticks:
                self.counts[name][i] += 1
        if step.get("free_rnti"):
            self._free_rnti.append(ue.rnti)

    def _emit(self, t: int, ue: UE, name: str, value: float) -> None:
        ue.sent[name] = ue.state.get(name)
        self.ekpm.append({
            "type": "metric", "ts": t, "src": "ebpf", "node": self.cfg["node"], "kind": "ekpm",
            "name": name, "value": float(value), "unit": self.cfg["ekpm"][name]["unit"],
            "labels": {"cell": self.cfg["cell"], "ue": ue.label},
        })

    def _active_override(self, t: int, values: dict) -> tuple[Run, dict] | None:
        for r in self.runs:
            override = self.cfg["attacks"][r.attack_type].get("override")
            if override and r.ts_start <= t < r.ts_end and any(k in values for k in override):
                return r, override
        return None

    def _involve(self, run: Run, t: int, ue: UE) -> None:
        if ue.rnti is not None and (run.run_id, ue.label) not in self._involved_seen:
            self._involved_seen.add((run.run_id, ue.label))
            self.involved[run.run_id].append((t, ue.label))

    # ------------------------------------------------------------------ 정상 UE

    def _schedule_subscribers(self) -> None:
        sub = self.cfg["subscribers"]
        for i in range(sub["count"]):
            ue = UE("subscriber", _rng(self.seed, f"ue:{i}"))
            self.subscribers.append(ue)
            self.at(self.start_ns + _ns(ue.rng.uniform(*sub["first_registration_s"])), self._begin, ue, "registration")

    def _begin(self, t: int, ue: UE, name: str) -> None:
        if ue.busy:  # 공격이 끼어들어 다른 절차가 진행 중
            self.at(t + self.cfg["subscribers"]["busy_retry_ms"] * MS, self._begin, ue, name)
            return
        self.start_procedure(t, ue, name, on_done=self._next_for_subscriber)

    def _next_for_subscriber(self, t: int, ue: UE) -> None:
        sub = self.cfg["subscribers"]
        rng = ue.rng
        state = ue.state.get("ue_rrc_state")
        if state == "RRC_CONNECTED":
            stay = rng.uniform(*sub["connected_s"])
            until_reestablish = rng.expovariate(sub["reestablish_per_min"] / 60) if sub["reestablish_per_min"] > 0 else stay
            if until_reestablish < stay:
                self.at(t + _ns(until_reestablish), self._begin, ue, "reestablish")
            else:
                name = "suspend" if rng.random() < sub["suspend_prob"] else "release"
                self.at(t + _ns(stay), self._begin, ue, name)
        elif state == "RRC_INACTIVE":
            self.at(t + _ns(rng.uniform(*sub["idle_s"])), self._begin, ue, "resume")
        else:
            self.at(t + _ns(rng.uniform(*sub["idle_s"])), self._begin, ue, "service")

    # ------------------------------------------------------------------ 공격

    def _schedule_attacks(self) -> None:
        for run in self.runs:
            rng = _rng(self.seed, f"attack:{run.run_id}")
            for inj in self.cfg["attacks"][run.attack_type]["inject"]:
                attacker = UE("attacker", rng) if inj["who"] == "attacker" else None
                t = run.ts_start + round(rng.uniform(*inj["first_at_ms"]) * MS)
                while t < run.ts_end:
                    self.at(t, self._inject, run, inj, attacker, rng)
                    gap = rng.expovariate(inj["rate_per_s"]) if "rate_per_s" in inj else rng.uniform(*inj["interval_s"])
                    t += _ns(gap)

    def _inject(self, t: int, run: Run, inj: dict, attacker: UE | None, rng: random.Random) -> None:
        if inj["who"] == "new":
            ue = UE("fake", rng)
        elif inj["who"] == "attacker":
            if attacker.busy:
                return
            ue = attacker
        else:
            victims = [u for u in self.subscribers if u.state.get("ue_rrc_state") == "RRC_CONNECTED" and not u.busy]
            if not victims:
                return
            ue = rng.choice(victims)
        self.start_procedure(t, ue, inj["procedure"], run=run)

    # ------------------------------------------------------------------ KPM 메시지

    def kpm_messages(self) -> list[dict]:
        out = []
        for i in range(self.n_ticks):
            ts = self.start_ns + (i + 1) * self.tick_ns  # 구간 끝 시각에 그 구간 값을 보고
            for name, k in self.cfg["kpm"].items():
                if k["type"] == "CC":
                    value = float(self.counts[name][i])
                else:
                    occ = self.occupancy[k["state"]]
                    value = occ.area[i] / self.tick_ns if k["stat"] == "mean" else float(occ.peak[i])
                out.append({
                    "type": "metric", "ts": ts, "src": "kpm", "node": self.cfg["node"], "kind": "kpm",
                    "name": name, "value": round(value, 3), "unit": k["unit"], "labels": {"cell": self.cfg["cell"]},
                })
        return out


def overhead_messages(cfg: dict, duration_s: int, start_ns: int, seed: int) -> list[dict]:
    rng = _rng(seed, "overhead")
    ov = cfg["overhead"]
    out = []
    for i in range(round(duration_s / cfg["tick_s"])):
        elapsed = i * cfg["tick_s"]
        if elapsed % ov["interval_s"]:
            continue
        ebpf_on = (elapsed // ov["toggle_s"]) % 2 == 0
        for node, base in ov["nodes"].items():
            cpu = base["cpu_pct"] + (ov["ebpf_cost"]["cpu_pct"] if ebpf_on else 0)
            mem = base["mem_mb"] + (ov["ebpf_cost"]["mem_mb"] if ebpf_on else 0)
            out.append({
                "type": "overhead", "ts": start_ns + _ns(elapsed), "node": node, "ebpf_on": ebpf_on,
                "cpu_pct": round(max(0.0, cpu + rng.gauss(0, ov["noise"]["cpu_pct"])), 2),
                "mem_mb": round(max(0.0, mem + rng.gauss(0, ov["noise"]["mem_mb"])), 1),
            })
    return out


# --------------------------------------------------------------------------- 탐지 이벤트

def plan_detections(cfg: dict, runs: list[Run], duration_s: int, start_ns: int, seed: int,
                    involved: dict[str, list[tuple[int, str]]] | None = None) -> list[dict]:
    """공격별 탐지(TP 후보)와 공격 없는 구간의 오탐을 만든다. event_id는 탐지 시각 순으로 붙인다.
    involved(run_id → [(시각, UE 라벨)])가 있으면 탐지 시각까지 연루된 UE를 target.ue에 넣는다."""
    end_ns = start_ns + duration_s * NS
    involved = involved or {}
    detections: list[dict] = []
    for ruleset in RULESETS:
        # 공격마다 난수열을 따로 둬서, 한 공격의 탐지 여부가 다른 공격의 결과를 바꾸지 않게 한다.
        for run in runs:
            rng = _rng(seed, f"detect:{ruleset}:{run.run_id}")
            detections += _run_detections(cfg, run, ruleset, rng, involved.get(run.run_id, []))
        detections += _false_positives(cfg, runs, ruleset, duration_s, start_ns, _rng(seed, f"fp:{ruleset}"))

    detections = [d for d in detections if d["ts_detected"] < end_ns]
    detections.sort(key=lambda d: (d["ts_detected"], RULESETS.index(d["ruleset"])))
    for i, d in enumerate(detections, 1):
        d["event_id"] = f"det-s{seed}-{i:06d}"
    return detections


def _run_detections(cfg: dict, run: Run, ruleset: str, rng: random.Random,
                    involved: list[tuple[int, str]]) -> list[dict]:
    rs = cfg["attacks"][run.attack_type]["rulesets"][ruleset]
    if rng.random() >= rs["detect_prob"]:
        return []
    ts = run.ts_start + round(rng.uniform(*rs["delay_ms"]) * MS)
    out = []
    while ts <= run.ts_end or not out:
        latency = round(rng.uniform(*rs["latency_ms"]) * MS)
        ues = [label for t, label in involved if t <= ts][: cfg["detection"]["target_max_ues"]]
        out.append(_detection(cfg, run.attack_type, ruleset, ts, max(run.ts_start, ts - latency), rng, False, ues))
        if not rs["repeat_interval_s"]:
            break
        ts += _ns(rs["repeat_interval_s"])
    return out


def _false_positives(
    cfg: dict, runs: list[Run], ruleset: str, duration_s: int, start_ns: int, rng: random.Random
) -> list[dict]:
    fp = cfg["false_positive"]
    per_hour = fp["per_hour"][ruleset]
    if per_hour <= 0:
        return []
    quiet_ns = _ns(fp["exclude_after_attack_s"])
    attack_types = list(cfg["attacks"])
    out = []
    t = 0.0
    while True:
        t += rng.expovariate(per_hour / 3600)
        if t >= duration_s:
            return out
        ts = start_ns + _ns(t)
        attack_type = rng.choice(attack_types)
        latency = round(rng.uniform(*cfg["attacks"][attack_type]["rulesets"][ruleset]["latency_ms"]) * MS)
        if any(r.ts_start <= ts <= r.ts_end + quiet_ns for r in runs):
            continue
        out.append(_detection(cfg, attack_type, ruleset, ts, ts - latency, rng, True, []))


def _detection(
    cfg: dict, attack_type: str, ruleset: str, ts_detected: int, ts_first_evidence: int,
    rng: random.Random, false_positive: bool, ues: list[str],
) -> dict:
    rs = cfg["attacks"][attack_type]["rulesets"][ruleset]
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
    target: dict[str, Any] = {"node": cfg["node"], "cell": cfg["cell"]}
    if ues:
        target["ue"] = ues
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
        "target": target,
        "evidence": evidence,
    }


def _just_past(op: str, threshold: float, excess: float) -> float:
    """오탐 근거 값: 임계값을 excess 비율만큼 살짝 넘긴 값. ==면 임계값, !=면 1 다른 값."""
    if op == "==":
        return threshold
    if op == "!=":
        return threshold + 1
    step = abs(threshold) * excess or excess
    return threshold + step if op in (">", ">=") else threshold - step


# --------------------------------------------------------------------------- 전체 흐름

def generate(cfg: dict, scenario: str, duration_s: int, seed: int, start_ns: int) -> Iterator[dict]:
    """모든 메시지를 시각 순으로 낸다 (attack_run은 공격 시작 시점, detection은 탐지 시점)."""
    runs = schedule_runs(cfg, scenario, duration_s, start_ns, seed)
    sim = Simulator(cfg, runs, duration_s, start_ns, seed).run()
    events = [attack_run_message(cfg, r, seed) for r in runs]
    events += plan_detections(cfg, runs, duration_s, start_ns, seed, sim.involved)
    events.sort(key=message_time)
    return heapq.merge(sim.ekpm, sim.kpm_messages(), overhead_messages(cfg, duration_s, start_ns, seed),
                       events, key=message_time)


def send_all(messages: Iterable[dict], out: str, start_ns: int, speed: float, progress_s: int = 60) -> Counter:
    """메시지를 검증하고 보낸다. speed > 0이면 시뮬레이션 시각에 맞춰 기다린다 (0이면 기다리지 않음)."""
    validator = get_validator()
    counts: Counter = Counter()
    sink = open_sink(out)
    next_progress = progress_s
    try:
        for msg in paced(messages, message_time, start_ns, speed, before_sleep=sink.flush):
            if not validator.is_valid(msg):
                raise RuntimeError(f"mock이 스키마에 맞지 않는 메시지를 만들었습니다: {validation_errors(msg)}\n{msg}")
            if (message_time(msg) - start_ns) / NS >= next_progress:
                log.info("시뮬레이션 %ds 경과, 보낸 메시지 %d건", next_progress, sum(counts.values()))
                next_progress += progress_s
            sink.send(encode(msg))
            counts[count_key(msg)] += 1
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
    return f"udp://{os.environ['COLLECTOR_UDP_HOST']}:{os.environ['COLLECTOR_UDP_PORT']}"


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
