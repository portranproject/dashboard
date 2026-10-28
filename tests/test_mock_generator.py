import copy
import json
import statistics
from collections import Counter, defaultdict

import pytest

from common.schema import get_validator, message_time as emit_ns, validation_errors
from mock.generator import (
    NS,
    Run,
    Simulator,
    check_config,
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


@pytest.fixture(scope="module")
def long_mixed(cfg):
    """공격 유형마다 여러 번 나오도록 30분."""
    return list(generate(cfg, "mixed", 1800, seed=11, start_ns=START))


def runs_of(msgs):
    return [m for m in msgs if m["type"] == "attack_run"]


def metrics(msgs, kind, name=None):
    return [m for m in msgs if m["type"] == "metric" and m["kind"] == kind and (name is None or m["name"] == name)]


# --------------------------------------------------------------------------- 설정

def test_config_attack_types_match_schema(cfg):
    assert sorted(cfg["attacks"]) == sorted(get_validator().schema["$defs"]["attack_type"]["enum"])


def test_config_follows_paper_tables(cfg):
    # TeleRAN Table I(10개) → eKPM, Table II(14개) → 표준 KPM
    assert len(cfg["ekpm"]) == 10
    assert list(cfg["kpm"]) == [
        "RRC.ConnEstabAtt", "RRC.ConnEstabSucc", "RRC.ConnEstabFailCause", "RRC.RelWithoutSuspendConfig",
        "UECNTX.ConnEstabAtt", "UECNTX.ConnEstabSucc", "RRC.ReEstabAtt", "RRC.ReEstabSuccWithUeContext",
        "RRC.ResumeAtt", "RRC.ResumeSucc", "RRC.ConnMean", "RRC.ConnMax", "RRC.InactiveConnMean", "RRC.InactiveConnMax",
    ]


@pytest.mark.parametrize("break_config, message", [
    (lambda c: c["procedures"]["release"][0].update(typo=1), "모르는 항목"),
    (lambda c: c["procedures"]["release"][0].update(rrc="RRCNoSuchMessage"), "codes.rrc_msg_id에 없는"),
    (lambda c: c["procedures"]["release"][0]["set"].update(ue_rrc_state="RRC_SLEEPING"), "codes에 없습니다"),
    (lambda c: c["procedures"]["release"][0].update(count=["RRC.ConnMean"]), "CC 카운터가 아닙니다"),
    (lambda c: c["procedures"].pop("resume"), "정상 UE가 씀"),
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["inject"][0].update(procedure="nope"), "procedures에 없는 절차"),
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["inject"][0].update(rate_per_s=5), "하나만"),
    (lambda c: c["attacks"]["F1AP_MSG_TAMPER"]["override"].update(ue_cipher_alg="NEA9"), "codes에 없습니다"),
    (lambda c: c["attacks"]["RRC_SIGNALING_STORM"]["rulesets"].pop("kpm_only"), "모두 있어야"),
    (lambda c: c["attacks"]["F1AP_MSG_TAMPER"]["rulesets"]["full"]["evidence"][0].update(value=[0, 1]), "만족하지 않습니다"),
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
    validator = get_validator()
    invalid = [m for m in mixed if not validator.is_valid(m)]
    assert invalid == [], validation_errors(invalid[0])
    assert {m["type"] for m in mixed} == {"metric", "detection", "attack_run", "overhead"}
    assert {m["kind"] for m in mixed if m["type"] == "metric"} == {"ekpm", "kpm"}


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


def test_cli_writes_ten_minutes_to_file(cfg, tmp_path):
    out = tmp_path / "mock.jsonl"
    rc = main(["--duration", "600", "--seed", "7", "--speed", "0",
               "--start", "2026-11-20T10:00:00", "--out", f"file://{out}"])
    assert rc == 0
    msgs = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    validator = get_validator()
    assert all(validator.is_valid(m) for m in msgs)
    per_name = Counter(m["name"] for m in metrics(msgs, "kpm"))
    assert per_name == {name: 600 for name in cfg["kpm"]}  # 1초 주기, 10분


# --------------------------------------------------------------------------- 동작

def test_messages_are_in_time_order(mixed):
    times = [emit_ns(m) for m in mixed]
    assert times == sorted(times)


def test_kpm_reported_every_tick_at_period_end(cfg, mixed):
    ts = sorted({m["ts"] for m in metrics(mixed, "kpm")})
    tick = cfg["tick_s"] * NS
    assert ts == [START + (i + 1) * tick for i in range(TEN_MIN)]


def test_ekpm_values_use_code_tables(cfg, mixed):
    pool = cfg["rnti_pool"]
    for m in metrics(mixed, "ekpm"):
        assert m["src"] == "ebpf" and set(m["labels"]) == {"cell", "ue"}
        assert pool["first"] <= int(m["labels"]["ue"], 16) < pool["first"] + pool["size"]
        if m["name"] in cfg["codes"]:
            assert m["value"] in cfg["codes"][m["name"]].values(), m


def test_kpm_counters_match_ekpm_messages(cfg, mixed):
    """KPM과 eKPM은 같은 절차에서 나오므로 개수가 맞아야 한다."""
    rrc = {v: k for k, v in cfg["codes"]["rrc_msg_id"].items()}
    msg_counts = Counter(rrc[m["value"]] for m in metrics(mixed, "ekpm", "rrc_msg_id"))
    kpm_sum = defaultdict(float)
    for m in metrics(mixed, "kpm"):
        kpm_sum[m["name"]] += m["value"]
    assert kpm_sum["RRC.ConnEstabAtt"] == msg_counts["RRCSetupRequest"]
    assert kpm_sum["RRC.ConnEstabSucc"] == msg_counts["RRCSetupComplete"]
    assert kpm_sum["RRC.ResumeAtt"] == msg_counts["RRCResumeRequest"]
    assert kpm_sum["RRC.ReEstabAtt"] == msg_counts["RRCReestablishmentRequest"]


def test_connected_ue_statistics_are_sane(cfg):
    msgs = list(generate(cfg, "normal", 900, seed=2, start_ns=START))
    by = defaultdict(dict)
    for m in metrics(msgs, "kpm"):
        by[m["ts"]][m["name"]] = m["value"]
    n = cfg["subscribers"]["count"]
    for v in by.values():
        assert 0 <= v["RRC.ConnMean"] <= v["RRC.ConnMax"] <= n
        assert 0 <= v["RRC.InactiveConnMean"] <= v["RRC.InactiveConnMax"] <= n
    assert statistics.mean(v["RRC.ConnMean"] for v in by.values()) > 0.5  # 평소에 연결된 UE가 있다
    assert sum(v["RRC.ConnEstabFailCause"] for v in by.values()) == 0     # 평상시엔 연결 실패 없음


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


# --------------------------------------------------------------------------- 공격별로 보이는 것 (핵심 주장)

class Phases:
    """1초 구간을 '공격 한가운데' / '평상시'로 나눈다. 경계 구간과 공격 직후 10초는 뺀다
    (위조 연결이 공격이 끝난 뒤에도 몇 초 남아 있다가 해제되므로)."""

    def __init__(self, msgs, tick_ns=NS):
        self.runs = runs_of(msgs)
        self.tick = tick_ns

    def of_period(self, end_ns):
        start = end_ns - self.tick
        for r in self.runs:
            if r["ts_start"] <= start and end_ns <= r["ts_end"]:
                return r["scenario"]
            if start < r["ts_end"] + 10 * NS and end_ns > r["ts_start"]:
                return None
        return "normal"

    def of_time(self, ts):
        return self.of_period((ts // self.tick + 1) * self.tick)


def per_second(msgs, phases, pick):
    """phase별 초당 건수. pick(m)이 참인 eKPM 메시지를 센다."""
    seconds = Counter(phases.of_period(m["ts"]) for m in metrics(msgs, "kpm", "RRC.ConnEstabAtt"))
    hits = Counter(phases.of_time(m["ts"]) for m in metrics(msgs, "ekpm") if pick(m))
    return {p: hits[p] / seconds[p] for p in seconds if p}


def kpm_mean(msgs, phases, name):
    vals = defaultdict(list)
    for m in metrics(msgs, "kpm", name):
        vals[phases.of_period(m["ts"])].append(m["value"])
    return {p: statistics.mean(v) for p, v in vals.items() if p}


def code(cfg, name, value_name):
    return cfg["codes"][name][value_name]


def transient_ues(cfg, msgs):
    """5G-Spector의 transient UE: 인증 요청을 받고 응답 없이 해제된 RRC 연결. (연결 시작 시각, 수명 초) 목록."""
    rrc, nas = cfg["codes"]["rrc_msg_id"], cfg["codes"]["nas_msg_id"]
    answers = {nas["AuthenticationResponse"], nas["AuthenticationFailure"]}
    open_conn, out = {}, []
    for m in metrics(msgs, "ekpm"):
        ue, name, v = m["labels"]["ue"], m["name"], m["value"]
        if name == "rrc_msg_id" and v == rrc["RRCSetupRequest"]:
            open_conn[ue] = {"start": m["ts"], "auth": False, "answered": False}
        elif ue in open_conn and name == "nas_msg_id" and v == nas["AuthenticationRequest"]:
            open_conn[ue]["auth"] = True
        elif ue in open_conn and name == "nas_msg_id" and v in answers:
            open_conn[ue]["answered"] = True
        elif ue in open_conn and name == "rrc_msg_id" and v == rrc["RRCRelease"]:
            c = open_conn.pop(ue)
            if c["auth"] and not c["answered"]:
                out.append((c["start"], (m["ts"] - c["start"]) / NS))
    return out


def test_storm_is_bts_resource_depletion_kpm_sees_load_but_only_ekpm_sees_fake_ues(cfg, long_mixed):
    """5G-Spector의 BTS Resource Depletion: 위조 연결이 인증 요청까지 가서 몇 초 머문 뒤 해제된다."""
    ph = Phases(long_mixed)
    storm = "RRC_SIGNALING_STORM"
    att = kpm_mean(long_mixed, ph, "RRC.ConnEstabAtt")
    succ = kpm_mean(long_mixed, ph, "RRC.ConnEstabSucc")
    conn = kpm_mean(long_mixed, ph, "RRC.ConnMean")
    fail = kpm_mean(long_mixed, ph, "RRC.ConnEstabFailCause")
    # 표준 KPM에도 부하는 보인다: 연결 시도·성공이 늘고, 연결된 UE 수가 크게 오른다(자원 고갈)
    assert att[storm] > 20 * max(att["normal"], 0.05)
    assert succ[storm] > 20 * max(succ["normal"], 0.05)
    assert conn[storm] > conn["normal"] + 10
    assert fail[storm] == fail["normal"] == 0
    # 어떤 UE가 가짜인지(인증 요청에 응답 없이 몇 초 만에 사라진 연결)는 eKPM에만 있다
    transients = transient_ues(cfg, long_mixed)
    in_storm = [life for start, life in transients if ph.of_time(start) == storm]
    assert len(in_storm) > 100
    assert all(life < 10 for life in in_storm)
    assert not [t for t in transients if ph.of_time(t[0]) == "normal"]


def test_abnormal_attach_shows_in_ekpm_but_barely_in_kpm(cfg, long_mixed):
    ph = Phases(long_mixed)
    auth_fail = code(cfg, "nas_msg_id", "AuthenticationFailure")
    reject = code(cfg, "nas_msg_id", "RegistrationReject")
    fails = per_second(long_mixed, ph, lambda m: m["name"] == "nas_msg_id" and m["value"] in (auth_fail, reject))
    att = kpm_mean(long_mixed, ph, "RRC.ConnEstabAtt")
    attach = "ABNORMAL_UE_ATTACH"
    assert fails["normal"] == 0 and fails[attach] > 0.4
    assert att[attach] - att["normal"] < 1.0                  # 연결 시도는 초당 1건도 안 늘어난다
    # 시도마다 다른 신원(S-TMSI)
    s_tmsi = [m["value"] for m in metrics(long_mixed, "ekpm", "ue_s_tmsi") if ph.of_time(m["ts"]) == attach]
    assert len(set(s_tmsi)) > 0.8 * len(s_tmsi) > 5


def test_tamper_is_invisible_in_kpm_but_visible_in_ekpm(cfg, long_mixed):
    ph = Phases(long_mixed)
    nea0 = code(cfg, "ue_cipher_alg", "NEA0")
    smc = code(cfg, "rrc_msg_id", "SecurityModeCommand")
    tamper = "F1AP_MSG_TAMPER"
    # NEA0으로 바뀌는 순간(SecurityModeCommand와 같은 시각·UE)은 변조 구간에만 있다.
    # 이미 낮아진 UE가 공격 뒤 재개(resume)하며 NEA0을 다시 보고하는 건 실제와 같은 동작이라 따로 센다.
    smc_at = {(m["ts"], m["labels"]["ue"]) for m in metrics(long_mixed, "ekpm", "rrc_msg_id") if m["value"] == smc}
    downgrades = per_second(long_mixed, ph, lambda m: m["name"] == "ue_cipher_alg" and m["value"] == nea0
                            and (m["ts"], m["labels"]["ue"]) in smc_at)
    mismatches = per_second(long_mixed, ph,
                            lambda m: m["name"] == "ue_c_rnti" and m["value"] != int(m["labels"]["ue"], 16))
    assert downgrades["normal"] == 0 and downgrades[tamper] > 0
    assert mismatches["normal"] == 0 and mismatches[tamper] > 0
    for name, k in cfg["kpm"].items():
        if k["type"] == "CC" and not name.startswith("RRC.ReEstab"):
            mean = kpm_mean(long_mixed, ph, name)
            assert abs(mean[tamper] - mean["normal"]) < 0.3, name  # 연결·해제 카운터는 거의 그대로


def test_overhead_has_both_modes_and_ebpf_costs_more(mixed):
    cpu = defaultdict(list)
    for m in mixed:
        if m["type"] == "overhead":
            cpu[(m["node"], m["ebpf_on"])].append(m["cpu_pct"])
    for node in ("cu", "du"):
        assert statistics.mean(cpu[(node, True)]) > statistics.mean(cpu[(node, False)])


def test_attack_run_is_marked_as_mock(cfg, mixed):
    for r in runs_of(mixed):
        assert r["params"]["generator"] == "mock" and r["params"]["seed"] == 42
        assert r["params"]["inject"] == cfg["attacks"][r["scenario"]]["inject"]


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


def test_detection_targets_are_ues_involved_in_the_attack(cfg, mixed):
    runs = runs_of(mixed)
    labels_by_run = defaultdict(set)
    for m in metrics(mixed, "ekpm"):
        for r in runs:
            if r["ts_start"] <= m["ts"] <= r["ts_end"] + 2 * NS:
                labels_by_run[r["run_id"]].add(m["labels"]["ue"])
    checked = 0
    for d in (m for m in mixed if m["type"] == "detection"):
        run = next((r for r in runs if r["ts_start"] <= d["ts_detected"] <= r["ts_end"]
                    and r["scenario"] == d["attack_type"]), None)
        if run and "ue" in d["target"]:
            assert set(d["target"]["ue"]) <= labels_by_run[run["run_id"]]
            assert len(d["target"]["ue"]) <= cfg["detection"]["target_max_ues"]
            checked += 1
    assert checked > 0


def test_detection_times_are_consistent(cfg, mixed):
    runs = runs_of(mixed)
    for d in (m for m in mixed if m["type"] == "detection"):
        assert d["ts_first_evidence"] <= d["ts_detected"]
        run = next((r for r in runs if r["ts_start"] <= d["ts_detected"] < r["ts_end"]), None)
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
            # 오탐 근거 값은 임계값을 살짝 넘긴 값 (== 룰은 임계값 그대로)
            for ev in d["evidence"]:
                op, v, th = ev["op"], ev["value"], ev["threshold"]
                assert {">": v > th, ">=": v >= th, "<": v < th, "<=": v <= th, "==": v == th}[op]
    attack_hours = sum((r.ts_end - r.ts_start) for r in runs) / NS / 3600
    for ruleset, per_hour in cfg["false_positive"]["per_hour"].items():
        expected = per_hour * (24 - attack_hours)
        assert 0.5 * expected < fps[ruleset] < 1.5 * expected, (ruleset, fps[ruleset], expected)
    assert fps["kpm_only"] > fps["full"]


def test_rnti_pool_exhaustion_is_reported(cfg):
    small = copy.deepcopy(cfg)
    small["rnti_pool"]["size"] = 10
    runs = [Run("r1", "RRC_SIGNALING_STORM", START + 5 * NS, START + 25 * NS)]
    with pytest.raises(ValueError, match="rnti_pool"):
        Simulator(small, runs, 30, START, seed=1).run()
