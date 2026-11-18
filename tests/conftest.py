"""pytest 공통 설정.

InfluxDB·Grafana가 필요한 테스트는 서비스가 없으면 건너뛴다(로컬에서 Docker 없이도 돌리도록).
그런데 CI에서는 건너뛴 테스트도 통과로 보여서 통합 테스트가 실제로 돌았는지 알 수 없다.
PORTRAN_REQUIRE_SERVICES=1이면 건너뛴 테스트를 실패로 바꾼다. CI(.github/workflows/ci.yml)가 켠다.
"""
import os
import uuid

import pytest

REQUIRE_SERVICES = os.environ.get("PORTRAN_REQUIRE_SERVICES") == "1"


@pytest.fixture(scope="module")
def temp_bucket():
    """테스트 파일(module)마다 따로 만드는 임시 bucket — 끝나면 지운다. InfluxDB가 없거나 .env가 없으면 건너뛴다.
    파일마다 따로라서, bucket 전체 점 수를 세는 통합 테스트가 다른 파일의 데이터와 섞이지 않는다.
    돌려주는 값: (InfluxDBClient, InfluxSettings — bucket만 임시 bucket)."""
    from common.config import ENV_PATH, InfluxSettings, influx_settings

    if not ENV_PATH.exists():
        pytest.skip(".env 없음")
    from influxdb_client import InfluxDBClient

    s = influx_settings()
    client = InfluxDBClient(url=s.url, token=s.token, org=s.org, timeout=10000, retries=False)
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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if REQUIRE_SERVICES and report.skipped and not hasattr(report, "wasxfail"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"PORTRAN_REQUIRE_SERVICES=1인데 건너뜀 — {reason.removeprefix('Skipped: ')}"
