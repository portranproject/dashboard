import csv
import threading
import time
import uuid

import pytest

from evaluator.evaluate import (
    NS,
    AttackRun,
    Detection,
    detect_data_source,
    evaluate,
    fetch,
    match,
    non_attack_hours,
    percentile,
    write_reports,
    write_results,
)

T0 = 1_795_136_400 * NS  # 2026-11-20T10:00:00+09:00
GRACE = 5 * NS
STORM, ATTACH = "RRC_SIGNALING_STORM", "ABNORMAL_UE_ATTACH"


def run(run_id="r1", scenario=STORM, start_s=100, end_s=130, **params):
    return AttackRun(run_id, scenario, T0 + start_s * NS, T0 + end_s * NS, params)


def det(at_ns, attack_type=STORM, ruleset="full", event_id=None, evidence_lead_ms=100):
    return Detection(event_id or f"d{at_ns}", attack_type, ruleset, at_ns, at_ns - evidence_lead_ms * 1_000_000)


def window(seconds=3600):
    return T0, T0 + seconds * NS


def row(ev, scenario=STORM, ruleset="full"):
    return next(r for r in ev.rows if r.scenario == scenario and r.ruleset == ruleset)


# --------------------------------------------------------------------------- 매칭 경계 (CLAUDE.md 12절 4항)

def test_detection_exactly_at_grace_boundary_is_tp():
    r = run()
    ev = evaluate([r], [det(r.ts_end + GRACE)], *window(), GRACE)
    assert (row(ev).tp, row(ev).fn, row(ev).fp_count) == (1, 0, 0)


def test_detection_one_ns_after_grace_is_fp_and_run_is_fn():
    r = run()
    ev = evaluate([r], [det(r.ts_end + GRACE + 1)], *window(), GRACE)
    assert (row(ev).tp, row(ev).fn, row(ev).fp_count) == (0, 1, 1)
    assert row(ev).detection_rate == 0.0 and row(ev).precision == 0.0


def test_detection_at_ts_start_matches_but_one_ns_before_does_not():
    r = run()
    assert evaluate([r], [det(r.ts_start)], *window(), GRACE).rows[0].tp == 1
    ev = evaluate([r], [det(r.ts_start - 1)], *window(), GRACE)
    assert (row(ev).tp, row(ev).fp_count) == (0, 1)


def test_different_attack_type_does_not_match():
    r = run(scenario=STORM)
    ev = evaluate([r], [det(r.ts_start + NS, attack_type=ATTACH)], *window(), GRACE)
    assert (row(ev, STORM).tp, row(ev, STORM).fn) == (0, 1)
    assert row(ev, STORM).detections == 0
    assert (row(ev, ATTACH).runs, row(ev, ATTACH).fp_count, row(ev, ATTACH).precision) == (0, 1, 0.0)
    assert row(ev, ATTACH).detection_rate is None  # run이 없으면 탐지율은 계산할 수 없다


def test_many_detections_in_one_run_count_as_one_tp():
    r = run()
    dets = [det(r.ts_start + i * 10 * NS) for i in range(4)]
    ev = evaluate([r], dets, *window(), GRACE)
    assert (row(ev).runs, row(ev).tp, row(ev).detections, row(ev).matched, row(ev).fp_count) == (1, 1, 4, 4, 0)
    assert row(ev).precision == 1.0


def test_rulesets_are_evaluated_separately():
    r = run()
    ev = evaluate([r], [det(r.ts_start + NS, ruleset="full")], *window(), GRACE)
    assert (row(ev, ruleset="full").tp, row(ev, ruleset="kpm_only").fn) == (1, 1)
    assert row(ev, ruleset="kpm_only").precision is None  # 탐지가 없으면 precision은 계산할 수 없다


def test_detection_in_overlapping_runs_matches_both():
    a = run("a", start_s=100, end_s=130)
    b = run("b", start_s=132, end_s=160)  # a의 grace(135초) 안에서 b가 시작
    d = det(T0 + 133 * NS)
    assert match([a, b], [d], GRACE) == {"a": [d], "b": [d]}
    ev = evaluate([a, b], [d], *window(), GRACE)
    assert (row(ev).tp, row(ev).matched, row(ev).fp_count) == (2, 1, 0)


def test_latency_uses_first_matched_detection_per_run():
    r = run()
    first = det(r.ts_start + 300_000_000, evidence_lead_ms=100)    # 시작 0.3초 뒤, 근거 0.1초 전
    later = det(r.ts_start + 10 * NS, evidence_lead_ms=5000)
    ev = evaluate([r], [later, first], *window(), GRACE)
    assert row(ev).latency_p50_ms == pytest.approx(100)
    assert row(ev).onset_p50_ms == pytest.approx(300)


# --------------------------------------------------------------------------- 평가 구간 경계

def test_run_started_before_window_is_context_only():
    """구간 시작 전에 시작한 run은 세지 않지만, 그 run의 탐지가 오탐으로 세지지도 않는다."""
    before = run("before", start_s=-20, end_s=10)
    ev = evaluate([before], [det(T0 + 5 * NS)], *window(), GRACE)
    assert (row(ev).runs, row(ev).detections, row(ev).matched, row(ev).fp_count) == (0, 1, 1, 0)


def test_run_near_window_end_matches_detection_after_window():
    """구간 끝 직전 run의 탐지가 구간 밖(grace 안)에 와도 TP. 그 탐지는 precision 계산에서는 빠진다."""
    w_from, w_to = window(200)
    r = run(start_s=190, end_s=199)
    ev = evaluate([r], [det(T0 + 202 * NS)], w_from, w_to, GRACE)
    assert (row(ev).tp, row(ev).detections) == (1, 0)


def test_non_attack_hours_merges_overlaps_and_clips_to_window():
    w_from, w_to = window(3600)
    runs = [run("a", start_s=-60, end_s=60), run("b", start_s=600, end_s=1200),
            run("c", start_s=900, end_s=1500), run("d", start_s=3500, end_s=4000)]
    # 공격 시간: 0~60, 600~1500, 3500~3600 → 1060초
    assert non_attack_hours(w_from, w_to, runs) == pytest.approx((3600 - 1060) / 3600)


def test_fp_per_hour_uses_non_attack_time():
    w_from, w_to = window(7200)
    r = run(start_s=0, end_s=3600)  # 2시간 중 1시간 공격
    fps = [det(T0 + s * NS, attack_type=ATTACH) for s in (4000, 5000, 6000)]
    ev = evaluate([r], fps, w_from, w_to, GRACE)
    assert row(ev, ATTACH).fp_per_hour == pytest.approx(3.0)


# --------------------------------------------------------------------------- 기타

@pytest.mark.parametrize("values, p, expected", [
    ([], 50, None), ([7.0], 95, 7.0), ([1, 2, 3, 4], 50, 2.5), ([1, 2, 3, 4], 95, 3.85), ([10, 0], 0, 0),
])
def test_percentile(values, p, expected):
    assert percentile(values, p) == (pytest.approx(expected) if expected is not None else None)


def test_detect_data_source():
    assert detect_data_source([]) == "unknown"
    assert detect_data_source([run(generator="mock")]) == "mock"
    assert detect_data_source([run(generator="mock", replay={"file": "raw.jsonl"})]) == "mock"  # 재생한 mock도 mock
    assert detect_data_source([run(replay={"file": "raw.jsonl"})]) == "replay"
    assert detect_data_source([run()]) == "real"


def test_reports_mark_mock_and_have_all_rows(tmp_path):
    r = run(generator="mock")
    ev = evaluate([r], [det(r.ts_start + NS)], *window(), GRACE, data_source="mock")
    md, csv_path = write_reports(ev, "eval-test", tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "성능 결과가 아니다" in text and "r1" in text
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert [(x["scenario"], x["ruleset"]) for x in rows] == [(STORM, "full"), (STORM, "kpm_only")]
    assert rows[0]["data_source"] == "mock" and rows[0]["detection_rate"] == "1.0"
    assert rows[1]["precision"] == ""  # 계산할 수 없는 값은 빈칸


def test_mock_detection_rates_follow_config():
    """mock 생성기가 정한 탐지율이 evaluator로 다시 나오는지 (평가 로직과 mock의 정합성)."""
    from mock.generator import generate, load_config

    cfg = load_config()
    duration = 6 * 3600
    msgs = list(generate(cfg, "mixed", duration, seed=3, start_ns=T0))
    runs, dets = runs_and_detections(msgs)
    ev = evaluate(runs, dets, T0, T0 + duration * NS, GRACE, detect_data_source(runs))
    assert ev.data_source == "mock"
    for r in ev.rows:
        expected = cfg["attacks"][r.scenario]["rulesets"][r.ruleset]["detect_prob"]
        assert abs(r.detection_rate - expected) < 0.15, (r.scenario, r.ruleset, r.detection_rate)
    full = [r for r in ev.rows if r.ruleset == "full"]
    kpm = [r for r in ev.rows if r.ruleset == "kpm_only"]
    assert min(r.detection_rate for r in full) > max(r.detection_rate for r in kpm)
    assert max(r.latency_p95_ms for r in full) < min(r.latency_p50_ms for r in kpm)


def runs_and_detections(msgs):
    runs = [AttackRun(m["run_id"], m["scenario"], m["ts_start"], m["ts_end"], m["params"])
            for m in msgs if m["type"] == "attack_run"]
    dets = [Detection(m["event_id"], m["attack_type"], m["ruleset"], m["ts_detected"], m["ts_first_evidence"])
            for m in msgs if m["type"] == "detection"]
    return runs, dets


# --------------------------------------------------------------------------- InfluxDB (없으면 건너뜀)

@pytest.fixture(scope="module")
def temp_bucket():
    from common.config import ENV_PATH, InfluxSettings, influx_settings

    if not ENV_PATH.exists():
        pytest.skip(".env 없음")
    from influxdb_client import InfluxDBClient

    s = influx_settings()
    client = InfluxDBClient(url=s.url, token=s.token, org=s.org, timeout=5000, retries=False)
    try:
        if not client.ping():
            pytest.skip("InfluxDB에 접속할 수 없음")
    except Exception:
        pytest.skip("InfluxDB에 접속할 수 없음")
    bucket = client.buckets_api().create_bucket(bucket_name=f"portran_test_{uuid.uuid4().hex[:8]}", org=s.org)
    try:
        yield client, InfluxSettings(url=s.url, org=s.org, bucket=bucket.name, token=s.token)
    finally:
        client.buckets_api().delete_bucket(bucket)
        client.close()


def test_evaluate_from_influx_matches_direct_evaluation(temp_bucket, tmp_path):
    """mock → collector → InfluxDB → fetch → evaluate 결과가 메시지로 직접 계산한 결과와 같아야 한다."""
    from influxdb_client.client.write_api import SYNCHRONOUS

    from collector.collector import Collector, run as collector_run
    from collector.influx_writer import InfluxWriter
    from common.transport import FileTailSource, encode
    from mock.generator import generate, load_config

    client, settings = temp_bucket
    start = (time.time_ns() // NS - 7200) * NS
    duration = 1800
    msgs = list(generate(load_config(), "mixed", duration, seed=5, start_ns=start))
    src = tmp_path / "mock.jsonl"
    src.write_text("".join(encode(m) + "\n" for m in msgs), encoding="utf-8")
    writer = InfluxWriter(settings, timeout_ms=5000)
    collector = Collector(writer, tmp_path / "rec", batch_size=5000, max_pending=100_000)
    collector_run(collector, [FileTailSource(src, follow=False)], flush_interval_s=1.0, stop=threading.Event())
    collector.close()
    writer.close()

    w_from, w_to = start, start + duration * NS
    runs, dets = fetch(client.query_api(), settings.bucket, settings.org, w_from - 3600 * NS, w_to + 60 * NS)
    from_influx = evaluate(runs, dets, w_from, w_to, GRACE, detect_data_source(runs))
    direct = evaluate(*runs_and_detections(msgs), w_from, w_to, GRACE, "mock")
    assert from_influx.rows == direct.rows
    assert from_influx.data_source == "mock"

    n = write_results(client.write_api(write_options=SYNCHRONOUS), settings.bucket, settings.org,
                      from_influx, "eval-test", time.time_ns())
    flux = f'''from(bucket: "{settings.bucket}") |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "eval_result" and r._field == "detection_rate")'''
    stored = {(rec.values["scenario"], rec.values["ruleset"]): rec.get_value()
              for t in client.query_api().query(flux, org=settings.org) for rec in t.records}
    assert n == len(from_influx.rows) == len(stored)
    for r in from_influx.rows:
        assert stored[(r.scenario, r.ruleset)] == pytest.approx(r.detection_rate)
