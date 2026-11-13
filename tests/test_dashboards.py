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
    # 옛 메시지 기준 realtime·evaluation은 M10에서 지웠다
    assert [p.name for p in DASHBOARDS] == ["monitoring.json", "performance.json"]


# --------------------------------------------------------------------------- 새 대시보드 (grafana/build.py, M10)

NEW_DASHBOARDS = ["monitoring.json", "performance.json"]
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
            # 단계 비교는 출처를 함수 인자로 넘긴다(count_raises(env: "${source}"))
            assert 'r.env == "${source}"' in q or 'env: "${source}"' in q, item


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
    # 짧은 이름(사용자 요청 11/13): '#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈'
    assert set(options) == set(RULE_NAMES["rules"]) | set(RULE_NAMES["candidates"])
    assert options["L3-01-V"]["text"] == "UE 컨텍스트 고갈" and options["AN-08"]["text"] == "기존 UE들의 재등록 급증"
    assert not any(v["text"].startswith("#") or "(" in v["text"] for v in options.values())


def test_kpm2_lines_break_where_data_is_missing():
    """받지 않은 구간을 선으로 이으면 그 사이 값이 있었던 것처럼 보인다(M10 AWS 화면). 3초 묶음 2칸 넘게 비면 끊는다."""
    d = load(DASHBOARD_DIR / "monitoring.json")
    lines = [p for p in d["panels"] if p["type"] == "timeseries"
             and p["fieldConfig"]["defaults"]["custom"].get("drawStyle") == "line"]
    assert lines
    for panel in lines:
        custom = panel["fieldConfig"]["defaults"]["custom"]
        assert custom["spanNulls"] is False and custom["insertNulls"] == 6000, panel["title"]


def test_tables_sort_before_renaming_map():
    """map으로 만든 열로 정렬하면 InfluxDB 2.7이 줄을 떨어뜨린다 — 관제 경보 목록에서 해제된 1단계 경보가 빠졌다(M11에서 찾음).
    정렬은 map 앞, 원래 열로 한다."""
    for name, title, key in (("monitoring.json", "경보", 'sort(columns: ["start"], desc: true)'),
                             ("performance.json", "공격별 경보 결과", 'sort(columns: ["n"], desc: true)')):
        p = next(p for p in load(DASHBOARD_DIR / name)["panels"] if p.get("title") == title)
        q = p["targets"][0]["query"]
        last_map = q.rindex("|> map(")
        assert key in q and q.index(key) < last_map, title
        assert "|> sort(" not in q[last_map:], title
    # 경보 목록에 단계 열이 없다(사용자 요청 11/13)
    p = next(p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"] if p.get("title") == "경보")
    order = p["transformations"][0]["options"]["indexByName"]
    assert "단계" not in order and min(order, key=order.get) == "시작"


def test_performance_layout():
    """성능 대시보드 = 탐지 성과 + CU 자원(수집 오버헤드, M11) (docs/dashboard-design.md 3절)."""
    d = load(DASHBOARD_DIR / "performance.json")
    assert d["uid"] == "portran-performance"
    rows = [p["title"].split(" — ")[0] for p in d["panels"] if p["type"] == "row"]
    assert rows == ["탐지 결과", "경보·입력 품질", "CU 자원"]  # '파이프라인 완성 뒤' 자리는 없앴다(11/13)
    # 단계 비교(1~4단계 vs 1단계만)는 없앴다(사용자 결정 11/13)
    assert [v["name"] for v in d["templating"]["list"]] == ["source", "cell"]
    panels = {p["title"]: p for p in d["panels"] if p["type"] != "row"}
    assert not any("단계 비교" in title or "kpm_only" in json.dumps(p) for title, p in panels.items())
    # 공격별 막대: 모든 룰·후보 ID → 짧은 공격 이름('#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈')
    assert panels["공격별 경보 수"]["options"]["orientation"] == "horizontal"  # 세로 막대는 해 보고 되돌림(11/13)
    q = panels["공격별 경보 수"]["targets"][0]["query"]
    assert all(f'"{rule}":' in q for rule in {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]})
    assert '"L3-01-V": "UE 컨텍스트 고갈"' in q and '"L3-24": "하향 IMSI 추출"' in q
    assert '"AN-02": "식별 요청 증가"' in q and "#" not in q.split("names = ")[1].split("\n")[0]
    table = panels["공격별 경보 결과"]
    # 룰 ID·단계 열은 빼고(사용자 요청 11/13) 공격 이름부터
    order = table["transformations"][0]["options"]["indexByName"]
    assert "룰" not in order and "단계" not in order and min(order, key=order.get) == "공격"
    attack = next(o for o in table["fieldConfig"]["overrides"] if o["matcher"]["options"] == "공격")
    assert attack["properties"][0]["value"][0]["options"]["L3-01-V"]["text"] == "UE 컨텍스트 고갈"
    # 경보·입력 품질도 셀로 거른다. CU 자원(overhead)은 노드 값이라 셀과 무관
    for p in panels.values():
        for t in p.get("targets", []):
            node_level = 'r._measurement == "overhead' in t["query"] and '"kpm2"' not in t["query"]
            assert node_level or "${cell:json}" in t["query"], p["title"]


def test_performance_overhead_row():
    """CU 자원 줄(SCHEMA.md 6절 overhead): Beszel식 2열 — CPU·메모리는 노드 전체와 분석 엔진 몫, 링크 트래픽, 부하와 함께."""
    d = load(DASHBOARD_DIR / "performance.json")
    panels = d["panels"]
    start = next(i for i, p in enumerate(panels) if p["type"] == "row" and p["title"].startswith("CU 자원"))
    end = next((i for i, p in enumerate(panels) if i > start and p["type"] == "row"), len(panels))
    row = {p["title"]: p for p in panels[start + 1:end]}
    assert list(row) == ["노드", "고른 시간 범위 요약", "CPU 사용률 (노드 전체)", "CPU 내역 (코어 수, 쌓기)",
                         "메모리 사용량 (노드 전체)", "메모리 내역 (쌓기)",
                         "F1·N2 SCTP 트래픽 (바이트/초, 위 = 들어옴 · 아래 = 나감)",
                         "F1·N2 SCTP 패킷 (패킷/초, 위 = 들어옴 · 아래 = 나감)", "부하와 함께 — CPU 사용률 · RRC 연결 시도"]
    for title, p in row.items():
        if p["type"] == "timeseries":
            # 3초 구간이 6초 넘게 비면 선을 끊는다(상시 KPM2와 같게)
            assert p["fieldConfig"]["defaults"]["custom"]["insertNulls"] == 6000, title
    load_panel = row["부하와 함께 — CPU 사용률 · RRC 연결 시도"]
    assert [t["refId"] for t in load_panel["targets"]] == ["A", "B"]
    # 두 계열을 한곳에, 이름과 평균·최대가 붙게(목록이면 오른쪽 축 계열만 따로 가고, 아래 표는 너무 벌어짐)
    legend = load_panel["options"]["legend"]
    assert (legend["displayMode"], legend["placement"], legend["calcs"]) == ("table", "right", ["mean", "max"])
    assert '"overhead"' in load_panel["targets"][0]["query"] and '"kpm2"' in load_panel["targets"][1]["query"]
    # 링크: 바이트/초와 패킷/초, 둘 다 구간 길이로 나눈 초당 값
    for title, field, unit in (("F1·N2 SCTP 트래픽 (바이트/초, 위 = 들어옴 · 아래 = 나감)", "wire_bytes", "binBps"),
                               ("F1·N2 SCTP 패킷 (패킷/초, 위 = 들어옴 · 아래 = 나감)", "sctp_packets", "pps")):
        q = row[title]["targets"][0]["query"]
        assert '"overhead_link"' in q and f"ingress_{field}" in q and f"egress_{field}" in q and "/ r.secs" in q, title
        assert row[title]["fieldConfig"]["defaults"]["unit"] == unit, title
        # 범례 = 'F1 들어옴 (DU → CU)' — NIC 이름은 범례에서 뺀다
        assert row[title]["fieldConfig"]["defaults"]["displayName"] == "${__field.labels.link} ${__field.labels.dir}"
        assert '"들어옴 (DU → CU)"' in q and '"나감 (CU → AMF)"' in q


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
        # 바꾸지 않은 변수가 남으면 Flux가 문자열 보간("${x}")으로 읽어 엉뚱한 오류가 난다 — 먼저 잡는다
        left = set(re.findall(r"\$\{[^}]+\}", q))
        if left:
            errors.append(f"{name}: VARIABLE_VALUES에 없는 변수 {sorted(left)}")
            continue
        result = grafana_query(q)
        if "error" in result:
            errors.append(f"{name}: {result['error']}")
    assert errors == []
