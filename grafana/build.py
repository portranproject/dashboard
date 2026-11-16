"""관제·성능 대시보드 JSON을 만든다 (M10, 설계는 docs/dashboard-design.md).

    python grafana/build.py           # grafana/dashboards/monitoring.json·performance.json을 다시 쓴다
    python grafana/build.py --check   # 커밋된 JSON이 이 스크립트 출력과 같은지 (테스트가 부른다)

대시보드 JSON은 이 스크립트로만 고친다(손으로 고치면 다음 생성 때 사라진다). 이렇게 하는 이유:
  - 데이터 출처(env) 필터, datasource, 룰 ID → 공격 이름 값 매핑(grafana/rule-names.json)을 모든 패널에 똑같이 넣으려고
  - Flux 쿼리를 읽기 쉬운 여러 줄 문자열로 두려고
저장 구조는 schema/SCHEMA.md 5절. 패널마다 description에 "무슨 질문에 답하나"를 적는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "dashboards"
RULE_NAMES = json.loads((ROOT / "rule-names.json").read_text(encoding="utf-8"))
DS = {"type": "influxdb", "uid": "portran-influxdb"}

# 데이터 출처 선택 (docs/dashboard-design.md 1절). 지금은 AWS만 받는다. On-Premise를 받게 되면 ("On-Premise", "lab")을 더한다.
# On-Premise(lab)는 아직 받지 않는다 — 선택지만 둔다(D158)
SOURCES = [("AWS", "p4"), ("On-Premise", "lab"), ("재생", "replay"), ("샘플", "sample")]

# 상태 불명: 열린 경보에 마지막 레코드 뒤 이 시간 동안 아무것도 없으면 (27_ §7)
STALE_NS = {"1": 15_000_000_000, "other": 90_000_000_000}
CELL_LIMIT = 96  # 셀 UE 컨텍스트 한도 (27_ §5.3, ext.UeCtxMax ≥ 90%면 high)
# 상시 KPM2 선은 점 사이가 이보다 길게 비면 끊는다(3초 묶음 2칸). 이으면 받지 않은 구간에
# 값이 서서히 변한 것처럼 보인다.
KPM2_LINE_BREAK_MS = 2 * 3000
# 근거 KPM1 타임라인에서 UE의 마지막 메시지를 이만큼만 그린다(그 뒤는 빈칸)
TIMELINE_END_S = 1


# --------------------------------------------------------------------------- 공통 조각

def short_rule_name(name: str) -> str:
    """'#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈'. 번호(#n)·괄호 설명·' — ' 뒤 부연을 빼고,
    이상 유형은 앞의 '이상 유형 — '를 뺀다(ID가 AN-로 구분된다). 두 대시보드 모두 이 이름을 쓴다(사용자 요청 11/13)."""
    name = name.removeprefix("이상 유형 — ")
    name = re.sub(r"^#\d+\s+", "", name)
    name = re.sub(r"\s*\([^)]*\)$", "", name)
    return name.split(" — ")[0].strip()


def rule_mappings() -> list[dict]:
    """룰·후보 ID → 짧은 공격 이름 값 매핑(원래 이름은 grafana/rule-names.json)."""
    names = {k: short_rule_name(v) for k, v in {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]}.items()}
    return [{"type": "value", "options": {k: {"text": v, "index": i} for i, (k, v) in enumerate(names.items())}}]


SEVERITY_MAPPINGS = [{"type": "value", "options": {
    "2": {"text": "high", "color": "red", "index": 0},
    "1": {"text": "medium", "color": "orange", "index": 1},
    "0": {"text": "없음", "color": "green", "index": 2},
    "high": {"color": "red", "index": 3},
    "medium": {"color": "orange", "index": 4}}}]

STATUS_MAPPINGS = [{"type": "value", "options": {
    "열림": {"color": "red", "index": 0},
    "상태 불명": {"color": "purple", "index": 1},
    "해제": {"color": "green", "index": 2}}},
    {"type": "regex", "options": {"pattern": "강제 종료.*", "result": {"color": "blue", "index": 3}}}]

KIND_MAPPINGS = [{"type": "value", "options": {
    "공격": {"color": "red", "index": 0},
    "이상 유형": {"color": "yellow", "index": 1},
    "판정 보류": {"color": "purple", "index": 2}}}]

# 경보 종류: 공격 경보 / 4단계 이상 유형(AN-) / 판정 보류 경보(2·3단계 룰인데 kind anomaly) — 27_ §5.5
CLASS_EXPR = ('if r.kind == "attack" then "공격" else if strings.hasPrefix(v: r.rule, prefix: "AN-") '
              'then "이상 유형" else "판정 보류"')

ENV = 'r.env == "${source}"'


def alert_summary(alert_start: str, evidence_start: str | None, stop: str = "v.timeRangeStop") -> str:
    """경보 하나 = 한 행으로 합친 Flux(끝은 ungroup). 열: alert_id, rule, stage, kind, cell, start(raise), last(마지막 경보 레코드),
    active(경보·근거 중 마지막), event(마지막 이벤트), sev(0·1·2 최대), ues·rep·key·reason(마지막 값, 문자열), status(열림·해제·
    강제 종료 (사유)·상태 불명), class(공격·이상 유형·판정 보류).
    pivot은 경보마다 필드 구성이 달라 표 모양이 갈리므로 쓰지 않고, 값을 문자열 한 열로 모아 reduce로 합친다.
    상태 불명 판단에 쓸 마지막 근거 시각도 같은 모양으로 붙여(union) 함께 합친다(join.left는 reduce 결과에서 실패함).
    start가 지금 기준(-5m 등)이면 stop도 now()로 준다 — stop이 화면 시간 범위 끝이면, 지난 범위를 골랐을 때
    start > stop이 되어 "cannot query an empty range"로 패널이 깨진다.
    evidence_start가 None이면 근거를 읽지 않는다(성능 대시보드 — 끝난 실험을 넓은 범위로 보므로 근거를 다 읽으면 느리고,
    clear·end가 안 온 경보는 근거와 상관없이 '끝이 안 옴'으로 센다)."""
    if evidence_start is None:
        evidence = "evidence = alerts |> filter(fn: (r) => false)"
    else:
        evidence = f"""evidence = from(bucket: v.defaultBucket)
  |> range(start: {evidence_start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "evidence" and r._field == "seq" and {ENV})
  |> group(columns: ["alert_id"])
  |> max(column: "_time")
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: "", stage: "", kind: "", cell: "", event: "", t: r._time, f: "evidence",
      s: "", a: false}}))
  |> group()"""
    return f"""alerts = from(bucket: v.defaultBucket)
  |> range(start: {alert_start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "alert" and {ENV})
  |> filter(fn: (r) => r._field == "severity" or r._field == "ues_total" or r._field == "rep_value"
      or r._field == "rep_key" or r._field == "reason")
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: r.rule, stage: r.stage, kind: r.kind, cell: r.cell, event: r.event,
      t: r._time, f: r._field, s: string(v: r._value), a: true}}))
  |> group()
{evidence}
summary = union(tables: [alerts, evidence])
  |> group(columns: ["alert_id"])
  |> sort(columns: ["t"])
  |> reduce(identity: {{rule: "", stage: "", kind: "", cell: "", start: time(v: 0), last: time(v: 0), active: time(v: 0),
                       event: "", sev: 0, ues: "", rep: "", key: "", reason: "", n: 0}},
      fn: (r, accumulator) => ({{
        rule: if r.a then r.rule else accumulator.rule,
        stage: if r.a then r.stage else accumulator.stage,
        kind: if r.a then r.kind else accumulator.kind,
        cell: if r.a then r.cell else accumulator.cell,
        start: if r.a and accumulator.n == 0 then r.t else accumulator.start,
        last: if r.a then r.t else accumulator.last,
        active: if r.t > accumulator.active then r.t else accumulator.active,
        event: if r.a then r.event else accumulator.event,
        sev: if r.f == "severity" and r.s == "high" then 2
             else if r.f == "severity" and r.s == "medium" and accumulator.sev < 1 then 1 else accumulator.sev,
        ues: if r.f == "ues_total" then r.s else accumulator.ues,
        rep: if r.f == "rep_value" then r.s else accumulator.rep,
        key: if r.f == "rep_key" then r.s else accumulator.key,
        reason: if r.f == "reason" then r.s else accumulator.reason,
        n: if r.a then accumulator.n + 1 else accumulator.n}}))
  |> filter(fn: (r) => r.n > 0)
  |> group()
  |> map(fn: (r) => {{
      idle = int(v: now()) - int(v: r.active)
      limit = if r.stage == "1" then {STALE_NS["1"]} else {STALE_NS["other"]}
      return {{r with
        status: if r.event == "clear" then "해제" else if r.event == "end" then "강제 종료 (" + r.reason + ")"
                else if idle > limit then "상태 불명" else "열림",
        class: {CLASS_EXPR}}}
    }})
"""


def target(query: str, ref: str = "A", hide: bool = False) -> dict:
    t = {"datasource": DS, "refId": ref, "query": query.strip("\n")}
    if hide:
        t["hide"] = True
    return t


def column_order(columns: list[str], hide: tuple[str, ...] = ()) -> list[dict]:
    """표·stat의 열 순서를 고정하는 Grafana 변환. Flux map의 열 순서는 정해져 있지 않아, 정하지 않으면 새로고침할 때마다
    열이 섞여 나온다(관제 판정 요약 등, 11/13 사용자 지적)."""
    return [{"id": "organize", "options": {"excludeByName": {name: True for name in hide}, "renameByName": {},
                                           "indexByName": {name: i for i, name in enumerate(columns)}}}]


def override(name: str, *props: tuple[str, object], regex: bool = False) -> dict:
    return {"matcher": {"id": "byRegexp" if regex else "byName", "options": name},
            "properties": [{"id": k, "value": v} for k, v in props]}


class Board:
    def __init__(self):
        self.panels: list[dict] = []
        self._id = 0
        self.y = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def row(self, title: str) -> None:
        self.panels.append({"id": self._next_id(), "type": "row", "title": title, "collapsed": False,
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []})
        self.y += 1

    def add(self, type_: str, title: str, x: int, w: int, h: int, targets: list[dict], description: str,
            field_config: dict | None = None, options: dict | None = None, transformations: list | None = None,
            new_line: bool = False) -> dict:
        p = {"id": self._next_id(), "type": type_, "title": title, "description": description, "datasource": DS,
             "gridPos": {"h": h, "w": w, "x": x, "y": self.y}, "targets": targets,
             "fieldConfig": field_config or {"defaults": {}, "overrides": []}, "options": options or {}}
        if transformations:
            p["transformations"] = transformations
        self.panels.append(p)
        if new_line:
            self.y += h
        return p


def source_variable() -> dict:
    options = [{"text": name, "value": env, "selected": i == 0} for i, (name, env) in enumerate(SOURCES)]
    return {"name": "source", "label": "데이터 출처", "type": "custom", "query": ", ".join(f"{n} : {e}" for n, e in SOURCES),
            "current": {"text": SOURCES[0][0], "value": SOURCES[0][1]}, "options": options, "hide": 0,
            "description": "AWS = AWS 테스트베드 p4 · On-Premise = 연구실 테스트베드 lab(아직 받지 않음) · "
                           "재생 = replay로 다시 보낸 데이터 · 샘플 = 탐지 쪽 시험 샘플"}


def query_variable(name: str, label: str, query: str, multi: bool = False, include_all: bool = False,
                   description: str = "") -> dict:
    v = {"name": name, "label": label, "type": "query", "datasource": DS, "query": query.strip("\n"),
         "definition": query.strip("\n"), "refresh": 2, "sort": 0, "multi": multi, "includeAll": include_all,
         "hide": 0, "description": description, "current": {}, "options": []}
    if include_all:
        v["current"] = {"text": "All", "value": "$__all"}
    return v


def annotation(name: str, query: str, color: str, panel_ids: list[int], region: bool = False) -> dict:
    mappings = {"time": {"source": "field", "value": "_time"}, "text": {"source": "field", "value": "text"},
                "tags": {"source": "field", "value": "tags"}}
    if region:
        mappings["timeEnd"] = {"source": "field", "value": "timeEnd"}
    # 늘 켜 두고 위쪽 토글은 숨긴다(11/16 사용자 결정 — 변수 줄을 간단하게)
    return {"name": name, "datasource": DS, "enable": True, "hide": True, "iconColor": color,
            "target": {"datasource": DS, "refId": "Anno", "query": query.strip("\n")}, "mappings": mappings,
            "filter": {"exclude": False, "ids": panel_ids}}


def dashboard(uid: str, title: str, description: str, board: Board, variables: list[dict],
              annotations: list[dict], refresh: str, time_from: str) -> dict:
    builtin = {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": True,
               "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"}
    return {"uid": uid, "title": title, "description": description, "tags": ["portran"], "timezone": "browser",
            "editable": False, "graphTooltip": 1, "refresh": refresh, "time": {"from": time_from, "to": "now"},
            "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]}, "schemaVersion": 39, "version": 1,
            "links": [], "annotations": {"list": [builtin, *annotations]}, "templating": {"list": variables},
            "panels": board.panels}


# --------------------------------------------------------------------------- 관제

def monitoring() -> dict:
    b = Board()

    # ---- 탐지 결과 (요약 줄 대신, 성능 대시보드에서 옮김 — 11/16)
    add_detection_rows(b)

    # ---- 상시 KPM2
    # 줄·패널 제목은 짧게(11/16 사용자 요청) — 셀·3초 묶음·셀 한도는 패널 설명(ⓘ)에 있다
    b.row("KPM")
    kpm_bars = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kpm2" and {ENV} and contains(value: r.cell, set: ${{cell:json}}))
  |> filter(fn: (r) => r._field == "cc.RRC.ConnEstabAtt.total" or r._field == "cc.RRC.ConnEstabSucc.total"
      or r._field == "cc.RRC.ConnEstabFailCause.NoReply")
  |> map(fn: (r) => ({{_time: r._time, _value: r._value, cell: r.cell,
      _field: if r._field == "cc.RRC.ConnEstabAtt.total" then "연결 시도"
              else if r._field == "cc.RRC.ConnEstabSucc.total" then "연결 성공" else "무응답 (NoReply)"}}))
  |> group(columns: ["cell"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    bars = b.add("timeseries", "RRC 연결 시도 · 성공 · 무응답", 0, 24, 9, [target(kpm_bars)],
                 "상시 KPM2(TeleRAN Table II) — 셀마다 3초 묶음, 위쪽 셀 선택으로 거른다. "
                 "셀에 무슨 일이 일어나고 있나. UE 컨텍스트 고갈 공격(1단계)은 시도와 무응답이 함께 솟고 성공은 그대로다. "
                 "주황 영역 = 경보 구간, 회색 영역 = 데이터 없음(gap)·칸 일부 없음, 파란 세로선 = 분석 엔진 세션 시작(hello), 보라 세로선 = DU·CU 재시작(f1_evt)",
                 field_config={"defaults": {"unit": "none", "min": 0,
                                            "displayName": "${__field.name} · 셀 ${__field.labels.cell}",
                                            "custom": {"drawStyle": "bars", "fillOpacity": 70, "barAlignment": -1,
                                                       "lineWidth": 1, "spanNulls": False, "stacking": {"mode": "none"}}},
                               "overrides": [
                                   override("연결 시도.*", ("color", {"mode": "fixed", "fixedColor": "blue"}), regex=True),
                                   override("연결 성공.*", ("color", {"mode": "fixed", "fixedColor": "green"}), regex=True),
                                   override("무응답.*", ("color", {"mode": "fixed", "fixedColor": "red"}), regex=True)]},
                 options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    kpm_lines = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kpm2" and {ENV} and contains(value: r.cell, set: ${{cell:json}}))
  |> filter(fn: (r) => r._field == "ext.UeCtxMax" or r._field == "si.RRC.ConnMax" or r._field == "si.RRC.ConnMean")
  |> map(fn: (r) => ({{_time: r._time, _value: r._value, cell: r.cell,
      _field: if r._field == "ext.UeCtxMax" then "UE 컨텍스트 수 (최대)"
              else if r._field == "si.RRC.ConnMax" then "RRC 연결 UE (최대)" else "RRC 연결 UE (평균)"}}))
  |> group(columns: ["cell"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    lines = b.add("timeseries", "UE 컨텍스트 · 연결 UE 수", 0, 24, 8, [target(kpm_lines)],
                  f"셀 자원이 고갈되고 있나. 빨간 선 = 셀 한도 {CELL_LIMIT}의 90%(1·2단계 경보가 high가 되는 기준). "
                  "UE 컨텍스트 수는 완료를 기다리는 UE까지 센 탐지 쪽 확장 지표(ext.UeCtxMax)",
                  field_config={"defaults": {"unit": "none", "min": 0,
                                             "displayName": "${__field.name} · 셀 ${__field.labels.cell}",
                                             "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 10,
                                                        "spanNulls": False, "insertNulls": KPM2_LINE_BREAK_MS,
                                                        "thresholdsStyle": {"mode": "line+area"}},
                                             "thresholds": {"mode": "absolute", "steps": [
                                                 {"color": "transparent", "value": None},
                                                 {"color": "red", "value": round(CELL_LIMIT * 0.9)}]}},
                                "overrides": []},
                  options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                           "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)
    kpm_panels = [bars["id"], lines["id"]]

    # ---- 경보 목록
    b.row("경보 목록")
    alert_list = f'''
import "date"
import "strings"
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)")}
// 정렬은 map 앞에서 한다 — map으로 만든 열("시작")로 정렬하면 InfluxDB 2.7이 줄을 떨어뜨린다(해제된 경보가 목록에서 빠졌음, M11)
summary
  |> filter(fn: (r) => r.start >= v.timeRangeStart or r.status == "열림" or r.status == "상태 불명")
  |> sort(columns: ["start"], desc: true)
  |> limit(n: 300)
  |> map(fn: (r) => ({{
      시작: r.start,
      셀: r.cell,
      룰: r.rule,
      공격: r.rule,
      종류: r.class,
      심각도: string(v: r.sev),
      "UE 수": r.ues,
      "대표 값": if r.key == "" then "" else r.key + " = " + r.rep,
      상태: r.status,
      "길이(초)": float(v: int(v: if r.event == "raise" or r.event == "update" then now() else r.last) - int(v: r.start)) / 1000000000.0,
      alert_id: r.alert_id}}))
'''
    link = {"title": "이 경보 상세 보기",
            "url": "/d/portran-monitoring/?var-source=${source}&var-cell=${cell}&var-alert_id=${__data.fields.alert_id}&${__url_time_range}"}
    # 룰별 경보 수 막대는 없애고 표를 한 줄 가득(11/16 — 맨 위 탐지 결과의 공격별 경보 수와 겹침)
    b.add("table", "경보", 0, 24, 11, [target(alert_list)],
          "고른 시간 범위의 경보(범위 전에 열려 아직 열린 것 포함). 한 행 = 경보 하나(alert_id). 심각도 = 그 경보에서 나온 최고 값, "
          "UE 수·대표 값 = 마지막 값. 상태: 열림 / 해제(clear) / 강제 종료(end, 사유) / 상태 불명(마지막 레코드 뒤 1단계 15초, "
          "2~4단계 90초 동안 아무것도 없음). 행을 누르면 아래 경보 상세가 바뀐다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True},
                                     "links": [link]},
                        "overrides": [
                            override("시작", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                            override("셀", ("custom.width", 50)),
                            override("룰", ("custom.width", 80)),
                            override("공격", ("mappings", rule_mappings()), ("custom.width", 270)),
                            override("종류", ("mappings", KIND_MAPPINGS), ("custom.cellOptions", {"type": "color-text"}),
                                     ("custom.width", 90)),
                            override("심각도", ("mappings", SEVERITY_MAPPINGS),
                                     ("custom.cellOptions", {"type": "color-background"}), ("custom.width", 80)),
                            override("UE 수", ("custom.width", 65)),
                            override("상태", ("mappings", STATUS_MAPPINGS),
                                     ("custom.cellOptions", {"type": "color-text"}), ("custom.width", 150)),
                            override("길이(초)", ("unit", "s"), ("decimals", 0), ("custom.width", 80)),
                            override("alert_id", ("custom.width", 260))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False},
                   "sortBy": [{"displayName": "시작", "desc": True}]},
          transformations=[{"id": "organize", "options": {  # map의 열 순서는 정해져 있지 않다(이름순으로 섞여 나옴)
              "excludeByName": {}, "renameByName": {},
              "indexByName": {name: i for i, name in enumerate(
                  ["시작", "셀", "룰", "공격", "종류", "심각도", "UE 수", "대표 값", "상태", "길이(초)", "alert_id"])}}}],
          new_line=True)

    # ---- 경보 상세
    b.row("경보 상세 — ${alert_id}")
    sel = f'r._measurement == "alert" and {ENV} and r.alert_id == "${{alert_id}}"'
    summary = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel})
  |> filter(fn: (r) => r._field == "mode" or r._field == "severity" or r._field == "session")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> last(column: "_time")
  |> map(fn: (r) => ({{룰: r.rule, 공격: r.rule, 종류: r.kind, 셀: r.cell,
      "마지막 이벤트": r.event, 심각도: r.severity, 모드: r.mode,
      세션: if exists r.session then r.session else ""}}))
'''
    b.add("table", "판정 요약", 0, 24, 4, [target(summary)],
          "이 경보의 룰·공격·종류(attack / anomaly)·셀과 마지막 상태. 모드 dl_missing = 분석 엔진이 DL을 못 봐 축소 판정(1단계). "
          "갈래(branch) 열은 없앴다(11/16) — 값은 InfluxDB·원본 녹화에 남아 있다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("공격", ("mappings", rule_mappings()), ("custom.width", 300)),
                                      override("심각도", ("mappings", SEVERITY_MAPPINGS),
                                               ("custom.cellOptions", {"type": "color-background"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["룰", "공격", "종류", "셀", "심각도", "마지막 이벤트", "모드", "세션"]),
          new_line=True)

    labels = [("cond_json", "성립 조건 (cond)"), ("candidates_json", "같은 모양의 다른 공격 후보 (candidates)"),
              ("conditions_json", "공격자 행동 전제 (conditions)"), ("values_json", "관측값 (values, 마지막 값)"),
              ("params_json", "설정값 (params)"), ("refs_json", "판정 창 seq 범위 (refs)")]
    detail = f'''
import "date"
import "dict"
labels = dict.fromList(pairs: [{", ".join(f'{{key: "{k}", value: "{v}"}}' for k, v in labels)}])
order = dict.fromList(pairs: [{", ".join(f'{{key: "{k}", value: {i}}}' for i, (k, _) in enumerate(labels))}])
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel})
  |> filter(fn: (r) => {" or ".join(f'r._field == "{k}"' for k, _ in labels)})
  |> group(columns: ["_field"])
  |> max(column: "_time")
  |> group()
  |> map(fn: (r) => ({{n: dict.get(dict: order, key: r._field, default: 99),
      항목: dict.get(dict: labels, key: r._field, default: r._field), 값: string(v: r._value)}}))
  |> sort(columns: ["n"])
  |> drop(columns: ["n"])
'''
    b.add("table", "판정 근거 값", 0, 15, 9, [target(detail)],
          "왜 이 경보가 났나. raise에 실린 조건·후보·전제·설정값과, update로 덮어쓴 마지막 관측값",
          field_config={"defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("항목", ("custom.width", 260)),
                                      override("값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "md", "footer": {"show": False}},
          transformations=column_order(["항목", "값"]))

    candidates = f'''
import "array"
import "date"
import "strings"
c = from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel} and r._field == "candidates_json")
  |> group()
  |> max(column: "_time")
  |> findColumn(fn: (key) => true, column: "_value")
text = if length(arr: c) > 0 then strings.replaceAll(v: strings.trim(v: c[0], cutset: "[]"), t: "\\"", u: "") else ""
ids = array.filter(arr: strings.split(v: text, t: ","), fn: (x) => x != "")
array.from(rows: if length(arr: ids) > 0 then array.map(arr: ids, fn: (x) => ({{ID: x, 공격: x}})) else [{{ID: "-", 공격: "후보 없음"}}])
'''
    b.add("table", "후보 공격", 15, 9, 9, [target(candidates)],
          "이 경보와 같은 모양을 만드는 다른 공격(candidates). 탐지 엔진은 경보끼리 묶지 않으므로, 같은 셀·같은 시간의 다른 경보와 "
          "함께 본다. 4단계 이상 유형은 여기 후보 가운데 하나다",
          field_config={"defaults": {"custom": {"align": "left"}},
                        "overrides": [override("공격", ("mappings", rule_mappings())),
                                      override("ID", ("custom.width", 90))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["ID", "공격"]), new_line=True)

    ues = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert_ue" and {ENV} and r.alert_id == "${{alert_id}}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> map(fn: (r) => ({{"걸린 시각": r._time, "UE (cell-du_ue_id-uid)": r.ue,
      "S-TMSI": if exists r.s_tmsi then r.s_tmsi else "",
      "C-RNTI": if exists r.crnti then string(v: r.crnti) else "",
      조건: if exists r.cond then r.cond else "",
      "관측 오류": if exists r.uncertain then r.uncertain else "",
      "피해자 연결 (peers)": if exists r.peers then r.peers else "",
      근거: if exists r.evidence and r.evidence then "있음" else "없음",
      "UE 관측값": if exists r.values_json then r.values_json else "",
      이벤트: r.event}}))
'''
    b.add("table", "걸린 UE", 0, 24, 8, [target(ues)],
          "어느 단말 연결이 걸렸나. raise·update에 실린 UE를 모두 모은 것(update에는 새로 걸린 UE만 옴). UE는 (셀, du_ue_id, uid)로 가리키고 "
          "세션 안에서만 유일, 같은 단말의 여러 연결은 S-TMSI로 묶는다. 관측 오류(uncertain) = 그 UE를 온전히 못 본 이유: "
          "mid_join(연결 중간부터 봄)·loss(입력 유실·한 방향 미관측)·late(늦은 줄). 비어 있으면 깨끗하게 봄 — 관측 오류뿐인 경보는 판정 보류. "
          "Blind DoS(L3-20)의 피해자 연결은 peers에 ID만 온다(근거 메시지는 오지 않음)",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("걸린 시각", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                                      override("UE 관측값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["걸린 시각", "UE (cell-du_ue_id-uid)", "S-TMSI", "C-RNTI", "조건", "관측 오류",
                                        "피해자 연결 (peers)", "근거", "UE 관측값", "이벤트"]),
          new_line=True)

    ev_kpm2 = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "evidence" and {ENV} and r.alert_id == "${{alert_id}}" and r.raw_type == "kpm2")
  |> filter(fn: (r) => r._field == "cc.RRC.ConnEstabAtt.total" or r._field == "cc.RRC.ConnEstabSucc.total"
      or r._field == "cc.RRC.ConnEstabFailCause.NoReply")
  |> map(fn: (r) => ({{_time: r._time, _value: r._value,
      _field: if r._field == "cc.RRC.ConnEstabAtt.total" then "연결 시도"
              else if r._field == "cc.RRC.ConnEstabSucc.total" then "연결 성공" else "무응답 (NoReply)"}}))
  |> group()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    ev_bars = b.add("timeseries", "근거 KPM", 0, 24, 8, [target(ev_kpm2)],
                    "경보 근거로 온 KPM2(100 ms 칸). 1단계 경보가 왜 났나. 경보 직전 2.1초(pre 21칸)·경보 중(active)·해제 뒤 1초(post)의 셀 카운터를 100 ms 그대로 "
                    "보여 준다. 무응답은 시도보다 약 1초 늦게 찍힌다. 회색 영역 = 데이터 없음(gap). 시간 범위를 경보 구간에 맞춰 본다",
                    field_config={"defaults": {"unit": "none", "min": 0, "displayName": "${__field.name}",
                                               "custom": {"drawStyle": "bars", "fillOpacity": 70, "barAlignment": -1,
                                                          "lineWidth": 1, "spanNulls": False}},
                                  "overrides": [
                                      override("연결 시도", ("color", {"mode": "fixed", "fixedColor": "blue"})),
                                      override("연결 성공", ("color", {"mode": "fixed", "fixedColor": "green"})),
                                      override("무응답 (NoReply)", ("color", {"mode": "fixed", "fixedColor": "red"}))]},
                    options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                             "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    # 상태 타임라인은 값을 다음 값이 올 때까지 늘여 그린다 — UE의 마지막 메시지는 화면 끝(지금)까지 이어져
    # 24분짜리 상태처럼 보였다(11/13). 마지막 메시지 1초 뒤에 빈 값을 끼워 거기서 끝낸다(빈 값은 투명)
    timeline = f'''
import "date"
msgs = from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "evidence" and {ENV} and r.alert_id == "${{alert_id}}" and r.raw_type == "ue_evt")
  |> filter(fn: (r) => r._field == "msg" or r._field == "dir" or r._field == "uid")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({{_time: r._time, _value: (if r.dir == "UL" then "↑ " else "↓ ") + r.msg, ue: "UE " + string(v: r.uid)}}))
  |> group(columns: ["ue"])
  |> sort(columns: ["_time"])
ends = msgs
  |> last()
  |> map(fn: (r) => ({{_time: date.add(d: {TIMELINE_END_S}s, to: r._time), _value: "", ue: r.ue}}))
union(tables: [msgs, ends])
  |> group(columns: ["ue"])
  |> sort(columns: ["_time"])
'''
    tl = b.add("state-timeline", "UE_EVENT — UE별 메시지 흐름", 0, 24, 7, [target(timeline)],
               "경보 근거로 온 UE 메시지(ue_evt, KPM1). 걸린 단말이 어떤 메시지를 어떤 순서로 주고받았나. UE마다 한 줄, ↑ 단말 → 망(UL) / ↓ 망 → 단말(DL). "
               "자세한 값은 아래 표",
               field_config={"defaults": {"displayName": "${__field.labels.ue}", "color": {"mode": "palette-classic"},
                                          "custom": {"fillOpacity": 80, "lineWidth": 1},
                                          "mappings": [{"type": "special", "options": {
                                              "match": "empty", "result": {"color": "transparent", "text": " ", "index": 0}}}]},
                               "overrides": []},
               options={"showValue": "always", "rowHeight": 0.8, "mergeValues": False, "alignValue": "left",
                        "legend": {"showLegend": False}, "tooltip": {"mode": "single"}}, new_line=True)

    messages = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "evidence" and {ENV} and r.alert_id == "${{alert_id}}" and r.raw_type == "ue_evt")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> map(fn: (r) => ({{시각: r._time, UE: "UE " + string(v: r.uid) + " (du_ue_id " + string(v: r.du_ue_id) + ")",
      방향: if r.dir == "UL" then "↑ UL" else "↓ DL", 프로토콜: r.proto, 메시지: r.msg, 구간: r.phase, 원본: r.raw_json}}))
  |> limit(n: 1000)
'''
    b.add("table", "UE_EVENT — 메시지 흐름 상세", 0, 24, 10, [target(messages)],
          "근거 메시지 하나 = 한 행. pre = 그 UE가 경보에 처음 실릴 때의 최근 메시지(최대 16줄), active = 경보 중 새 메시지. "
          "원본은 분석 엔진이 보낸 ue_evt 그대로(f에 메시지에서 꺼낸 값)",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}},
                        "overrides": [override("시각", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                                      override("방향", ("custom.width", 70)), override("프로토콜", ("custom.width", 70)),
                                      override("구간", ("custom.width", 65)),
                                      override("원본", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["시각", "UE", "구간", "방향", "프로토콜", "메시지", "원본"]), new_line=True)

    # ---- 변수·주석
    variables = [
        source_variable(),
        query_variable("cell", "셀", f'''
import "influxdata/influxdb/schema"
schema.tagValues(bucket: v.defaultBucket, tag: "cell", start: -30d,
  predicate: (r) => (r._measurement == "kpm2" or r._measurement == "alert") and {ENV})
''', multi=True, include_all=True, description="탐지 결과·상시 KPM2 그래프에 넣을 셀"),
        query_variable("alert_id", "경보", f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert" and r._field == "severity" and r.event == "raise" and {ENV})
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> map(fn: (r) => ({{_value: r.alert_id}}))
  |> unique()
  |> limit(n: 500)
''', description="경보 상세에 보일 경보. 경보 목록에서 행을 누르면 바뀐다"),
    ]
    variables[2]["sort"] = 0
    variables[2]["hide"] = 2  # 위쪽 칸은 숨긴다(11/16) — 경보 목록에서 행을 눌러 고르고, 경보 상세 행 제목에 보인다

    # 열린 경보만 지금까지, 상태 불명은 마지막 레코드(경보·근거)까지, 닫힌 경보는 clear·end까지 칠한다
    alert_regions = f'''
import "date"
import "strings"
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)")}
summary
  |> filter(fn: (r) => contains(value: r.cell, set: ${{cell:json}}))
  |> map(fn: (r) => ({{_time: r.start,
      timeEnd: if r.status == "열림" then now() else if r.status == "상태 불명" then r.active else r.last,
      text: "경보 " + r.rule + " — " + r.status + " (" + r.class + ", 셀 " + r.cell + ")", tags: r.rule}}))
'''
    gaps = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "gap" and r._field == "t_to" and {ENV})
  |> group()
  |> map(fn: (r) => ({{_time: r._time, timeEnd: time(v: r._value * 1000000), text: "데이터 없음 (gap, 경보 " + r.alert_id + ")", tags: "gap"}}))
'''
    partial = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kpm2" and {ENV} and contains(value: r.cell, set: ${{cell:json}}))
  |> filter(fn: (r) => r._field == "n" or r._field == "t_end_ms")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> filter(fn: (r) => r.n * 100 < int(v: r.agg_ms))
  |> group()
  |> map(fn: (r) => ({{_time: r._time, timeEnd: time(v: r.t_end_ms * 1000000),
      text: "칸 일부 없음 (n " + string(v: r.n) + " / " + string(v: int(v: r.agg_ms) / 100) + ", 셀 " + r.cell + ")", tags: "partial"}}))
'''
    # 세션 시작(hello)과 DU·CU 재시작(f1_evt)은 뜻이 달라 색·토글을 나눈다(D157)
    sessions = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "hello" and r._field == "seq" and {ENV})
  |> map(fn: (r) => ({{_time: r._time, text: "분석 엔진 접속 — 새 세션 " + r.session, tags: "hello"}}))
  |> group()
'''
    restarts = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "f1_evt" and r._field == "msg" and {ENV})
  |> map(fn: (r) => ({{_time: r._time, text: "DU·CU 재시작 (" + string(v: r._value) + ")", tags: "f1_evt"}}))
  |> group()
'''
    ev_gaps = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "gap" and r._field == "t_to" and {ENV} and r.alert_id == "${{alert_id}}")
  |> group()
  |> map(fn: (r) => ({{_time: r._time, timeEnd: time(v: r._value * 1000000), text: "데이터 없음 (gap)", tags: "gap"}}))
'''
    annotations = [
        annotation("경보 구간", alert_regions, "rgba(255, 152, 48, 0.12)", kpm_panels, region=True),
        annotation("데이터 없음 (gap)", gaps, "rgba(128, 128, 128, 0.25)", kpm_panels, region=True),
        annotation("칸 일부 없음", partial, "rgba(128, 128, 128, 0.12)", kpm_panels, region=True),
        annotation("세션 시작", sessions, "rgba(31, 120, 193, 1)", kpm_panels),
        annotation("DU·CU 재시작", restarts, "rgba(163, 82, 204, 1)", kpm_panels),
        annotation("근거 데이터 없음 (gap)", ev_gaps, "rgba(128, 128, 128, 0.25)", [ev_bars["id"]], region=True),
    ]
    return dashboard("portran-monitoring", "PortRAN 관제",
                     "탐지 엔진 레코드(27_) 실시간 관제 — 탐지 결과(고른 범위의 경보 수·공격별·길이), 상시 KPM2, 경보 목록, "
                     "경보 상세(근거 KPM2·KPM1). docs/dashboard-design.md 2절",
                     b, variables, annotations, refresh="5s", time_from="now-1h")


# --------------------------------------------------------------------------- 성능 (탐지 성과)

CELL_FILTER = "contains(value: r.cell, set: ${cell:json})"
TEXT_COLOR = {"mode": "fixed", "fixedColor": "text"}


def flux_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)  # Flux 문자열 이스케이프(\" \\)는 JSON과 같다


def rule_name_dict() -> str:
    """룰 ID → 짧은 공격 이름(Flux 사전). 막대 그래프는 이름 열을 그대로 축에 쓴다."""
    names = {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]}
    return "[" + ", ".join(f"{flux_str(k)}: {flux_str(short_rule_name(v))}" for k, v in names.items()) + "]"


def alerts_in_range() -> str:
    """고른 시간 범위에서 시작한(raise) 경보 = 한 행(alert_summary). 끝난 실험을 보므로 근거는 읽지 않는다."""
    return f"""{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", None)}
in_range = summary
  |> filter(fn: (r) => r.start >= v.timeRangeStart and {CELL_FILTER})"""


def stat_options(fields: str = "", values: bool = False) -> dict:
    return {"colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "justifyMode": "center",
            "reduceOptions": {"calcs": [] if values else ["lastNotNull"], "fields": fields, "values": values},
            "orientation": "vertical"}


# --------------------------------------------------------------------------- 성능 — CU 자원 (수집 오버헤드, M11)

OVERHEAD = 'r._measurement == "overhead"'
# node_id 표시: cu로 끝나면 CU(AWS 탐지 쪽은 p4-cu로 보냄, 11/16 사용자 요청). 그 밖의 값은 그대로
# 시간 그래프는 노드마다 계열 — cu로 끝나는 node_id(cu·p4-cu)는 한 노드 CU로 묶는다(두 이름이 섞이면 범례가 둘씩 나왔음, 11/16)
NODE_FLUX = ('if not exists r.node then "-" else if strings.hasSuffix(v: strings.toLower(v: r.node), suffix: "cu") '
             'then "CU" else r.node')
NODE_MAPPINGS = [{"type": "regex", "options": {"pattern": "^(.+-)?(cu|CU)$", "result": {"text": "CU", "index": 0}}}]
OVERHEAD_STALE_S = 30  # 마지막 overhead가 이보다 오래되면 '수신 멈춤'으로 칠한다(3초 구간 10개)


def overhead_pivot(fields: list[str], measurement: str = "overhead") -> str:
    """고른 시간 범위의 overhead 필드들을 시각(구간 시작)마다 한 행으로. 세션(series)마다 표가 나뉘어 있다."""
    cond = " or ".join(f'r._field == "{f}"' for f in fields)
    return f'''from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "{measurement}" and {ENV} and ({cond}))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''


def timeseries_defaults(unit: str, min_zero: bool = True, **custom) -> dict:
    return {"unit": unit, **({"min": 0} if min_zero else {}), "displayName": "${__field.name}",
            "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 25, "spanNulls": False,
                       "insertNulls": KPM2_LINE_BREAK_MS, "showPoints": "never", **custom}}


def add_overhead_rows(b: Board) -> None:
    b.row("Overhead")  # 제목은 짧게(11/16) — CU 자원 수집 오버헤드, 분석 엔진이 3초 구간마다(노드 전체와 분석 엔진 몫)
    node_info = f'''
from(bucket: v.defaultBucket)
  |> range(start: -30d)
  |> filter(fn: (r) => {OVERHEAD} and {ENV} and (r._field == "cpu_count" or r._field == "mem_total_bytes"))
  |> group(columns: ["node", "_field"])
  |> last()
  |> group(columns: ["node"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({{_time: r._time, 노드: if exists r.node then r.node else "(node_id 없음)",
      코어: if exists r.cpu_count then r.cpu_count else 0,
      메모리: if exists r.mem_total_bytes then r.mem_total_bytes else 0,
      "마지막 수신": float(v: int(v: now()) - int(v: r._time)) / 1000000000.0}}))
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
  |> drop(columns: ["_time"])
'''
    b.add("stat", "노드", 0, 8, 4, [target(node_info)],
          "overhead를 보내는 노드와 코어 수·전체 메모리(마지막 값). 노드는 node_id가 cu로 끝나면(AWS는 p4-cu) CU로 보인다. "
          "마지막 수신 = 마지막 3초 구간이 "
          f"시작한 뒤 지난 시간(데이터 시각 기준) — {OVERHEAD_STALE_S}초를 넘으면 빨강. 화면 시간 범위와 상관없이 최근 30일에서 찾는다",
          field_config={"defaults": {"color": TEXT_COLOR, "noValue": "overhead 없음"},
                        "overrides": [override("노드", ("mappings", NODE_MAPPINGS)),
                                      override("메모리", ("unit", "bytes")),
                                      override("마지막 수신", ("unit", "s"), ("decimals", 0),
                                               ("color", {"mode": "thresholds"}),
                                               ("thresholds", {"mode": "absolute", "steps": [
                                                   {"color": "green", "value": None},
                                                   {"color": "red", "value": OVERHEAD_STALE_S}]}))]},
          options=stat_options("/.*/"),
          transformations=[{"id": "organize", "options": {  # map의 열 순서는 정해져 있지 않다
              "excludeByName": {}, "renameByName": {},
              "indexByName": {name: i for i, name in enumerate(["노드", "코어", "메모리", "마지막 수신"])}}}])

    summary = f'''
import "array"
cpu = {overhead_pivot(["node_busy_cores", "cpu_count"])}
  |> filter(fn: (r) => exists r.node_busy_cores and exists r.cpu_count)
  |> map(fn: (r) => ({{_time: r._time, _value: r.node_busy_cores / float(v: r.cpu_count) * 100.0}}))
  |> group()
mem = {overhead_pivot(["mem_used_bytes", "mem_total_bytes"])}
  |> filter(fn: (r) => exists r.mem_used_bytes and exists r.mem_total_bytes and r.mem_total_bytes > 0)
  |> map(fn: (r) => ({{_time: r._time, _value: float(v: r.mem_used_bytes) / float(v: r.mem_total_bytes) * 100.0}}))
  |> group()
field = (name) => from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => {OVERHEAD} and {ENV} and r._field == name)
  |> map(fn: (r) => ({{_time: r._time, _value: float(v: r._value)}}))
  |> group()
pick = (tables) => {{
  found = tables |> findColumn(fn: (key) => true, column: "_value")
  return if length(arr: found) > 0 then found[0] else -1.0
}}
array.from(rows: [{{"평균 CPU": pick(tables: cpu |> mean()), "최대 CPU": pick(tables: cpu |> max()),
  "최대 메모리": pick(tables: mem |> max()), "분석 엔진 평균": pick(tables: field(name: "process_cores") |> mean()),
  "분석 엔진 최대 메모리": pick(tables: field(name: "process_rss_bytes") |> max())}}])
'''
    no_data = [{"type": "value", "options": {"-1": {"text": "없음", "index": 0}}}]
    b.add("stat", "고른 시간 범위 요약", 8, 16, 4, [target(summary)],
          "실험 구간 동안 노드 CPU 사용률(바쁜 코어 / 코어 수)의 평균·최대, 메모리 사용률(MemTotal − MemAvailable) 최대, "
          "분석 엔진(계측기 프로세스, process_scope self) 평균 코어 수와 최대 메모리(RSS). 탐지 엔진·전송기는 노드 값에만 섞여 있다",
          field_config={"defaults": {"color": TEXT_COLOR, "mappings": no_data},
                        "overrides": [override("평균 CPU", ("unit", "percent"), ("decimals", 1)),
                                      override("최대 CPU", ("unit", "percent"), ("decimals", 1)),
                                      override("최대 메모리", ("unit", "percent"), ("decimals", 1)),
                                      override("분석 엔진 평균", ("unit", "suffix: 코어"), ("decimals", 3)),
                                      override("분석 엔진 최대 메모리", ("unit", "bytes"))]},
          options=stat_options("/.*/"), new_line=True)

    cpu_pct = f'''
import "strings"
{overhead_pivot(["node_busy_cores", "cpu_count"])}
  |> filter(fn: (r) => exists r.node_busy_cores and exists r.cpu_count)
  |> map(fn: (r) => ({{_time: r._time, node: {NODE_FLUX},
      "CPU 사용률": r.node_busy_cores / float(v: r.cpu_count) * 100.0}}))
  |> group(columns: ["node"])
  |> sort(columns: ["_time"])
'''
    b.add("timeseries", "CPU 사용률", 0, 12, 8, [target(cpu_pct)],
          "노드 전체. 구간(3초) 동안 노드가 바쁘게 돈 코어 수 / 코어 수. 분석 엔진·탐지 엔진·전송기·CU가 모두 들어 있다",
          field_config={"defaults": {**timeseries_defaults("percent"), "max": 100,
                                     "color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []},
          options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
                   "tooltip": {"mode": "multi", "sort": "none"}})

    cpu_split = f'''
import "strings"
{overhead_pivot(["node_busy_cores", "process_cores", "cpu_count"])}
  |> filter(fn: (r) => exists r.node_busy_cores and exists r.process_cores)
  |> map(fn: (r) => ({{_time: r._time, node: {NODE_FLUX},
      "분석 엔진": r.process_cores,
      "그 밖 (탐지 엔진·전송기·CU 등)": if r.node_busy_cores > r.process_cores then r.node_busy_cores - r.process_cores else 0.0,
      "코어 수": if exists r.cpu_count then float(v: r.cpu_count) else 0.0}}))
  |> group(columns: ["node"])
  |> sort(columns: ["_time"])
'''
    b.add("timeseries", "CPU 내역", 12, 12, 8, [target(cpu_split)],
          "노드가 쓴 코어 수를 분석 엔진(계측기 프로세스)과 그 밖으로 나눠 쌓았다. 점선 = 노드 코어 수(위쪽 한계). "
          "커널 안에서 도는 eBPF 프로그램 시간은 그 이벤트를 일으킨 CU 스레드 쪽(그 밖)에 잡힌다",
          field_config={"defaults": timeseries_defaults("none", stacking={"mode": "normal", "group": "A"}),
                        "overrides": [
                            override("분석 엔진", ("color", {"mode": "fixed", "fixedColor": "orange"})),
                            override("그 밖 (탐지 엔진·전송기·CU 등)", ("color", {"mode": "fixed", "fixedColor": "blue"})),
                            override("코어 수", ("color", {"mode": "fixed", "fixedColor": "text"}),
                                     ("custom.stacking", {"mode": "none", "group": "B"}), ("custom.fillOpacity", 0),
                                     ("custom.lineStyle", {"fill": "dash", "dash": [6, 4]}))]},
          options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                   "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    mem_use = f'''
import "strings"
{overhead_pivot(["mem_used_bytes", "mem_total_bytes"])}
  |> filter(fn: (r) => exists r.mem_used_bytes)
  |> map(fn: (r) => ({{_time: r._time, node: {NODE_FLUX},
      "사용 중": float(v: r.mem_used_bytes),
      "전체": if exists r.mem_total_bytes then float(v: r.mem_total_bytes) else 0.0}}))
  |> group(columns: ["node"])
  |> sort(columns: ["_time"])
'''
    b.add("timeseries", "메모리 사용량", 0, 12, 8, [target(mem_use)],
          "노드 전체. 사용 중 = MemTotal − MemAvailable(구간 끝 순간값). 점선 = 전체 메모리",
          field_config={"defaults": {**timeseries_defaults("bytes"), "color": {"mode": "fixed", "fixedColor": "green"}},
                        "overrides": [override("전체", ("color", {"mode": "fixed", "fixedColor": "text"}),
                                               ("custom.fillOpacity", 0),
                                               ("custom.lineStyle", {"fill": "dash", "dash": [6, 4]}))]},
          options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                   "tooltip": {"mode": "multi", "sort": "none"}})

    mem_split = f'''
import "strings"
{overhead_pivot(["mem_used_bytes", "process_rss_bytes"])}
  |> filter(fn: (r) => exists r.mem_used_bytes and exists r.process_rss_bytes)
  |> map(fn: (r) => ({{_time: r._time, node: {NODE_FLUX},
      "분석 엔진 (RSS)": float(v: r.process_rss_bytes),
      "그 밖": if r.mem_used_bytes > r.process_rss_bytes then float(v: r.mem_used_bytes - r.process_rss_bytes) else 0.0}}))
  |> group(columns: ["node"])
  |> sort(columns: ["_time"])
'''
    b.add("timeseries", "메모리 내역", 12, 12, 8, [target(mem_split)],
          "노드 사용 메모리를 분석 엔진(계측기 프로세스 resident)과 그 밖으로 나눠 쌓았다",
          field_config={"defaults": timeseries_defaults("bytes", stacking={"mode": "normal", "group": "A"}),
                        "overrides": [
                            override("분석 엔진 (RSS)", ("color", {"mode": "fixed", "fixedColor": "orange"})),
                            override("그 밖", ("color", {"mode": "fixed", "fixedColor": "green"}))]},
          options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                   "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    # 링크 값은 SCTP 패킷만 센다(F1AP·NGAP 시그널링 — F1-U 사용자 데이터는 빠짐, 탐지 쪽 11/13)
    def link_rate(kind: str) -> str:
        """overhead_link의 <방향>_<kind> 구간 증가분 ÷ 구간 길이 = 초당 값. 들어옴·나감 × 링크마다 한 계열."""
        return f'''
links = {overhead_pivot([f"ingress_{kind}", f"egress_{kind}", "t_end_ms"], measurement="overhead_link")}
  |> map(fn: (r) => ({{r with secs: float(v: r.t_end_ms - int(v: r._time) / 1000000) / 1000.0,
      link: if not exists r.role then r.iface else if r.role == "f1" then "F1" else if r.role == "n2" then "N2"
            else if r.role == "f1+n2" then "F1+N2" else r.role}}))
  |> filter(fn: (r) => r.secs > 0.0)
inbound = links
  |> filter(fn: (r) => exists r.ingress_{kind})
  |> map(fn: (r) => ({{_time: r._time, link: r.link, iface: r.iface, _value: float(v: r.ingress_{kind}) / r.secs,
      dir: if r.link == "F1" then "들어옴 (DU → CU)" else if r.link == "N2" then "들어옴 (AMF → CU)" else "들어옴"}}))
  |> group()
outbound = links
  |> filter(fn: (r) => exists r.egress_{kind})
  |> map(fn: (r) => ({{_time: r._time, link: r.link, iface: r.iface, _value: float(v: r.egress_{kind}) / r.secs,
      dir: if r.link == "F1" then "나감 (CU → DU)" else if r.link == "N2" then "나감 (CU → AMF)" else "나감"}}))
  |> group()
union(tables: [inbound, outbound])
  |> group(columns: ["link", "dir", "iface"])
  |> sort(columns: ["_time"])
'''

    link_note = ("선언한 NIC마다 SCTP 패킷(F1AP·NGAP 시그널링)만 센 구간 증가분 ÷ 구간 길이(3초 평균) — F1-U 사용자 데이터(GTP-U)는 "
                 "들어 있지 않다. 계열 = 링크(F1: CU ↔ DU, N2: CU ↔ 코어 AMF) × 방향 — 위 = 들어옴, 아래 = 나감(CU 기준). "
                 "네트워크 카드(NIC) 이름은 범례에서 빼고 툴팁의 iface에 둔다. 첫 구간이나 커널 맵을 못 읽은 구간은 빈칸")
    for x, title, kind, unit, extra in (
            (0, "F1·N2 SCTP 트래픽", "wire_bytes", "binBps",
             " 단위 바이트/초. 바이트는 이더넷 헤더 포함, FCS 제외."),
            (12, "F1·N2 SCTP 패킷", "sctp_packets", "pps",
             " 단위 패킷/초. 공격으로 시그널링이 몰리는 모양은 바이트보다 패킷 수에서 더 잘 보인다. GSO로 묶인 패킷은 세그먼트 수만큼 센다.")):
        b.add("timeseries", title, x, 12, 8, [target(link_rate(kind))], link_note + "." + extra,
              field_config={"defaults": {**timeseries_defaults(unit, min_zero=False),
                                         "displayName": "${__field.labels.link} ${__field.labels.dir}",
                                         "noValue": "링크 값 없음"},
                            "overrides": [override(".*나감.*", ("custom.transform", "negative-Y"), regex=True)]},
              options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                       "tooltip": {"mode": "multi", "sort": "none"}}, new_line=x == 12)

    load = f'''
{overhead_pivot(["node_busy_cores", "cpu_count"])}
  |> filter(fn: (r) => exists r.node_busy_cores and exists r.cpu_count)
  |> map(fn: (r) => ({{_time: r._time, _value: r.node_busy_cores / float(v: r.cpu_count) * 100.0}}))
  |> group()
  |> sort(columns: ["_time"])
  |> map(fn: (r) => ({{_time: r._time, "CPU 사용률": r._value}}))
'''
    attempts = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kpm2" and {ENV} and r._field == "cc.RRC.ConnEstabAtt.total"
      and contains(value: r.cell, set: ${{cell:json}}))
  |> group()
  |> aggregateWindow(every: 3s, fn: sum, createEmpty: false, timeSrc: "_start")
  |> map(fn: (r) => ({{_time: r._time, "RRC 연결 시도": r._value}}))
'''
    b.add("timeseries", "CPU 사용률 · RRC 연결 시도", 0, 24, 8,
          [target(load, "A"), target(attempts, "B")],
          "공격으로 연결 시도가 몰릴 때 CU CPU가 얼마나 오르나. 왼쪽 축 = 노드 CPU 사용률, 오른쪽 축(막대) = 상시 KPM2 RRC 연결 시도"
          "(위쪽 셀 변수로 고른 셀의 합). 둘 다 3초 구간이라 칸끼리 겹친다. 상시 KPM2가 없는 출처(샘플 등)에서는 RRC 연결 시도가 안 보인다",
          field_config={"defaults": {**timeseries_defaults("percent"), "max": 100,
                                     "color": {"mode": "fixed", "fixedColor": "blue"}},
                        "overrides": [override("RRC 연결 시도.*", ("unit", "none"), ("max", None),
                                               ("custom.axisPlacement", "right"), ("custom.drawStyle", "bars"),
                                               ("custom.fillOpacity", 50), ("custom.barAlignment", 1),
                                               ("color", {"mode": "fixed", "fixedColor": "orange"}), regex=True)]},
          # 범례는 오른쪽 표(이름·평균·최대) — 아래 목록이면 Grafana가 오른쪽 축 계열을 따로 떼어 두고, 오른쪽 목록은 값이
          # 줄마다 어긋난다(사용자 확인 11/13). 표 모드는 오른쪽 축 계열에 '(right y-axis)'를 붙이는데 끌 설정이 없다
          options={"legend": {"displayMode": "table", "placement": "right", "showLegend": True, "calcs": ["mean", "max"]},
                   "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)


def add_detection_rows(b: Board) -> None:
    """탐지 결과 줄 — 고른 시간 범위에 시작한 경보의 공격별 수, 경보 길이, 공격별 결과.
    관제 대시보드 맨 위에 둔다(11/16 사용자 결정 — 요약 줄을 없애고 성능 대시보드에서 옮김)."""
    b.row("탐지 결과")
    # 경보 수 — 종류별 stat은 없앴다(11/16 사용자 요청)
    per_attack = f'''
import "dict"
names = {rule_name_dict()}
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert" and r._field == "severity" and r.event == "raise" and {ENV}
      and {CELL_FILTER})
  |> group(columns: ["rule"])
  |> count()
  |> group()
  |> sort(columns: ["_value"], desc: true)
  |> map(fn: (r) => ({{rule: r.rule, 공격: dict.get(dict: names, key: r.rule, default: r.rule), "경보 수": r._value}}))
  |> keep(columns: ["공격", "경보 수"])
'''
    b.add("barchart", "공격별 경보 수", 0, 12, 11, [target(per_attack)],
          "실험 동안 어떤 공격·이상 유형이 몇 번 울렸나(raise 기준). 같은 공격에 여러 룰이 함께 울릴 수 있다",
          field_config={"defaults": {"unit": "none", "min": 0, "decimals": 0,
                                     "color": {"mode": "fixed", "fixedColor": "orange"},
                                     "custom": {"fillOpacity": 80, "lineWidth": 1, "gradientMode": "none"}},
                        "overrides": []},
          options={"orientation": "horizontal", "xField": "공격", "showValue": "auto", "groupWidth": 0.7, "barWidth": 0.9,
                   "stacking": "none", "legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
                   "tooltip": {"mode": "single", "sort": "none"}})

    durations = f'''
import "date"
import "strings"
{alerts_in_range()}
in_range
  |> filter(fn: (r) => r.event == "clear" or r.event == "end")
  |> map(fn: (r) => ({{alert_id: r.alert_id, "경보 길이(초)": float(v: int(v: r.last) - int(v: r.start)) / 1000000000.0}}))
  |> keep(columns: ["경보 길이(초)"])
'''
    b.add("histogram", "경보 길이 분포", 12, 12, 11, [target(durations)],
          "경보가 얼마나 오래 이어졌나 — raise부터 clear·end까지(= duration_ms). 가로축 = 경보 길이(초), "
          "세로축 = 경보 수. 해제·강제 종료된 경보만 — 아직 끝나지 않은 경보는 빠진다",
          field_config={"defaults": {"unit": "none", "color": {"mode": "fixed", "fixedColor": "orange"},
                                     "custom": {"fillOpacity": 70, "lineWidth": 1}}, "overrides": []},
          options={"bucketCount": 20, "combine": False,
                   "legend": {"displayMode": "list", "placement": "bottom", "showLegend": False}},
          new_line=True)

    per_rule = f'''
import "date"
import "strings"
{alerts_in_range()}
in_range
  |> map(fn: (r) => ({{rule: r.rule, class: r.class,
      high: if r.sev == 2 then 1 else 0,
      cleared: if r.event == "clear" then 1 else 0,
      ended: if r.event == "end" then 1 else 0,
      open: if r.event == "raise" or r.event == "update" then 1 else 0,
      secs: if r.event == "clear" or r.event == "end" then float(v: int(v: r.last) - int(v: r.start)) / 1000000000.0 else 0.0}}))
  |> group(columns: ["rule", "class"])
  |> reduce(identity: {{n: 0, high: 0, cleared: 0, ended: 0, open: 0, secs: 0.0, longest: 0.0}},
      fn: (r, accumulator) => ({{n: accumulator.n + 1, high: accumulator.high + r.high,
        cleared: accumulator.cleared + r.cleared, ended: accumulator.ended + r.ended, open: accumulator.open + r.open,
        secs: accumulator.secs + r.secs, longest: if r.secs > accumulator.longest then r.secs else accumulator.longest}}))
  |> group()
  |> sort(columns: ["n"], desc: true)
  |> map(fn: (r) => ({{rule: r.rule, 공격: r.rule, 종류: r.class, "경보 수": r.n,
      "high 도달": r.high, 해제: r.cleared, "강제 종료": r.ended, "끝이 안 옴": r.open,
      "평균 길이(초)": if r.cleared + r.ended > 0 then r.secs / float(v: r.cleared + r.ended) else 0.0,
      "최대 길이(초)": r.longest}}))
'''
    # Flux map의 열 순서는 정해져 있지 않아서 표에서 순서를 정한다
    columns = ["공격", "종류", "경보 수", "high 도달", "해제", "강제 종료", "끝이 안 옴", "평균 길이(초)", "최대 길이(초)"]
    b.add("table", "공격별 경보 결과", 0, 24, 9, [target(per_rule)],
          "공격(룰)·종류마다 경보 수와 끝난 모습. high 도달 = 심각도가 한 번이라도 high까지 오른 경보(한 번 오르면 내려가지 않음, 룰마다 조건이 다르고 L3-24·L3-06·이상 유형·판정 보류는 늘 medium). 강제 종료 = end"
          "(분석 엔진 재시작·입력 끊김·입력 멈춤). 끝이 안 옴 = clear·end가 오지 않은 경보. 길이는 해제·강제 종료된 경보만",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}},
                        "overrides": [override("공격", ("mappings", rule_mappings())),
                                      override("종류", ("mappings", KIND_MAPPINGS),
                                               ("custom.cellOptions", {"type": "color-text"}), ("custom.width", 90)),
                                      *[override(name, ("custom.width", 105)) for name in columns[2:7]],
                                      override("평균 길이(초)", ("decimals", 1), ("custom.width", 115)),
                                      override("최대 길이(초)", ("decimals", 1), ("custom.width", 115))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False},
                   "sortBy": [{"displayName": "경보 수", "desc": True}]},
          transformations=[{"id": "organize", "options": {
              "excludeByName": {"rule": True}, "renameByName": {},
              "indexByName": {name: i for i, name in enumerate(columns)}}}],
          new_line=True)


def performance() -> dict:
    b = Board()

    # 탐지 결과는 관제로 옮기고 경보·입력 품질 줄은 없앴다(11/16 사용자 결정) — 성능은 CU 자원만
    # ---- CU 자원 (수집 오버헤드, M11)
    add_overhead_rows(b)

    variables = [
        source_variable(),
        query_variable("cell", "셀", f'''
import "influxdata/influxdb/schema"
schema.tagValues(bucket: v.defaultBucket, tag: "cell", start: -30d,
  predicate: (r) => (r._measurement == "kpm2" or r._measurement == "alert") and {ENV})
''', multi=True, include_all=True, description="CPU 사용률 · RRC 연결 시도 그래프의 RRC 연결 시도에 넣을 셀"),
    ]
    return dashboard("portran-performance", "PortRAN 성능",
                     "CU 자원(수집 오버헤드 — 노드·분석 엔진 CPU·메모리, F1·N2 SCTP). docs/dashboard-design.md 3절",
                     b, variables, [], refresh="1m", time_from="now-24h")


# --------------------------------------------------------------------------- 알림 — Slack (M12)

# 알림은 AWS 실측에서만 보낸다(11/13 사용자 결정). On-Premise(lab)는 받기 시작하면 더한다.
NOTIFY_SOURCE = "p4"
NOTIFY_INTERVAL = "10s"           # 규칙을 조회하는 주기
ATTACK_LOOKBACK_S = 6 * 3600      # 공격 경보를 찾는 범위. 이보다 오래 열린 경보는 '끝 소식 없음'으로 끝난다
COLLECT_STOP_S = 300              # 수집 멈춤: 마지막 레코드 뒤 이만큼 아무것도 없으면
COLLECT_LOOKBACK_S = 3600         # 이 범위에 아무것도 없으면 테스트베드를 끈 것으로 보고 알리지 않는다
ALERTING_OUT = ROOT / "provisioning" / "alerting" / "portran.json"
SLACK_ALL = "PortRAN Slack"
SLACK_NO_RESOLVE = "PortRAN Slack (해제 알림 없음)"

# 알림 메시지(Slack). 한 알림 = 경보 하나(group_by alert_id)라서 .CommonLabels·.CommonAnnotations만 쓴다.
# provisioning 파일은 환경변수를 바꿔 넣으므로 템플릿에 '$'를 쓰지 않는다.
NOTIFY_TEMPLATE = (
    '{{ define "portran.title" }}{{ if eq .CommonLabels.notify "collect" }}⚠️ PortRAN 수집 멈춤'
    '{{ else if eq .Status "firing" }}🚨 PortRAN 공격 경보{{ else }}✅ PortRAN 공격 경보 끝{{ end }}{{ end }}\n'
    '{{ define "portran.text" }}{{ if eq .CommonLabels.notify "collect" }}{{ .CommonAnnotations.summary }}'
    '{{ else }}*{{ .CommonLabels.attack }}* · 셀 {{ .CommonLabels.cell }} · '
    '{{ if eq .Status "firing" }}{{ .CommonAnnotations.severity }} · 시작 {{ .CommonLabels.start }}'
    '{{ else }}{{ .CommonAnnotations.status }}{{ end }}\n'
    # ExternalURL(= GF_SERVER_ROOT_URL)은 Grafana가 늘 '/'로 끝나게 맞춘다
    '<{{ .ExternalURL }}d/portran-monitoring?var-source=' + NOTIFY_SOURCE + '&var-alert_id={{ .CommonLabels.alert_id }}|경보 상세 보기>'
    '{{ end }}{{ end }}\n'
)


def alert_rule(uid: str, title: str, query: str, lookback_s: int, threshold: float, labels: dict,
               annotations: dict) -> dict:
    """InfluxDB 조회(A) → 계열마다 마지막 값(B) → B > threshold면 울림(C)."""
    return {
        "uid": uid, "title": title, "condition": "C",
        "data": [
            {"refId": "A", "relativeTimeRange": {"from": lookback_s, "to": 0}, "datasourceUid": DS["uid"],
             "model": {"refId": "A", "query": query.strip("\n")}},
            {"refId": "B", "relativeTimeRange": {"from": 0, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": "last",
                       "settings": {"mode": "dropNN"}}},
            {"refId": "C", "relativeTimeRange": {"from": 0, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "C", "type": "threshold", "expression": "B",
                       "conditions": [{"evaluator": {"type": "gt", "params": [threshold]}}]}},
        ],
        # 조회 결과가 없으면 정상, 조회가 실패하면 마지막 상태를 유지(InfluxDB가 잠깐 죽어도 Slack에 오류를 쏟지 않게)
        "noDataState": "OK", "execErrState": "KeepLast", "for": "0s",
        "labels": labels, "annotations": annotations, "isPaused": False,
    }


def alerting() -> dict:
    env = f'r.env == "{NOTIFY_SOURCE}"'
    # 공격 경보(kind attack)마다 한 계열. 값: 열림(raise·update) = 1(medium)·2(high), 해제 = 0, 강제 종료 = -1.
    # 경보 상태는 alert_summary(관제 대시보드와 같은 계산)로 정한다
    attacks = f'''
import "date"
import "dict"
import "strings"
names = {rule_name_dict()}
{alert_summary(f"-{ATTACK_LOOKBACK_S}s", "-5m", stop="now()").replace(ENV, env)}
summary
  |> filter(fn: (r) => r.kind == "attack")
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: r.rule, cell: r.cell,
      attack: dict.get(dict: names, key: r.rule, default: r.rule),
      start: strings.replaceAll(v: strings.substring(v: string(v: date.add(d: 9h, to: r.start)), start: 0, end: 19), t: "T", u: " "),
      _time: now(),
      _value: if r.event == "raise" or r.event == "update" then (if r.sev == 2 then 2.0 else 1.0)
              else if r.event == "end" then -1.0 else 0.0}}))
  |> group(columns: ["alert_id", "rule", "cell", "attack", "start"])
'''
    measurements = {"kpm2": "n", "overhead": "seq", "alert": "severity", "evidence": "seq", "hello": "seq"}
    seen = " or ".join(f'(r._measurement == "{m}" and r._field == "{f}")' for m, f in measurements.items())
    collect = f'''
from(bucket: v.defaultBucket)
  |> range(start: -{COLLECT_LOOKBACK_S}s)
  |> filter(fn: (r) => {env} and ({seen}))
  |> keep(columns: ["_time"])
  |> group()
  |> max(column: "_time")
  |> map(fn: (r) => ({{_time: now(), _value: float(v: int(v: now()) - int(v: r._time)) / 1000000000.0}}))
'''
    rules = [
        alert_rule("portran-attack", "공격 경보 (AWS)", attacks, ATTACK_LOOKBACK_S, 0,
                   {"notify": "attack"},
                   # 조회 결과가 없을 때(NoData)는 .Values가 비어 있어 B를 꺼내면 템플릿이 깨진다 — with로 감싼다
                   {"severity": '{{ with .Values }}{{ if eq .B.Value 2.0 }}high{{ else }}medium{{ end }}{{ end }}',
                    "status": '{{ with .Values }}{{ if gt .B.Value 0.0 }}끝 소식 없음(6시간 안에 해제·강제 종료가 오지 않음)'
                              '{{ else if lt .B.Value 0.0 }}강제 종료{{ else }}해제{{ end }}{{ end }}',
                    "description": "AWS(p4) 공격 경보(kind attack)가 열리면 울리고, 해제·강제 종료되면 끝난다. "
                                   "이상 유형·판정 보류 경보는 알리지 않는다(M12)"}),
        alert_rule("portran-collect-stop", "수집 멈춤 (AWS)", collect, COLLECT_LOOKBACK_S, COLLECT_STOP_S,
                   {"notify": "collect"},
                   {"summary": f"AWS(p4)에서 {COLLECT_STOP_S // 60}분 넘게 데이터(상시 KPM2·오버헤드·경보·근거)가 오지 않아요. "
                               "{{ with .Values }}마지막 수신 {{ printf \"%.0f\" .B.Value }}초 전. {{ end }}실험을 일부러 멈춘 거라면 무시하세요",
                    "description": f"마지막 레코드 뒤 {COLLECT_STOP_S}초. 최근 {COLLECT_LOOKBACK_S // 60}분에 아무것도 없으면 "
                                   "테스트베드를 끈 것으로 보고 울리지 않는다. 다시 들어와도 알리지 않는다"}),
    ]
    slack = lambda uid, no_resolve: {"uid": uid, "type": "slack", "disableResolveMessage": no_resolve, "settings": {
        "url": "${SLACK_WEBHOOK_URL}", "title": '{{ template "portran.title" . }}', "text": '{{ template "portran.text" . }}'}}
    return {
        "apiVersion": 1,
        "groups": [{"orgId": 1, "name": "PortRAN 알림", "folder": "PortRAN", "interval": NOTIFY_INTERVAL, "rules": rules}],
        "contactPoints": [
            {"orgId": 1, "name": SLACK_ALL, "receivers": [slack("portran-slack", False)]},
            {"orgId": 1, "name": SLACK_NO_RESOLVE, "receivers": [slack("portran-slack-no-resolve", True)]},
        ],
        # 한 알림 = 경보 하나. 같은 알림을 다시 보내는 간격은 길게(오래 열린 경보로 Slack이 시끄럽지 않게)
        "policies": [{"orgId": 1, "receiver": SLACK_ALL, "group_by": ["alertname", "alert_id"],
                      "group_wait": "0s", "group_interval": "10s", "repeat_interval": "24h",
                      "routes": [{"receiver": SLACK_NO_RESOLVE, "object_matchers": [["notify", "=", "collect"]]}]}],
        "templates": [{"orgId": 1, "name": "portran", "template": NOTIFY_TEMPLATE}],
    }


# --------------------------------------------------------------------------- 쓰기

BUILDERS = {OUT_DIR / "monitoring.json": monitoring, OUT_DIR / "performance.json": performance,
            ALERTING_OUT: alerting}


def render() -> dict[Path, str]:
    return {path: json.dumps(build(), ensure_ascii=False, indent=2) + "\n" for path, build in BUILDERS.items()}


def main(argv: list[str]) -> int:
    outputs = render()
    if "--check" in argv:
        stale = [p.name for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"대시보드·알림 JSON이 grafana/build.py와 다릅니다: {', '.join(stale)} — python grafana/build.py로 다시 만드세요")
            return 1
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print(f"썼음: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
