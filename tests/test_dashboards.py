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
    # 요약 줄은 없애고 성능 대시보드의 탐지 결과 줄을 맨 위로 옮겼다(사용자 결정 11/16)
    # 줄 제목은 짧게(11/16): 탐지 결과 · KPM(상시 KPM2) · 경보 목록 · 경보 상세 — ${alert_id}
    assert rows == ["탐지 결과", "KPM", "경보 목록", "경보 상세"]
    # 경보 목록 줄은 경보 표 하나만 한 줄 가득(룰별 경보 수 막대는 없앰 — 사용자 요청 11/16)
    i = next(i for i, p in enumerate(d["panels"]) if p["type"] == "row" and p["title"].startswith("경보 목록"))
    assert d["panels"][i + 1]["title"] == "경보" and d["panels"][i + 1]["gridPos"]["w"] == 24
    assert d["panels"][i + 2]["type"] == "row"
    assert [v["name"] for v in d["templating"]["list"]] == ["source", "cell", "alert_id"]
    names = {a["name"] for a in d["annotations"]["list"]}
    assert {"데이터 없음 (gap)", "칸 일부 없음", "세션 시작", "DU·CU 재시작"} <= names
    # 경보 구간은 주석이 아니라 KPM 패널의 경보 계열(refId B)로 칠한다 — 주석은 새로고침마다 깜빡였다(D209)
    assert "경보 구간" not in names
    # 세션 시작(hello)과 DU·CU 재시작(f1_evt)은 색이 달라야 구분된다
    colors = {a["name"]: a["iconColor"] for a in d["annotations"]["list"]}
    assert colors["세션 시작"] != colors["DU·CU 재시작"]
    # 주석은 늘 켜 두고 위쪽 토글은 숨긴다(사용자 요청 11/16)
    assert all(a["enable"] and a["hide"] for a in d["annotations"]["list"])
    # 경보 고르기 칸도 숨긴다(11/16) — 경보 목록 행 링크(var-alert_id)로 고른다
    hidden = {v["name"]: v["hide"] for v in d["templating"]["list"]}
    assert hidden == {"source": 0, "cell": 0, "alert_id": 2}
    # 공격 이름 값 매핑이 rule-names.json 그대로
    table = next(p for p in d["panels"] if p["title"] == "경보")
    mapping = next(o for o in table["fieldConfig"]["overrides"] if o["matcher"]["options"] == "공격")
    options = mapping["properties"][0]["value"][0]["options"]
    # 짧은 이름(사용자 요청 11/13): '#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈'
    assert set(options) == set(RULE_NAMES["rules"]) | set(RULE_NAMES["candidates"])
    assert options["L3-01-V"]["text"] == "UE 컨텍스트 고갈" and options["AN-08"]["text"] == "기존 UE들의 재등록 급증"
    assert not any(v["text"].startswith("#") or "(" in v["text"] for v in options.values())


def test_kpm2_lines_break_where_data_is_missing():
    """받지 않은 구간을 선으로 이으면 그 사이 값이 있었던 것처럼 보인다(M10 AWS 화면). 데이터가 없는 구간(win)은 쿼리가
    null 행으로 남기고(createEmpty: true) 선을 거기서 끊는다 — insertNulls는 고정 ms라 묶은 구간 길이를 몰라 쓰지 않는다(D202)."""
    d = load(DASHBOARD_DIR / "monitoring.json")
    lines = [p for p in d["panels"] if p["type"] == "timeseries"
             and p["fieldConfig"]["defaults"]["custom"].get("drawStyle") == "line"]
    assert lines
    for panel in lines:
        custom = panel["fieldConfig"]["defaults"]["custom"]
        assert custom["spanNulls"] is False and "insertNulls" not in custom, panel["title"]
        # 데이터 쿼리(A) — B는 경보 툴팁 계열(그래프에 안 그림)
        assert all("createEmpty: true" in t["query"] for t in panel["targets"] if t["refId"] == "A"), panel["title"]


def all_queries():
    """두 대시보드와 알림 규칙의 (이름, 쿼리)."""
    out = [(f"{name} {item}", q) for name in NEW_DASHBOARDS for item, q, _ in queries(load(DASHBOARD_DIR / name))]
    out += [(f"alert {r['uid']}", r["data"][0]["model"]["query"]) for r in load(ALERTING)["groups"][0]["rules"]]
    return out


def first_filters(q):
    """각 range( 바로 뒤의 filter( 호출 글(다음 |> 앞까지)."""
    out = []
    for m in re.finditer(r"\|> range\(", q):
        f = q.find("|> filter(", m.end())
        if f < 0:
            continue
        end = q.find("|>", f + 2)
        out.append(q[f:end if end > 0 else len(q)])
    return out


def test_storage_filters_have_no_contains():
    """range 바로 뒤 filter에 contains()를 쓰면 InfluxDB가 저장소에서 거르지 못해(pushdown 안 됨) 데이터를 다 읽는다 —
    관제 KPM 그래프가 7일 범위에서 30초를 넘어 시간 제한에 걸렸다(11/18 AWS). 셀은 정규식 ${cell:regex}로 거른다(D202)."""
    found = 0
    for name, q in all_queries():
        for text in first_filters(q):
            found += 1
            assert "contains(" not in text, (name, text)
    assert found


def raw_series_queries():
    """상시 KPM2·overhead 원본(3초 칸)을 읽는 시간 그래프 쿼리와 주석 — 근거 KPM(경보 하나의 100 ms 근거)은 뺀다."""
    out = []
    for name in NEW_DASHBOARDS:
        d = load(DASHBOARD_DIR / name)
        for p in d["panels"]:
            if p["type"] == "timeseries":
                out += [(p["title"], t["query"]) for t in p["targets"]
                        if re.search(r'_measurement == "(kpm2|overhead|overhead_link)"', t["query"])]
        out += [(a["name"], a["target"]["query"]) for a in d["annotations"]["list"]
                if "target" in a and '_measurement == "kpm2"' in a["target"]["query"]]
    return out


def test_raw_series_are_windowed():
    """3초 원본을 그대로 가져오면 7일에 셀·지표 하나가 20만 점 — Grafana 점 수 상한(maxDataPoints × 10)에 걸린다(11/18 AWS).
    화면 간격(v.windowPeriod)을 3초 배수로 올린 구간(win)으로 묶는다(D202)."""
    items = raw_series_queries()
    titles = {t for t, _ in items}
    assert {"RRC 연결 시도 · 성공 · 무응답", "UE 컨텍스트 · 연결 UE 수", "칸 일부 없음", "CPU 사용률", "CPU 내역",
            "메모리 사용량", "메모리 내역", "F1·N2 SCTP 트래픽", "F1·N2 SCTP 패킷", "CPU 사용률 · RRC 연결 시도"} == titles
    for title, q in items:
        assert "win = duration(v: (int(v: v.windowPeriod) + 2999999999) / 3000000000 * 3000000000)" in q, title
        assert "aggregateWindow(every: win," in q and "aggregateWindow(every: 3s" not in q, title
        # 원본을 읽는 from마다 range·filter 바로 뒤에 묶는다(저장소에서 계산) — 앞에 pivot·map이 오면 다 읽는다
        for m in re.finditer(r"from\(bucket: v\.defaultBucket\)", q):
            rest = q[m.end():]
            steps = [s.strip().split("(")[0] for s in rest.split("|>")[1:5]]
            assert steps[0] == "range" and "pivot" not in steps[:3] and "aggregateWindow" in steps, (title, steps)


def test_kpm_panels_show_alerts_in_tooltip():
    """경보 구간 어디에 마우스를 대도 툴팁에 경보가 보인다(사용자 요청 11/18, D204) — Grafana 주석 글은 아래쪽 작은 마커에서만
    뜬다. 경보 계열(refId B)이 경보 구간을 직접 칠하고(주석은 새로고침마다 깜빡임, D209) 툴팁에도 나온다. 범례에는 없고,
    자기 숨은 축(0~1, 값 1 = 축 끝까지)이라 다른 계열의 y축에 영향이 없다."""
    panels = {p["title"]: p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"]}
    for title in ("RRC 연결 시도 · 성공 · 무응답", "UE 컨텍스트 · 연결 UE 수"):
        p = panels[title]
        [hover] = [t for t in p["targets"] if t["refId"] == "B"]
        q = hover["query"]
        # 경보 구간 주석과 같은 끝(열림 = 지금, 상태 불명 = 마지막 레코드), 구간(win)마다 빈틈없이 채움 —
        # 경보 길이에 비례하는 interpolate로(화면 범위 전체를 채우는 createEmpty는 7일 5~11초, Reviewer 1차)
        assert 'if r.status == "열림" then now() else if r.status == "상태 불명" then r.active else r.last' in q
        assert "experimental.unpivot()" in q and "interpolate.linear(every: win)" in q and "createEmpty" not in q
        assert "r.cell =~ /^${cell:regex}$/" in q
        # 경보 필드는 severity·reason만 읽는다(읽는 시간이 필드 수에 비례 — 7일 2.9초가 대부분 이 읽기)
        assert 'r._field == "severity" or r._field == "reason")' in q and 'r._field == "ues_total"' not in q
        [override] = [o for o in p["fieldConfig"]["overrides"] if o["matcher"] == {"id": "byFrameRefID", "options": "B"}]
        props = {x["id"]: x["value"] for x in override["properties"]}
        assert props["custom.hideFrom"] == {"legend": True, "tooltip": False, "viz": False}
        assert props["custom.axisPlacement"] == "hidden" and props["displayName"] == "${__field.labels.alert}"
        # 구간을 계단 모양으로 축 끝까지 칠한다(선은 안 보이게), 예전 주석 색 rgba(255, 152, 48, 0.12)
        assert (props["custom.drawStyle"], props["custom.lineInterpolation"], props["custom.lineWidth"]) == ("line", "stepAfter", 0)
        assert (props["min"], props["max"], props["custom.fillOpacity"]) == (0, 1, 12)
        assert props["color"] == {"mode": "fixed", "fixedColor": "orange"} and props["custom.spanNulls"] is False
        assert "_value: r.v" in q and "v: 1.0" in q
        assert p["options"]["tooltip"]["mode"] == "multi"


def test_kpm_bars_cover_their_window():
    """막대 시각 = 구간 시작이라 막대가 그 뒤(구간)를 덮어야 경보 구간 주석과 맞는다(-1이면 7일 화면에서 5분 앞에 그려짐)."""
    p = next(p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"] if p["title"] == "RRC 연결 시도 · 성공 · 무응답")
    assert p["fieldConfig"]["defaults"]["custom"]["barAlignment"] == 1


def test_tables_sort_before_renaming_map():
    """map으로 만든 열로 정렬하면 InfluxDB 2.7이 줄을 떨어뜨린다 — 관제 경보 목록에서 해제된 1단계 경보가 빠졌다(M11에서 찾음).
    정렬은 map 앞, 원래 열로 한다."""
    for name, title, key in (("monitoring.json", "경보", 'sort(columns: ["start"], desc: true)'),
                             ("monitoring.json", "공격별 경보 결과", 'sort(columns: ["n"], desc: true)')):
        p = next(p for p in load(DASHBOARD_DIR / name)["panels"] if p.get("title") == title)
        q = p["targets"][0]["query"]
        last_map = q.rindex("|> map(")
        assert key in q and q.index(key) < last_map, title
        assert "|> sort(" not in q[last_map:], title
    # 경보 목록에 단계 열이 없다(사용자 요청 11/13)
    p = next(p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"] if p.get("title") == "경보")
    order = p["transformations"][0]["options"]["indexByName"]
    assert "단계" not in order and min(order, key=order.get) == "시작"


def test_alert_list_rep_percent():
    """대표 값 ratio(0~1)는 %로 — 0.5714 → 57%(사용자 요청 11/18). ×100 뒤 반올림(둘째 자리 반올림 뒤 ×100은 56.99999…%)."""
    q = next(p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"] if p.get("title") == "경보")["targets"][0]["query"]
    assert 'import "math"' in q and 'r.key == "ratio"' in q
    assert 'string(v: math.round(x: float(v: r.rep) * 100.0)) + "%"' in q


def test_alert_detail_columns():
    """판정 요약의 갈래 열과 걸린 UE의 전제 열은 없애고, 불확실은 '관측 오류'로(사용자 요청 11/16).
    판정 요약의 모드 열도 없앤다(11/18)."""
    panels = {p["title"]: p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"]}
    summary = panels["판정 요약"]["transformations"][0]["options"]["indexByName"]
    q = panels["판정 요약"]["targets"][0]["query"]
    assert "갈래" not in summary and "branch" not in q
    assert "모드" not in summary and "모드" not in q and '"mode"' not in q and "r.mode" not in q
    ues = panels["걸린 UE"]["transformations"][0]["options"]["indexByName"]
    assert "관측 오류" in ues and not {"불확실", "전제"} & set(ues)
    assert "r.conditions" not in panels["걸린 UE"]["targets"][0]["query"]


def test_ue_shown_as_cell_uid():
    """UE는 화면에서 셀-uid로(사용자 요청 11/18) — 걸린 UE·peers·UE_EVENT 두 패널. InfluxDB의 ue 태그는 그대로다."""
    panels = {p["title"]: p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"]}
    ues = panels["걸린 UE"]
    order = ues["transformations"][0]["options"]["indexByName"]
    assert "UE (cell-uid)" in order and "UE (cell-du_ue_id-uid)" not in order
    q = ues["targets"][0]["query"]
    assert '"UE (cell-uid)": string(v: r.cell) + "-" + string(v: r.uid)' in q and "r.ue," not in q
    assert "short(s: r.peers)" in q
    timeline = panels["UE_EVENT — UE별 메시지 흐름"]
    q = timeline["targets"][0]["query"]
    assert '"UE " +' not in q and 'ue: r.cell + "-" + string(v: r.uid)' in q
    assert timeline["fieldConfig"]["defaults"]["displayName"] == "${__field.labels.ue}"
    messages = panels["UE_EVENT — 메시지 흐름 상세"]
    order = messages["transformations"][0]["options"]["indexByName"]
    assert "UE (cell-uid)" in order and "UE" not in order
    q = messages["targets"][0]["query"]
    assert '"UE (cell-uid)": r.cell + "-" + string(v: r.uid)' in q and "du_ue_id" not in q


def test_kpm1_timeline_ends_after_last_message():
    """상태 타임라인은 마지막 값을 화면 끝까지 늘인다 — UE마다 마지막 메시지 1초 뒤 빈 값(투명)으로 끝낸다(11/13)."""
    p = next(p for p in load(DASHBOARD_DIR / "monitoring.json")["panels"] if p["title"] == "UE_EVENT — UE별 메시지 흐름")
    q = p["targets"][0]["query"]
    assert "|> last()" in q and "date.add(d: 1s" in q and 'union(tables: [msgs, ends])' in q
    [mapping] = p["fieldConfig"]["defaults"]["mappings"]
    assert mapping["options"]["match"] == "empty" and mapping["options"]["result"]["color"] == "transparent"


def test_detection_rows_on_monitoring():
    """탐지 결과(경보 수·공격별·길이·결과 표)는 관제 맨 위에 있다 — 요약 줄 대신, 성능에서 옮김(사용자 결정 11/16)."""
    d = load(DASHBOARD_DIR / "monitoring.json")
    first_row = next(i for i, p in enumerate(d["panels"]) if p["type"] == "row" and p["title"] == "KPM")
    panels = {p["title"]: p for p in d["panels"][:first_row] if p["type"] != "row"}
    # 경보 수 — 종류별 stat은 없앴다(11/16)
    assert list(panels) == ["공격별 경보 수", "경보 길이 분포", "공격별 경보 결과"]
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
    # 셀로 거른다(정규식 — contains는 저장소에서 거르지 못함, D202)
    for p in panels.values():
        assert all("${cell:regex}" in t["query"] for t in p["targets"]), p["title"]


def test_performance_layout():
    """성능 대시보드 = CU 자원(수집 오버헤드, M11)과 수집 지연(D211) (docs/dashboard-design.md 3절)."""
    d = load(DASHBOARD_DIR / "performance.json")
    assert d["uid"] == "portran-performance"
    rows = [p["title"].split(" — ")[0] for p in d["panels"] if p["type"] == "row"]
    # '파이프라인 완성 뒤' 자리는 없앴고(11/13), 탐지 결과는 관제로 옮기고 경보·입력 품질은 없앴다(11/16)
    assert rows == ["Overhead", "수집 지연"]  # CU 자원 — 수집 오버헤드(제목은 짧게, 11/16), 수집 지연(11/20)
    # 단계 비교(1~4단계 vs 1단계만)는 없앴다(사용자 결정 11/13)
    assert [v["name"] for v in d["templating"]["list"]] == ["source", "cell"]
    panels = {p["title"]: p for p in d["panels"] if p["type"] != "row"}
    assert not any("단계 비교" in title or "kpm_only" in json.dumps(p) for title, p in panels.items())
    # CU 자원(overhead)·수집 지연은 셀과 무관, 상시 KPM2를 함께 그리는 패널만 셀로 거른다
    for p in panels.values():
        for t in p.get("targets", []):
            node_level = ('r._measurement == "overhead' in t["query"] or 'r._measurement == "ingest_delay"' in t["query"]) \
                and '"kpm2"' not in t["query"].replace('r.type == "kpm2"', "")
            assert node_level or "${cell:regex}" in t["query"], p["title"]


def test_performance_ingest_delay_row():
    """수집 지연(D211): 받은 시각 − 데이터 시각의 백분위 표(종류마다 한 행 — p50·p95·p99·개수, 11/20)와 추이(구간 평균)."""
    d = load(DASHBOARD_DIR / "performance.json")
    start = next(i for i, p in enumerate(d["panels"]) if p["type"] == "row" and p["title"] == "수집 지연")
    row = {p["title"]: p for p in d["panels"][start + 1:] if p["type"] != "row"}
    assert list(row) == ["수집 지연 백분위", "수집 지연 추이"]
    stat = row["수집 지연 백분위"]
    q = stat["targets"][0]["query"]
    assert 'r._measurement == "ingest_delay"' in q and 'r.type == "kpm2"' in q and 'r.type == "alert"' in q
    # 백분위는 정렬 뒤 순위로(한 번 읽기) — 백분위마다 quantile을 부르면 데이터를 그만큼 다시 읽는다
    assert q.count('sort(columns: ["_value"])') == 2 and "quantile(" not in q
    assert stat["type"] == "table" and '종류: "KPM 지연"' in q and '종류: "경보 지연"' in q
    order = stat["transformations"][0]["options"]["indexByName"]
    assert list(order) == ["종류", "p50", "p95", "p99", "개수"] and "최대" not in q
    assert stat["fieldConfig"]["defaults"]["unit"] == "ms"
    trend = row["수집 지연 추이"]
    q = trend["targets"][0]["query"]
    # 추세만 — KPM 지연과 경보 지연 두 계열(구간 평균)(11/20)
    assert "aggregateWindow(every: win," in q and q.count("from(bucket: v.defaultBucket)") == 2
    assert '_field: "KPM 지연"' in q and '_field: "경보 지연"' in q and "fn: max" not in q
    assert 'pivot(rowKey: ["_time"], columnKey: ["_field"]' in q
    assert trend["fieldConfig"]["defaults"]["unit"] == "ms"


def test_performance_overhead_row():
    """CU 자원 줄(SCHEMA.md 6절 overhead): Beszel식 2열 — CPU·메모리는 노드 전체와 분석 엔진 몫, 링크 트래픽, 부하와 함께."""
    d = load(DASHBOARD_DIR / "performance.json")
    panels = d["panels"]
    start = next(i for i, p in enumerate(panels) if p["type"] == "row" and p["title"] == "Overhead")
    end = next((i for i, p in enumerate(panels) if i > start and p["type"] == "row"), len(panels))
    row = {p["title"]: p for p in panels[start + 1:end]}
    assert list(row) == ["노드", "고른 시간 범위 요약", "CPU 사용률", "CPU 내역",
                         "메모리 사용량", "메모리 내역",
                         "F1·N2 SCTP 트래픽",
                         "F1·N2 SCTP 패킷", "CPU 사용률 · RRC 연결 시도"]
    for title, p in row.items():
        if p["type"] == "timeseries":
            # 데이터가 없는 구간은 null 행으로 남겨 선을 끊는다(상시 KPM2와 같게, D202)
            assert "insertNulls" not in p["fieldConfig"]["defaults"]["custom"], title
            assert "createEmpty: true" in p["targets"][0]["query"], title
    load_panel = row["CPU 사용률 · RRC 연결 시도"]
    assert [t["refId"] for t in load_panel["targets"]] == ["A", "B"]
    # 두 계열을 한곳에, 이름과 평균·최대가 붙게(목록이면 오른쪽 축 계열만 따로 가고, 아래 표는 너무 벌어짐)
    legend = load_panel["options"]["legend"]
    assert (legend["displayMode"], legend["placement"], legend["calcs"]) == ("table", "right", ["mean", "max"])
    assert '"overhead"' in load_panel["targets"][0]["query"] and '"kpm2"' in load_panel["targets"][1]["query"]
    # 링크: 바이트/초와 패킷/초, 둘 다 구간 증가분(구간 평균)을 구간 길이 3초로 나눈 초당 값
    for title, field, unit in (("F1·N2 SCTP 트래픽", "wire_bytes", "binBps"),
                               ("F1·N2 SCTP 패킷", "sctp_packets", "pps")):
        q = row[title]["targets"][0]["query"]
        assert '"overhead_link"' in q and f"ingress_{field}" in q and f"egress_{field}" in q and "r._value / 3.0" in q, title
        assert row[title]["fieldConfig"]["defaults"]["unit"] == unit, title
        # 범례 = 'F1 들어옴 (DU → CU)' — NIC 이름은 범례에서 뺀다
        assert row[title]["fieldConfig"]["defaults"]["displayName"] == "${__field.labels.link} ${__field.labels.dir}"
        assert '"들어옴 (DU → CU)"' in q and '"나감 (CU → AMF)"' in q
    # 노드 이름: cu로 끝나면 CU로 보인다(AWS는 p4-cu, 11/16)
    node = row["노드"]
    [mapping] = next(o for o in node["fieldConfig"]["overrides"] if o["matcher"]["options"] == "노드")["properties"]
    pattern = mapping["value"][0]["options"]["pattern"]
    assert [bool(re.match(pattern, v)) for v in ("p4-cu", "cu", "CU", "p4-du", "cuda")] == [True, True, True, False, False]
    # 시간 그래프도 cu로 끝나는 node_id(cu·p4-cu)를 한 노드로 묶는다 — 두 이름이 섞인 범위에서 범례가 둘씩 나왔음(11/16)
    for title in ("CPU 사용률", "CPU 내역", "메모리 사용량", "메모리 내역"):
        q = row[title]["targets"][0]["query"]
        assert 'strings.hasSuffix(v: strings.toLower(v: r.node), suffix: "cu")' in q and 'then "CU"' in q, title
        assert "node: if exists r.node then r.node" not in q, title


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
def test_tables_have_fixed_column_order(path):
    """Flux map의 열 순서는 정해져 있지 않다 — 표마다 organize로 순서를 고정하지 않으면 새로고침할 때마다 섞인다(11/13)."""
    for p in load(path)["panels"]:
        if p["type"] == "table":
            org = [t for t in p.get("transformations", []) if t["id"] == "organize"]
            assert org and org[0]["options"]["indexByName"], p["title"]


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_panel_titles_are_short(path):
    """패널·줄 제목에 괄호 설명을 붙이지 않는다 — 설명은 패널 설명(ⓘ)에 둔다(사용자 요청 11/16)."""
    for p in load(path)["panels"]:
        assert "(" not in p["title"], p["title"]


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda p: p.name)
def test_descriptions_have_no_spec_refs(path):
    """패널·변수 설명(ⓘ)에 명세 참조('27_ §5.1')를 넣지 않는다 — 화면을 보는 사람에게는 뜻 없는 기호(사용자 요청 11/16)."""
    d = load(path)
    for item in d["panels"] + d["templating"]["list"]:
        assert not re.search(r"27_|§", item.get("description", "")), item.get("title", item.get("name"))


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


# --------------------------------------------------------------------------- Slack 알림 (M12, grafana/build.py가 만든다)

ALERTING = REPO_ROOT / "grafana" / "provisioning" / "alerting" / "portran.json"


def test_alerting_provisioning():
    """공격 경보·수집 멈춤 두 규칙, AWS(p4)만, Slack 연락처 둘(수집 멈춤은 해제 알림 없음)."""
    a = load(ALERTING)
    [group] = a["groups"]
    assert group["folder"] == "PortRAN" and group["interval"] == "10s"
    rules = {r["uid"]: r for r in group["rules"]}
    assert set(rules) == {"portran-attack", "portran-collect-stop"}
    for r in rules.values():
        q = r["data"][0]["model"]["query"]
        assert r["data"][0]["datasourceUid"] == DATASOURCE_UID
        assert 'r.env == "p4"' in q and "${" not in q, r["uid"]  # AWS 실측만(On-Premise는 받기 시작하면)
        assert r["noDataState"] == "OK" and r["execErrState"] == "KeepLast", r["uid"]
    assert 'r.kind == "attack"' in rules["portran-attack"]["data"][0]["model"]["query"]  # 이상 유형·판정 보류는 알리지 않음
    assert rules["portran-attack"]["labels"] == {"notify": "attack"}
    assert rules["portran-collect-stop"]["labels"] == {"notify": "collect"}
    # 조회 결과가 없을 때도 템플릿이 깨지지 않게 .Values는 with 안에서만
    for r in rules.values():
        for text in r["annotations"].values():
            assert ".Values" not in text or "{{ with .Values }}" in text, (r["uid"], text)
    points = {c["name"]: c["receivers"][0] for c in a["contactPoints"]}
    assert all(p["type"] == "slack" and p["settings"]["url"] == "${SLACK_WEBHOOK_URL}" for p in points.values())
    assert [p["disableResolveMessage"] for p in points.values()] == [False, True]
    [policy] = a["policies"]
    assert policy["group_by"] == ["alertname", "alert_id"]  # 알림 하나 = 경보 하나
    assert policy["routes"] == [{"receiver": "PortRAN Slack (해제 알림 없음)", "object_matchers": [["notify", "=", "collect"]]}]
    # provisioning은 환경변수를 바꿔 넣는다 — 템플릿·주석에 '$'가 있으면 깨질 수 있다(웹훅 주소만 예외)
    text = json.dumps(a, ensure_ascii=False).replace("${SLACK_WEBHOOK_URL}", "")
    assert "$" not in text


# --------------------------------------------------------------------------- 쿼리 실행 (Grafana 필요)

VARIABLE_VALUES = {
    "${source}": "sample",
    "${cell:json}": '["1"]',
    "${cell:regex}": "1",
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


def test_grafana_always_gets_a_slack_webhook_url():
    """SLACK_WEBHOOK_URL이 비어 있으면 Slack 연락처 검사에 걸려 Grafana가 아예 뜨지 않는다(11/13 임시 Grafana에서 확인).
    compose가 비어 있을 때도 기본 주소를 넘겨야 한다."""
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL:-http" in compose


def test_alert_queries_run_without_error(grafana_up):
    """알림 규칙의 Flux도 Grafana(InfluxDB 데이터소스)에서 오류 없이 돈다."""
    errors = []
    for rule in load(ALERTING)["groups"][0]["rules"]:
        result = grafana_query(rule["data"][0]["model"]["query"])
        if "error" in result:
            errors.append(f"{rule['uid']}: {result['error']}")
    assert errors == []


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
