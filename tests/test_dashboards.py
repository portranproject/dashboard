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


def test_dashboards_exist():
    # 옛 메시지 기준 realtime·evaluation은 M10에서 지웠다. performance.json은 M10에서 더한다
    assert [p.name for p in DASHBOARDS] == ["monitoring.json"]


# --------------------------------------------------------------------------- 새 대시보드 (grafana/build.py, M10)

NEW_DASHBOARDS = ["monitoring.json"]
RULE_NAMES = json.loads((REPO_ROOT / "grafana" / "rule-names.json").read_text(encoding="utf-8"))


def test_generated_dashboards_are_up_to_date():
    """대시보드 JSON은 grafana/build.py로만 만든다. 손으로 고쳤거나 build.py를 고치고 다시 만들지 않았으면 실패."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(REPO_ROOT / "grafana" / "build.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rule_names_cover_samples_and_spec():
    """경보의 rule·candidates ID마다 공격 이름이 있다 (27_ §5.3 대응표, 탐지 쪽 샘플)."""
    known = set(RULE_NAMES["rules"]) | set(RULE_NAMES["candidates"])
    used = set()
    for path in (REPO_ROOT / "tests" / "data" / "detection").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            msg = json.loads(line)
            if msg["type"] == "alert":
                used |= {msg["rule"], *msg.get("candidates", [])}
    assert used and used <= known, used - known
    spec = (REPO_ROOT / "reference" / "detection" / "27_탐지엔진_1-4단계-대시보드-지표_명세서.md").read_text(encoding="utf-8")
    table = spec[spec.index("**공격 이름 대응표"):spec.index("### 5.4")]
    listed = set(re.findall(r"`((?:L3|AN)-[0-9]+[A-Za-z0-9-]*)`", table))
    not_detected = {"AN-03", "AN-05", "AN-06b", "AN-09", "L3-36-V"}  # 탐지하지 않음·나오지 않음 (27_ §5.3)
    assert listed - not_detected <= known, (listed - not_detected) - known


@pytest.mark.parametrize("name", NEW_DASHBOARDS)
def test_new_dashboards_filter_by_source(name):
    """모든 쿼리가 데이터 출처(env)로 거른다 — 출처끼리 섞이지 않게 (docs/dashboard-design.md 1절)."""
    d = load(DASHBOARD_DIR / name)
    source = next(v for v in d["templating"]["list"] if v["name"] == "source")
    assert source["type"] == "custom" and source["current"]["value"] == "p4"
    assert source["query"] == "AWS : p4, On-Premise : lab, 재생 : replay, 샘플 : sample"
    for item, q, _ in queries(d):
        if item != "variable source":
            assert 'r.env == "${source}"' in q, item


def test_monitoring_layout():
    d = load(DASHBOARD_DIR / "monitoring.json")
    assert d["uid"] == "portran-monitoring" and d["refresh"] == "5s"
    rows = [p["title"].split(" — ")[0] for p in d["panels"] if p["type"] == "row"]
    assert rows == ["요약", "상시 KPM2", "경보 목록", "경보 상세"]
    assert [v["name"] for v in d["templating"]["list"]] == ["source", "cell", "alert_id"]
    names = {a["name"] for a in d["annotations"]["list"]}
    assert {"경보 구간", "데이터 없음 (gap)", "칸 일부 없음", "세션 시작", "DU·CU 재시작"} <= names
    # 세션 시작(hello)과 DU·CU 재시작(f1_evt)은 색이 달라야 구분된다
    colors = {a["name"]: a["iconColor"] for a in d["annotations"]["list"]}
    assert colors["세션 시작"] != colors["DU·CU 재시작"]
    # 공격 이름 값 매핑이 rule-names.json 그대로
    table = next(p for p in d["panels"] if p["title"] == "경보")
    mapping = next(o for o in table["fieldConfig"]["overrides"] if o["matcher"]["options"] == "공격")
    options = mapping["properties"][0]["value"][0]["options"]
    assert {k: v["text"] for k, v in options.items()} == {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]}


def test_kpm2_lines_break_where_data_is_missing():
    """받지 않은 구간을 선으로 이으면 그 사이 값이 있었던 것처럼 보인다(M10 AWS 화면). 3초 묶음 2칸 넘게 비면 끊는다."""
    d = load(DASHBOARD_DIR / "monitoring.json")
    lines = [p for p in d["panels"] if p["type"] == "timeseries"
             and p["fieldConfig"]["defaults"]["custom"].get("drawStyle") == "line"]
    assert lines
    for panel in lines:
        custom = panel["fieldConfig"]["defaults"]["custom"]
        assert custom["spanNulls"] is False and custom["insertNulls"] == 6000, panel["title"]


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
def test_ranges_are_never_empty(path):
    """range의 stop이 화면 시간 범위 끝이면 start도 화면 시간 범위 기준이어야 한다. start가 지금 기준(-5m)이면 지난
    시간 범위를 골랐을 때 start > stop이 되어 'cannot query an empty range'로 패널이 깨진다(AWS 요약 줄, 11/11)."""
    found = 0
    for item, q, _ in queries(load(path)):
        for start, stop in re.findall(r"range\(start: (.+?), stop: (.+?)\)$", q, flags=re.M):
            found += 1
            if stop == "v.timeRangeStop":
                assert "v.timeRangeStart" in start, (item, start)
            else:
                assert stop == "now()" and "v.timeRange" not in start, (item, start, stop)
    assert found


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


# --------------------------------------------------------------------------- 쿼리 실행 (Grafana 필요)

VARIABLE_VALUES = {
    "${source}": "sample",
    "${cell:json}": '["1"]',
    "${cell}": "1",
    "${alert_id}": "alert-not-exist",
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
