import copy
import json
import statistics
from collections import defaultdict

import pytest

from common.schema import get_validator, validation_errors
from mock.generator import (
    NS,
    Run,
    check_config,
    emit_ns,
    generate,
    load_config,
    main,
    plan_detections,
    schedule_runs,
)

START = 1_795_136_400 * NS  # 2026-11-20T10:00:00+09:00
TEN_MIN = 600


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def mixed(cfg):
    return list(generate(cfg, "mixed", TEN_MIN, seed=42, start_ns=START))


def runs_of(msgs):
    return [m for m in msgs if m["type"] == "attack_run"]


def active_run(runs, ts):
    return next((r for r in runs if r["ts_start"] <= ts < r["ts_end"]), None)


# --------------------------------------------------------------------------- 설정

def test_config_attack_types_match_schema(cfg):
    assert sorted(cfg["attacks"]) == sorted(get_validator().schema["$defs"]["attack_type"]["enum"])


@pytest.mark.parametrize("break_config, message", [
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["effects"].update(no_such_metric={"set": 1}), "metrics에 없는"),
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["effects"]["RRC.ConnMean"].update(set=1), "하나만"),
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["rulesets"].pop("kpm_only"), "모두 있어야"),
    (lambda c: c["attacks"]["F1AP_MSG_TAMPER"]["rulesets"]["full"]["evidence"][0].update(value=[1, 20]), "만족하지 않습니다"),
    (lambda c: c["schedule"].update(gap_s=[90, 40]), "최소, 최대"),
    (lambda c: c["attacks"].update(UNKNOWN_ATTACK=c["attacks"]["F1AP_MSG_TAMPER"]), "스키마에 없는"),
])
def test_config_mistakes_are_reported(cfg, break_config, message):
    broken = copy.deepcopy(cfg)
    break_config(broken)
    with pytest.raises(ValueError, match=message):
        check_config(broken)


# --------------------------------------------------------------------------- M2 완료 조건

def test_ten_minutes_all_messages_pass_schema(mixed):
    errors = [(m, validation_errors(m)) for m in mixed if validation_errors(m)]
    assert errors == []
    assert {m["type"] for m in mixed} == {"metric", "detection", "attack_run", "overhead"}


def test_same_seed_same_output(cfg, mixed):
    assert list(generate(cfg, "mixed", TEN_MIN, seed=42, start_ns=START)) == mixed


def test_different_seed_different_output(cfg, mixed):
    assert list(generate(cfg, "mixed", TEN_MIN, seed=43, start_ns=START)) != mixed


def test_same_seed_different_start_only_shifts_time(cfg, mixed):
    shift = 3600 * NS
    later = list(generate(cfg, "mixed", TEN_MIN, seed=42, start_ns=START + shift))
    assert len(later) == len(mixed)
    for a, b in zip(mixed, later):
        assert emit_ns(b) - emit_ns(a) == shift
        assert {k: v for k, v in a.items() if not k.startswith("ts")} == {k: v for k, v in b.items() if not k.startswith("ts")}


def test_cli_writes_ten_minutes_to_file(tmp_path):
    out = tmp_path / "mock.jsonl"
    rc = main(["--duration", "600", "--seed", "7", "--speed", "0",
               "--start", "2026-11-20T10:00:00", "--out", f"file://{out}"])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    msgs = [json.loads(line) for line in lines]
    assert all(get_validator().is_valid(m) for m in msgs)
    metric_ts = {m["ts"] for m in msgs if m["type"] == "metric"}
    assert len(metric_ts) == 600  # 1초 주기, 10분


# --------------------------------------------------------------------------- 동작

def test_messages_are_in_time_order(mixed):
    times = [emit_ns(m) for m in mixed]
    assert times == sorted(times)


def test_metrics_every_second(cfg, mixed):
    metric_ts = sorted({m["ts"] for m in mixed if m["type"] == "metric"})
    assert metric_ts[0] == START
    assert {b - a for a, b in zip(metric_ts, metric_ts[1:])} == {cfg["tick_s"] * NS}


def test_mixed_covers_every_attack_type(cfg, mixed):
    assert {r["scenario"] for r in runs_of(mixed)} == set(cfg["attacks"])


def test_single_scenario_and_normal(cfg):
    runs = schedule_runs(cfg, "RRC_SIGNALING_STORM", 1800, START, seed=1)
    assert runs and {r.attack_type for r in runs} == {"RRC_SIGNALING_STORM"}
    assert schedule_runs(cfg, "normal", 1800, START, seed=1) == []
    with pytest.raises(ValueError):
        schedule_runs(cfg, "NO_SUCH_ATTACK", 600, START, seed=1)


def test_runs_fit_in_duration_without_overlap(cfg):
    runs = schedule_runs(cfg, "mixed", 3600, START, seed=5)
    assert all(r.ts_start < r.ts_end for r in runs)
    assert all(a.ts_end < b.ts_start for a, b in zip(runs, runs[1:]))
    assert runs[-1].ts_end + cfg["schedule"]["gap_s"][0] * NS <= START + 3600 * NS


def test_attack_moves_ekpm_a_lot_but_kpm_only_a_little(cfg):
    """프로젝트 핵심 주장을 보여주는 데이터: 공격마다 eKPM 하나 이상은 크게, 표준 KPM은 20% 미만으로."""
    msgs = list(generate(cfg, "mixed", 3600, seed=11, start_ns=START))
    runs = runs_of(msgs)
    values = defaultdict(list)
    for m in msgs:
        if m["type"] == "metric":
            run = active_run(runs, m["ts"])
            values[(m["name"], run["scenario"] if run else None)].append(m["value"])
    metric_cfg = {m["name"]: m for m in cfg["metrics"]}

    for attack_type, attack in cfg["attacks"].items():
        big_ekpm = []
        for name, effect in attack["effects"].items():
            normal = statistics.mean(values[(name, None)])
            during = statistics.mean(values[(name, attack_type)])
            if metric_cfg[name]["kind"] == "kpm":
                assert abs(during - normal) / normal < 0.2, (attack_type, name, normal, during)
            elif abs(during - normal) > 10 * metric_cfg[name]["noise"]:
                big_ekpm.append(name)
        assert big_ekpm, f"{attack_type}: 크게 바뀌는 eKPM이 없습니다"


def test_overhead_has_both_modes_and_ebpf_costs_more(mixed):
    cpu = defaultdict(list)
    for m in mixed:
        if m["type"] == "overhead":
            cpu[(m["node"], m["ebpf_on"])].append(m["cpu_pct"])
    for node in ("cu", "du"):
        assert statistics.mean(cpu[(node, True)]) > statistics.mean(cpu[(node, False)])


def test_attack_run_is_marked_as_mock(mixed):
    for r in runs_of(mixed):
        assert r["params"]["generator"] == "mock" and r["params"]["seed"] == 42


# --------------------------------------------------------------------------- 탐지 이벤트

def synthetic_runs(n, attack_type, gap_s=120, length_s=30):
    return [Run(f"r{i}", attack_type, START + i * gap_s * NS, START + (i * gap_s + length_s) * NS) for i in range(n)]


@pytest.mark.parametrize("attack_type", ["RRC_SIGNALING_STORM", "ABNORMAL_UE_ATTACH", "F1AP_MSG_TAMPER"])
def test_detection_rate_and_delay_follow_config(cfg, attack_type):
    no_fp = copy.deepcopy(cfg)
    no_fp["false_positive"]["per_hour"] = {"full": 0, "kpm_only": 0}  # 오탐은 따로 테스트한다
    n = 400
    runs = synthetic_runs(n, attack_type)
    detections = plan_detections(no_fp, runs, n * 120, START, seed=3)
    by_run = {r.run_id: r for r in runs}
    first = {}
    for d in detections:
        run = next((r for r in runs if r.ts_start <= d["ts_detected"] <= r.ts_end + 20 * NS), None)
        if run and d["attack_type"] == attack_type:
            first.setdefault((d["ruleset"], run.run_id), d)

    for ruleset in ("full", "kpm_only"):
        rs = cfg["attacks"][attack_type]["rulesets"][ruleset]
        hits = [d for (r, _), d in first.items() if r == ruleset]
        assert abs(len(hits) / n - rs["detect_prob"]) < 0.08, (ruleset, len(hits) / n)
        lo, hi = rs["delay_ms"]
        for (r, run_id), d in first.items():
            if r == ruleset:
                delay_ms = (d["ts_detected"] - by_run[run_id].ts_start) / 1e6
                assert lo <= delay_ms <= hi

    full_max = cfg["attacks"][attack_type]["rulesets"]["full"]["delay_ms"][1]
    assert cfg["attacks"][attack_type]["rulesets"]["kpm_only"]["delay_ms"][0] > full_max


def test_detection_times_are_consistent(cfg, mixed):
    runs = runs_of(mixed)
    for d in (m for m in mixed if m["type"] == "detection"):
        assert d["ts_first_evidence"] <= d["ts_detected"]
        run = active_run(runs, d["ts_detected"])
        if run and run["scenario"] == d["attack_type"]:
            assert d["ts_first_evidence"] >= run["ts_start"]


def test_event_ids_unique_and_in_time_order(mixed):
    detections = [m for m in mixed if m["type"] == "detection"]
    ids = [d["event_id"] for d in detections]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_false_positives_only_outside_attacks(cfg):
    duration = 24 * 3600
    runs = schedule_runs(cfg, "mixed", duration, START, seed=9)
    quiet = cfg["false_positive"]["exclude_after_attack_s"] * NS
    detections = plan_detections(cfg, runs, duration, START, seed=9)
    fps = defaultdict(int)
    for d in detections:
        if not any(r.ts_start <= d["ts_detected"] <= r.ts_end + quiet for r in runs):
            fps[d["ruleset"]] += 1
            # 오탐 근거 값은 임계값을 살짝 넘긴 값
            for ev in d["evidence"]:
                assert ev["value"] > ev["threshold"] if ev["op"] in (">", ">=") else ev["value"] < ev["threshold"]
    attack_hours = sum((r.ts_end - r.ts_start) for r in runs) / NS / 3600
    for ruleset, per_hour in cfg["false_positive"]["per_hour"].items():
        expected = per_hour * (24 - attack_hours)
        assert 0.5 * expected < fps[ruleset] < 1.5 * expected, (ruleset, fps[ruleset], expected)
    assert fps["kpm_only"] > fps["full"]
