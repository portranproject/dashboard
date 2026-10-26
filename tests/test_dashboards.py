"""grafana/dashboards/*.json 검사.

정적 검사는 항상, 쿼리 실행 검사는 Grafana가 떠 있을 때만 한다 (없으면 건너뜀).
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from common.config import ENV_PATH, load_env
from mock.generator import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "grafana" / "dashboards"
DATASOURCE_UID = yaml.safe_load(
    (REPO_ROOT / "grafana" / "provisioning" / "datasources" / "influxdb.yml").read_text(encoding="utf-8")
)["datasources"][0]["uid"]
DASHBOARDS = sorted(DASHBOARD_DIR.glob("*.json"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def queries(d):
    """(이름, 쿼리, datasource) 목록: 패널 target, annotation, query 변수."""
    out = []
    for p in d["panels"]:
        for t in p.get("targets", []):
            out.append((f"panel {p['id']} {p.get('title')}", t["query"], t.get("datasource") or p.get("datasource")))
    for a in d["annotations"]["list"]:
        if "target" in a:
            out.append((f"annotation {a['name']}", a["target"]["query"], a["datasource"]))
    for v in d["templating"]["list"]:
        if v["type"] == "query":
            out.append((f"variable {v['name']}", v["query"], v["datasource"]))
    return out


@pytest.fixture(scope="module")
def realtime():
    return load(DASHBOARD_DIR / "realtime.json")


def test_dashboards_exist():
    assert [p.name for p in DASHBOARDS] == ["evaluation.json", "realtime.json"]


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_all_queries_use_provisioned_datasource_and_default_bucket(path):
    d = load(path)
    items = queries(d)
    assert items
    for name, q, ds in items:
        assert ds == {"type": "influxdb", "uid": DATASOURCE_UID}, name
        # bucket 이름은 .env에서 오므로 대시보드에 박아 넣지 않는다
        assert "from(bucket: v.defaultBucket)" in q or "bucket: v.defaultBucket" in q, name
        assert 'bucket: "' not in q, name


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_panel_layout(path):
    d = load(path)
    ids = [p["id"] for p in d["panels"]]
    assert len(ids) == len(set(ids))
    cells = set()
    for p in d["panels"]:
        g = p["gridPos"]
        assert 0 <= g["x"] and g["x"] + g["w"] <= 24, p["title"]
        for x in range(g["x"], g["x"] + g["w"]):
            for y in range(g["y"], g["y"] + g["h"]):
                assert (x, y) not in cells, f"겹침: {p['title']}"
                cells.add((x, y))


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_referenced_variables_are_defined(path):
    d = load(path)
    defined = {v["name"] for v in d["templating"]["list"]}
    builtin = {"__field", "__value", "__url_time_range", "__data"}
    text = json.dumps(d, ensure_ascii=False)
    used = set(re.findall(r"\$\{(\w+)", text)) - builtin
    assert used <= defined, used - defined


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_query_variables_refresh_on_time_range_change(path):
    """query 변수는 새로고침마다 다시 읽는다(refresh=2). 대시보드를 열 때만 읽으면(1) 데이터가 들어오기 전에 연
    대시보드에서 목록이 비어, 그 변수로 거르는 패널이 계속 No data가 된다(새 서버 첫 배포에서 겪음, M7 D103)."""
    for v in load(path)["templating"]["list"]:
        if v["type"] == "query":
            assert v["refresh"] == 2, v["name"]


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_annotation_filters_point_to_existing_panels(path):
    d = load(path)
    ids = {p["id"] for p in d["panels"]}
    for a in d["annotations"]["list"]:
        if "filter" in a:
            assert set(a["filter"]["ids"]) <= ids, a["name"]


def test_realtime_has_section_9_1_panels(realtime):
    """CLAUDE.md 9.1절: 요약 / 핵심 비교 / 이벤트 / 근거, 새로고침 5초, 변수 ruleset(기본 full)·node·attack_type."""
    assert realtime["uid"] == "portran-realtime" and realtime["refresh"] == "5s"
    rows = [p["title"] for p in realtime["panels"] if p["type"] == "row"]
    assert [r.split(" ")[0] for r in rows] == ["요약", "핵심", "이벤트", "근거"]
    variables = {v["name"]: v for v in realtime["templating"]["list"]}
    assert {"ruleset", "node", "attack_type", "event_id"} <= set(variables)
    assert variables["ruleset"]["current"]["value"] == "full"
    names = {a["name"] for a in realtime["annotations"]["list"]}
    assert {"탐지 (detection)", "공격 구간 (attack_run)"} <= names
    region = next(a for a in realtime["annotations"]["list"] if a["name"] == "공격 구간 (attack_run)")
    assert region["mappings"]["timeEnd"]["value"] == "timeEnd"  # 구간(region) annotation
    evidence = next(p for p in realtime["panels"] if p["type"] == "table" and p["title"].startswith("근거"))
    assert evidence["transformations"][0]["id"] == "extractFields"


def test_evaluation_has_section_9_2_panels():
    """CLAUDE.md 9.2절: 시나리오 × 룰셋 표(full vs kpm_only 나란히), 탐지율 막대, 지연 분포·p50/p95, eBPF on/off 오버헤드."""
    d = load(DASHBOARD_DIR / "evaluation.json")
    assert d["uid"] == "portran-evaluation"
    assert [v["name"] for v in d["templating"]["list"]] == ["eval_id"]
    types = {p["title"]: p["type"] for p in d["panels"]}
    assert types["시나리오 × 룰셋"] == "table"
    assert types["탐지율 (full vs kpm_only)"] == "barchart"
    assert types["탐지 지연 분포 (ts_detected − ts_first_evidence)"] == "histogram"
    assert types["지연 p50 / p95 (run별 첫 매칭 탐지)"] == "table"
    assert types["CPU (%)"] == types["메모리 (MB)"] == "barchart"
    table = next(p for p in d["panels"] if p["title"] == "시나리오 × 룰셋")
    renamed = table["transformations"][0]["options"]["renameByName"]
    for metric in ("탐지율", "precision", "오탐"):
        assert {f"{metric} full", f"{metric} kpm_only"} <= set(renamed.values())


def test_evaluation_reads_fields_written_by_evaluator():
    """대시보드가 읽는 eval_result 필드를 evaluator가 실제로 쓰는지."""
    import inspect

    from evaluator import evaluate as ev

    written = set(re.findall(r'\.field\("(\w+)"', inspect.getsource(ev.write_results)))
    written |= {"detection_rate", "precision", "fp_per_hour", "latency_p50_ms", "latency_p95_ms",
                "onset_p50_ms", "onset_p95_ms"}
    text = (DASHBOARD_DIR / "evaluation.json").read_text(encoding="utf-8")
    used = set(re.findall(r"\br\.(\w+)", text)) - {"_measurement", "_field", "_value", "_time", "scenario", "ruleset",
                                                  "data_source", "node", "ebpf_on", "rate", "fp", "runs", "grace"}
    assert used <= written, used - written


def test_realtime_ekpm_codes_match_code_table(realtime):
    """eKPM 패널이 쓰는 코드값이 mock/scenarios.yaml(= SCHEMA.md 6.3)의 코드표와 같아야 한다."""
    codes = load_config()["codes"]
    panel = next(p for p in realtime["panels"] if p["title"].startswith("eKPM"))
    q = panel["targets"][0]["query"]
    expected = [
        ("rrc_msg_id", codes["rrc_msg_id"]["RRCSetupRequest"]),
        ("nas_msg_id", codes["nas_msg_id"]["AuthenticationRequest"]),
    ]
    for name, value in expected:
        assert f'r.name == "{name}" and r._value == {float(value)}' in q, (name, value)
    assert f'r._value == {float(codes["nas_msg_id"]["AuthenticationFailure"])}' in q
    assert f'r._value == {float(codes["nas_msg_id"]["RegistrationReject"])}' in q
    assert codes["ue_cipher_alg"]["NEA0"] == codes["ue_integrity_alg"]["NIA0"] == 0
    assert 'r.name == "ue_integrity_alg") and r._value == 0.0' in q


def test_realtime_kpm_names_exist_in_mock(realtime):
    kpm = set(load_config()["kpm"])
    panel = next(p for p in realtime["panels"] if p["title"].startswith("표준 KPM"))
    used = set(re.findall(r'"(RRC\.[A-Za-z]+|UECNTX\.[A-Za-z]+)"', panel["targets"][0]["query"]))
    assert used and used <= kpm


# --------------------------------------------------------------------------- 쿼리 실행 (Grafana 필요)

VARIABLE_VALUES = {
    "${ruleset}": "full",
    "${node:json}": '["cu","du"]',
    "${attack_type:json}": '["RRC_SIGNALING_STORM","ABNORMAL_UE_ATTACH","F1AP_MSG_TAMPER"]',
    "${event_id}": "det-not-exist",
    "${eval_id}": "eval-not-exist",
}


def grafana_query(flux):
    load_env()
    port = os.environ.get("GRAFANA_PORT", "3000")
    body = {"queries": [{"refId": "A", "datasource": {"uid": DATASOURCE_UID}, "query": flux,
                         "intervalMs": 1000, "maxDataPoints": 500}],
            "from": "now-15m", "to": "now"}
    auth = base64.b64encode(f"{os.environ['GRAFANA_ADMIN_USER']}:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode())
    req = urllib.request.Request(f"http://localhost:{port}/api/ds/query", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {auth.decode()}"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))["results"]["A"]
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}


@pytest.fixture(scope="module")
def grafana_up():
    if not ENV_PATH.exists():
        pytest.skip(".env 없음")
    load_env()
    try:
        urllib.request.urlopen(f"http://localhost:{os.environ.get('GRAFANA_PORT', '3000')}/api/health", timeout=3)
    except Exception:
        pytest.skip("Grafana에 접속할 수 없음")


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_all_queries_run_without_error(grafana_up, path):
    errors = []
    for name, q, _ in queries(load(path)):
        for k, v in VARIABLE_VALUES.items():
            q = q.replace(k, v)
        result = grafana_query(q)
        if "error" in result:
            errors.append(f"{name}: {result['error']}")
    assert errors == []
