"""실제 InfluxDB에 쓰고 읽어 보는 통합 테스트.

임시 bucket을 만들어 쓰고 끝나면 지운다. InfluxDB가 떠 있지 않거나 .env가 없으면 건너뛴다.
"""
import threading
import time
import uuid
from collections import Counter

import pytest

from collector.collector import Collector, run
from collector.influx_writer import InfluxWriter
from common.config import ENV_PATH, InfluxSettings, influx_settings
from common.transport import FileTailSource, encode
from mock.generator import NS, generate, load_config


@pytest.fixture(scope="module")
def temp_bucket():
    if not ENV_PATH.exists():
        pytest.skip(".env 없음")
    from influxdb_client import InfluxDBClient

    s = influx_settings()
    client = InfluxDBClient(url=s.url, token=s.token, org=s.org, timeout=3000, retries=False)
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


def test_mock_file_to_influx(temp_bucket, tmp_path):
    client, settings = temp_bucket
    start_ns = (time.time_ns() // NS - 3600) * NS  # 1시간 전부터 2분치
    msgs = list(generate(load_config(), "mixed", 120, seed=21, start_ns=start_ns))
    src = tmp_path / "mock.jsonl"
    src.write_text("".join(encode(m) + "\n" for m in msgs), encoding="utf-8")

    writer = InfluxWriter(settings, timeout_ms=5000)
    writer.check()
    collector = Collector(writer, tmp_path / "rec", batch_size=500, max_pending=100_000)
    run(collector, [FileTailSource(src, follow=False)], flush_interval_s=1.0, stop=threading.Event())
    collector.close()
    writer.close()
    assert collector.stats.stored == len(msgs) and collector.pending == []

    one_field = {"metric": "value", "detection": "event_id", "attack_run": "run_id", "overhead": "cpu_pct"}
    flux = f"""
    from(bucket: "{settings.bucket}")
      |> range(start: time(v: {start_ns - NS}), stop: time(v: {start_ns + 200 * NS}))
      |> filter(fn: (r) => {" or ".join(f'(r._measurement == "{m}" and r._field == "{f}")' for m, f in one_field.items())})
      |> group(columns: ["_measurement"])
      |> count()
    """
    counts = {r.values["_measurement"]: r.get_value() for t in client.query_api().query(flux, org=settings.org) for r in t.records}
    assert counts == {k: v for k, v in Counter(m["type"] for m in msgs).items()}

    # 타임스탬프가 ns 그대로 저장됐는지, 탐지 지연이 계산됐는지
    det = next(m for m in msgs if m["type"] == "detection")
    flux = f"""
    from(bucket: "{settings.bucket}")
      |> range(start: time(v: {start_ns - NS}), stop: time(v: {start_ns + 200 * NS}))
      |> filter(fn: (r) => r._measurement == "detection" and r._field == "latency_ms")
      |> filter(fn: (r) => r.ruleset == "{det['ruleset']}" and r.attack_type == "{det['attack_type']}" and r.rule_id == "{det['rule_id']}")
      |> group()
      |> first()
    """
    [record] = [r for t in client.query_api().query(flux, org=settings.org) for r in t.records]
    assert record.get_time().timestamp() * NS == pytest.approx(det["ts_detected"], abs=1000)
    assert record.get_value() == pytest.approx((det["ts_detected"] - det["ts_first_evidence"]) / 1e6)
    assert record.values["attack_type"] == det["attack_type"]
