"""실제 InfluxDB에 쓰고 읽어 보는 통합 테스트.

임시 bucket을 만들어 쓰고 끝나면 지운다. InfluxDB가 떠 있지 않거나 .env가 없으면 건너뛴다.
"""
import uuid
from collections import Counter

import pytest

from collector.collector import Collector
from collector.influx_writer import InfluxWriter
from common.config import ENV_PATH, InfluxSettings, influx_settings


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


def test_detection_samples_to_influx(temp_bucket, tmp_path):
    """탐지 쪽 샘플 32개 + SCHEMA.md의 kpm2·hello·f1_evt·overhead 예시를 /ingest 요청처럼 넣는다.
    InfluxDB가 필드 타입 충돌로 거부하거나(27_ §7.1), 다른 레코드끼리 같은 점에 덮어쓰면 실패한다."""
    import json
    import re
    from pathlib import Path

    client, settings = temp_bucket
    repo = Path(__file__).resolve().parent.parent
    examples = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", (repo / "schema" / "SCHEMA.md").read_text(encoding="utf-8"), re.S)]
    extra = [m for m in examples if m["type"] in ("kpm2", "hello", "f1_evt", "overhead")]

    writer = InfluxWriter(settings, timeout_ms=5000)
    collector = Collector(writer, tmp_path / "rec", batch_size=500, max_pending=100_000)
    expected = Counter()
    for path in sorted((repo / "tests" / "data" / "detection").glob("*.jsonl")):
        body = path.read_bytes()
        status, payload = collector.handle_request(body, "itest", "test")
        n = len(body.splitlines())
        assert (status, payload) == (200, {"accepted": n, "rejected": 0, "duplicates": 0}), path.name
        for line in body.decode("utf-8").splitlines():
            msg = json.loads(line)
            expected[msg["type"]] += 1
    body = "".join(json.dumps(m) + "\n" for m in extra).encode("utf-8")
    assert collector.handle_request(body, "itest", "test")[1]["accepted"] == 4
    expected.update(m["type"] for m in extra)
    expected["overhead_link"] += sum(len(m.get("link", [])) for m in extra if m["type"] == "overhead")
    # 탐지 쪽 실제 overhead 30줄 — 계측기 코어 수가 정수 0과 실수로 섞여 와도 타입 충돌이 없어야 한다
    sample = (repo / "tests" / "data" / "overhead" / "overhead-sample-3s-30.jsonl").read_bytes()
    assert collector.handle_request(sample, "itest", "test")[1] == {"accepted": 30, "rejected": 0, "duplicates": 0}
    expected["overhead"] += 30
    expected["overhead_link"] += 60
    # UDP·파일 입력처럼 handle → flush(배치)로도 쓴다(다음 구간의 overhead)
    overhead = next(m for m in examples if m["type"] == "overhead")
    later = {**overhead, "seq": overhead["seq"] + 1, "t_start_ms": overhead["t_end_ms"],
             "t_end_ms": overhead["t_end_ms"] + 3000, "link": []}
    collector.handle(json.dumps(later).encode("utf-8"), "test")
    collector.flush()
    assert collector.pending == []
    expected["overhead"] += 1
    collector.close()
    writer.close()

    one_field = {"alert": "severity", "evidence": "seq", "gap": "t_to", "kpm2": "n", "hello": "seq", "f1_evt": "msg",
                 "overhead": "seq", "overhead_link": "seq"}
    flux = f"""
    from(bucket: "{settings.bucket}")
      |> range(start: 2001-01-01T00:00:00Z, stop: now())
      |> filter(fn: (r) => {" or ".join(f'(r._measurement == "{m}" and r._field == "{f}")' for m, f in one_field.items())})
      |> group(columns: ["_measurement"])
      |> count()
    """
    counts = {r.values["_measurement"]: r.get_value() for t in client.query_api().query(flux, org=settings.org) for r in t.records}
    assert counts == dict(expected)  # 점 수 = 줄 수 → 덮어쓴 것 없음

    # 모든 경보 레코드에 세션이 붙었는지 (같은 요청 안의 evidence에서 알아냄)
    flux = f"""
    from(bucket: "{settings.bucket}")
      |> range(start: 2001-01-01T00:00:00Z, stop: now())
      |> filter(fn: (r) => r._measurement == "alert" and r._field == "session")
      |> group()
      |> count()
    """
    [record] = [r for t in client.query_api().query(flux, org=settings.org) for r in t.records]
    assert record.get_value() == expected["alert"]
