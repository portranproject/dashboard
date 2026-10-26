"""pytest 공통 설정.

InfluxDB·Grafana가 필요한 테스트는 서비스가 없으면 건너뛴다(로컬에서 Docker 없이도 돌리도록).
그런데 CI에서는 건너뛴 테스트도 통과로 보여서 통합 테스트가 실제로 돌았는지 알 수 없다.
PORTRAN_REQUIRE_SERVICES=1이면 건너뛴 테스트를 실패로 바꾼다. CI(.github/workflows/ci.yml)가 켠다.
"""
import os

import pytest

REQUIRE_SERVICES = os.environ.get("PORTRAN_REQUIRE_SERVICES") == "1"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if REQUIRE_SERVICES and report.skipped and not hasattr(report, "wasxfail"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"PORTRAN_REQUIRE_SERVICES=1인데 건너뜀 — {reason.removeprefix('Skipped: ')}"
