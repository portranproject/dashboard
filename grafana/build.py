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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "dashboards"
RULE_NAMES = json.loads((ROOT / "rule-names.json").read_text(encoding="utf-8"))
DS = {"type": "influxdb", "uid": "portran-influxdb"}

# 데이터 출처 선택 (docs/dashboard-design.md 1절). 지금은 AWS만 받는다. On-Premise를 받게 되면 ("On-Premise", "lab")을 더한다.
SOURCES = [("AWS", "p4"), ("재생", "replay"), ("샘플", "sample")]

# 상태 불명: 열린 경보에 마지막 레코드 뒤 이 시간 동안 아무것도 없으면 (27_ §7)
STALE_NS = {"1": 15_000_000_000, "other": 90_000_000_000}
CELL_LIMIT = 96  # 셀 UE 컨텍스트 한도 (27_ §5.3, ext.UeCtxMax ≥ 90%면 high)


# --------------------------------------------------------------------------- 공통 조각

def rule_mappings() -> list[dict]:
    names = {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]}
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


def alert_summary(alert_start: str, evidence_start: str) -> str:
    """경보 하나 = 한 행으로 합친 Flux(끝은 ungroup). 열: alert_id, rule, stage, kind, cell, start(raise), last(마지막 경보 레코드),
    active(경보·근거 중 마지막), event(마지막 이벤트), sev(0·1·2 최대), ues·rep·key·reason(마지막 값, 문자열), status(열림·해제·
    강제 종료 (사유)·상태 불명), class(공격·이상 유형·판정 보류).
    pivot은 경보마다 필드 구성이 달라 표 모양이 갈리므로 쓰지 않고, 값을 문자열 한 열로 모아 reduce로 합친다.
    상태 불명 판단에 쓸 마지막 근거 시각도 같은 모양으로 붙여(union) 함께 합친다(join.left는 reduce 결과에서 실패함)."""
    return f"""alerts = from(bucket: v.defaultBucket)
  |> range(start: {alert_start}, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert" and {ENV})
  |> filter(fn: (r) => r._field == "severity" or r._field == "ues_total" or r._field == "rep_value"
      or r._field == "rep_key" or r._field == "reason")
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: r.rule, stage: r.stage, kind: r.kind, cell: r.cell, event: r.event,
      t: r._time, f: r._field, s: string(v: r._value), a: true}}))
  |> group()
evidence = from(bucket: v.defaultBucket)
  |> range(start: {evidence_start}, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "evidence" and r._field == "seq" and {ENV})
  |> group(columns: ["alert_id"])
  |> max(column: "_time")
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: "", stage: "", kind: "", cell: "", event: "", t: r._time, f: "evidence",
      s: "", a: false}}))
  |> group()
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
            "description": "AWS = AWS 테스트베드 p4 · 재생 = replay로 다시 보낸 데이터 · 샘플 = 탐지 쪽 시험 샘플. "
                           "On-Premise(연구실)는 받기 시작하면 더한다"}


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
    return {"name": name, "datasource": DS, "enable": True, "hide": False, "iconColor": color,
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

    # ---- 요약
    b.row("요약 — 지금")
    # 상태 불명 판단에는 최근 근거만 있으면 된다(근거가 5분 넘게 없으면 이미 상태 불명이다)
    open_alerts = f'''
import "array"
import "date"
import "strings"
{alert_summary("-7d", "-5m")}
// map 결과에 그대로 옮긴 열(alert_id)이 하나도 없으면 InfluxDB 2.7의 Flux가 조건식 값을 null로 만든다 — 그래서 alert_id를 함께 둔다
counted = summary
  |> filter(fn: (r) => r.status == "열림" or r.status == "상태 불명")
  |> map(fn: (r) => ({{alert_id: r.alert_id, class: if r.status == "열림" then r.class else "상태 불명", _value: 1}}))
  |> keep(columns: ["class", "_value"])
zeros = array.from(rows: [{{class: "공격", _value: 0}}, {{class: "이상 유형", _value: 0}}, {{class: "판정 보류", _value: 0}},
                         {{class: "상태 불명", _value: 0}}])
union(tables: [counted, zeros])
  |> group(columns: ["class"])
  |> sum()
'''
    b.add("stat", "열린 경보", 0, 9, 5, [target(open_alerts)],
          "지금 울리고 있는 경보 수(최근 7일 안에 열려 아직 clear·end가 오지 않은 것). 공격 경보만 '탐지'로 세고, "
          "4단계 이상 유형과 판정 보류 경보는 따로 센다(27_ §5.5). 상태 불명 = 열린 채 1단계 15초, 2~4단계 90초 동안 레코드가 없는 "
          "경보(탐지 엔진이 죽었거나 다시 떴을 수 있음, 27_ §7)",
          field_config={"defaults": {"displayName": "${__field.labels.class}", "unit": "none",
                                     "thresholds": {"mode": "absolute", "steps": [
                                         {"color": "green", "value": None}, {"color": "red", "value": 1}]}},
                        "overrides": []},
          options={"colorMode": "background", "graphMode": "none", "textMode": "value_and_name",
                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "orientation": "vertical"})

    max_sev = f'''
import "array"
import "date"
import "strings"
{alert_summary("-7d", "-5m")}
union(tables: [summary |> filter(fn: (r) => r.status == "열림") |> keep(columns: ["sev"]), array.from(rows: [{{sev: 0}}])])
  |> max(column: "sev")
  |> map(fn: (r) => ({{_value: string(v: r.sev)}}))
'''
    b.add("stat", "최고 심각도 (열린 경보)", 9, 3, 5, [target(max_sev)],
          "열린 경보가 그 경보에서 낸 심각도 가운데 가장 높은 것. high는 한 번 오르면 내려가지 않는다(27_ §5.3)",
          field_config={"defaults": {"mappings": SEVERITY_MAPPINGS, "displayName": "최고 심각도"}, "overrides": []},
          options={"colorMode": "background", "graphMode": "none", "textMode": "value",
                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/", "values": False}})

    freshness = f'''
from(bucket: v.defaultBucket)
  |> range(start: -30d)
  |> filter(fn: (r) => {ENV} and ((r._measurement == "kpm2" and r._field == "n")
      or (r._measurement == "alert" and r._field == "severity")
      or (r._measurement == "evidence" and r._field == "seq")))
  |> group(columns: ["_measurement"])
  |> max(column: "_time")
  |> map(fn: (r) => ({{row: 1, _time: r._time,
      name: if r._measurement == "kpm2" then "상시 KPM2" else if r._measurement == "alert" then "경보" else "근거",
      _value: float(v: int(v: now()) - int(v: r._time)) / 1000000000.0}}))
  |> group()
  |> pivot(rowKey: ["row"], columnKey: ["name"], valueColumn: "_value")
  |> drop(columns: ["row", "_time"])
'''
    b.add("stat", "수집 상태 — 마지막 수신 뒤", 12, 6, 5, [target(freshness)],
          "데이터 시각 기준으로 마지막 레코드가 몇 초 전인가. 상시 KPM2는 3초마다 와야 하고(실험 때 상시 경로를 켰을 때), "
          "경보·근거는 경보가 있을 때만 온다",
          field_config={"defaults": {"unit": "s", "decimals": 0,
                                     "thresholds": {"mode": "absolute", "steps": [
                                         {"color": "green", "value": None}, {"color": "orange", "value": 15},
                                         {"color": "red", "value": 60}]}}, "overrides": []},
          options={"colorMode": "value", "graphMode": "none", "textMode": "value_and_name",
                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "orientation": "vertical"})

    session = f'''
import "array"
last = from(bucket: v.defaultBucket)
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "hello" and r._field == "seq" and {ENV})
  |> group()
  |> max(column: "_time")
  |> findColumn(fn: (key) => true, column: "session")
restarts = from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "f1_evt" and r._field == "msg" and {ENV})
  |> group()
  |> count()
  |> findColumn(fn: (key) => true, column: "_value")
array.from(rows: [{{"지금 세션": if length(arr: last) > 0 then last[0] else "-",
                    "재시작 (범위 안)": if length(arr: restarts) > 0 then restarts[0] else 0}}])
'''
    b.add("stat", "분석 엔진 세션 · DU·CU 재시작", 18, 6, 5, [target(session)],
          "마지막 hello의 세션(분석 엔진이 다시 뜨면 바뀜)과, 고른 시간 범위 안의 DU·CU 재시작(f1_evt) 수",
          field_config={"defaults": {"unit": "none"}, "overrides": []},
          options={"colorMode": "none", "graphMode": "none", "textMode": "value_and_name", "orientation": "vertical",
                   "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/", "values": False}},
          new_line=True)

    # ---- 상시 KPM2
    b.row("상시 KPM2 — 셀 ${cell}, 3초 묶음 (TeleRAN Table II)")
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
    bars = b.add("timeseries", "RRC 연결 시도 · 성공 · 무응답 (3초마다)", 0, 24, 9, [target(kpm_bars)],
                 "셀에 무슨 일이 일어나고 있나. UE 컨텍스트 고갈 공격(1단계)은 시도와 무응답이 함께 솟고 성공은 그대로다(27_ §4.1). "
                 "주황 영역 = 경보 구간, 회색 영역 = 데이터 없음(gap)·칸 일부 없음, 세로선 = 세션 시작·재시작",
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
    lines = b.add("timeseries", f"UE 컨텍스트 · 연결 UE 수 — 셀 한도 {CELL_LIMIT}", 0, 24, 8, [target(kpm_lines)],
                  f"셀 자원이 고갈되고 있나. 빨간 선 = 셀 한도 {CELL_LIMIT}의 90%(1·2단계 경보가 high가 되는 기준, 27_ §5.3). "
                  "UE 컨텍스트 수는 완료를 기다리는 UE까지 센 탐지 쪽 확장 지표(ext.UeCtxMax)",
                  field_config={"defaults": {"unit": "none", "min": 0,
                                             "displayName": "${__field.name} · 셀 ${__field.labels.cell}",
                                             "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 10,
                                                        "spanNulls": False,
                                                        "thresholdsStyle": {"mode": "line+area"}},
                                             "thresholds": {"mode": "absolute", "steps": [
                                                 {"color": "transparent", "value": None},
                                                 {"color": "red", "value": round(CELL_LIMIT * 0.9)}]}},
                                "overrides": []},
                  options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                           "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)
    kpm_panels = [bars["id"], lines["id"]]

    # ---- 경보 목록
    b.row("경보 목록 — 행을 누르면 아래 경보 상세가 그 경보로 바뀐다")
    alert_list = f'''
import "date"
import "strings"
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)")}
summary
  |> filter(fn: (r) => r.start >= v.timeRangeStart or r.status == "열림" or r.status == "상태 불명")
  |> map(fn: (r) => ({{
      시작: r.start,
      셀: r.cell,
      단계: r.stage,
      룰: r.rule,
      공격: r.rule,
      종류: r.class,
      심각도: string(v: r.sev),
      "UE 수": r.ues,
      "대표 값": if r.key == "" then "" else r.key + " = " + r.rep,
      상태: r.status,
      "길이(초)": float(v: int(v: if r.event == "raise" or r.event == "update" then now() else r.last) - int(v: r.start)) / 1000000000.0,
      alert_id: r.alert_id}}))
  |> sort(columns: ["시작"], desc: true)
  |> limit(n: 300)
'''
    link = {"title": "이 경보 상세 보기",
            "url": "/d/portran-monitoring/?var-source=${source}&var-cell=${cell}&var-alert_id=${__data.fields.alert_id}&${__url_time_range}"}
    b.add("table", "경보", 0, 17, 11, [target(alert_list)],
          "고른 시간 범위의 경보(범위 전에 열려 아직 열린 것 포함). 한 행 = 경보 하나(alert_id). 심각도 = 그 경보에서 나온 최고 값, "
          "UE 수·대표 값 = 마지막 값. 상태: 열림 / 해제(clear) / 강제 종료(end, 사유) / 상태 불명(마지막 레코드 뒤 1단계 15초, "
          "2~4단계 90초 동안 아무것도 없음 — 27_ §7). 행을 누르면 아래 경보 상세가 바뀐다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True},
                                     "links": [link]},
                        "overrides": [
                            override("시작", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                            override("셀", ("custom.width", 50)), override("단계", ("custom.width", 50)),
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
                   "sortBy": [{"displayName": "시작", "desc": True}]})

    per_rule = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert" and r._field == "severity" and r.event == "raise" and {ENV})
  |> group(columns: ["rule"])
  |> count()
  |> group()
  |> sort(columns: ["_value"], desc: true)
  |> map(fn: (r) => ({{공격: r.rule, "경보 수": r._value}}))
'''
    b.add("bargauge", "룰별 경보 수 (raise)", 17, 7, 11, [target(per_rule)],
          "고른 시간 범위에 어떤 공격·이상 유형이 몇 번 울렸나. 같은 공격에 여러 룰이 함께 울릴 수 있다(27_ §5.1)",
          field_config={"defaults": {"unit": "none", "min": 0, "color": {"mode": "fixed", "fixedColor": "orange"},
                                     "mappings": rule_mappings()}, "overrides": []},
          options={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True, "valueMode": "color",
                   "reduceOptions": {"calcs": [], "fields": "/^경보 수$/", "values": True},
                   "namePlacement": "left", "sizing": "auto"},
          new_line=True)

    # ---- 경보 상세
    b.row("경보 상세 — ${alert_id}")
    sel = f'r._measurement == "alert" and {ENV} and r.alert_id == "${{alert_id}}"'
    summary = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel})
  |> filter(fn: (r) => r._field == "mode" or r._field == "branch" or r._field == "severity" or r._field == "session")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> last(column: "_time")
  |> map(fn: (r) => ({{룰: r.rule, 공격: r.rule, 단계: r.stage, 종류: r.kind, 셀: r.cell,
      "마지막 이벤트": r.event, 심각도: r.severity, 모드: r.mode,
      갈래: if exists r.branch then r.branch else "",
      세션: if exists r.session then r.session else ""}}))
'''
    b.add("table", "판정 요약", 0, 24, 4, [target(summary)],
          "이 경보의 룰·공격·단계·종류(attack / anomaly)·셀과 마지막 상태. 모드 dl_missing = 분석 엔진이 DL을 못 봐 축소 판정(1단계). "
          "갈래 = L3-21·L3-14·AN-02의 판정 갈래(27_ §5.2)",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("공격", ("mappings", rule_mappings()), ("custom.width", 300)),
                                      override("심각도", ("mappings", SEVERITY_MAPPINGS),
                                               ("custom.cellOptions", {"type": "color-background"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}, new_line=True)

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
          "왜 이 경보가 났나. raise에 실린 조건·후보·전제·설정값과, update로 덮어쓴 마지막 관측값(27_ §5.4 룰별 뜻)",
          field_config={"defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("항목", ("custom.width", 260)),
                                      override("값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "md", "footer": {"show": False}})

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
          "함께 본다(27_ §7). 4단계 이상 유형은 여기 후보 가운데 하나다",
          field_config={"defaults": {"custom": {"align": "left"}},
                        "overrides": [override("공격", ("mappings", rule_mappings())),
                                      override("ID", ("custom.width", 90))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}, new_line=True)

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
      불확실: if exists r.uncertain then r.uncertain else "",
      전제: if exists r.conditions then r.conditions else "",
      "피해자 연결 (peers)": if exists r.peers then r.peers else "",
      근거: if exists r.evidence and r.evidence then "있음" else "없음",
      "UE 관측값": if exists r.values_json then r.values_json else "",
      이벤트: r.event}}))
'''
    b.add("table", "걸린 UE (2~4단계)", 0, 24, 8, [target(ues)],
          "어느 단말 연결이 걸렸나. raise·update에 실린 UE를 모두 모은 것(update에는 새로 걸린 UE만 옴). UE는 (셀, du_ue_id, uid)로 가리키고 "
          "세션 안에서만 유일, 같은 단말의 여러 연결은 S-TMSI로 묶는다. 불확실: mid_join(연결 중간부터 봄)·loss(유실)·late. "
          "Blind DoS(L3-20)의 피해자 연결은 peers에 ID만 온다(근거 메시지는 오지 않음)",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("걸린 시각", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                                      override("UE 관측값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}, new_line=True)

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
    ev_bars = b.add("timeseries", "근거 KPM2 — 100 ms 칸 (1단계 경보)", 0, 24, 8, [target(ev_kpm2)],
                    "1단계 경보가 왜 났나. 경보 직전 2.1초(pre 21칸)·경보 중(active)·해제 뒤 1초(post)의 셀 카운터를 100 ms 그대로 "
                    "보여 준다(27_ §6.2). 무응답은 시도보다 약 1초 늦게 찍힌다. 회색 영역 = 데이터 없음(gap). 시간 범위를 경보 구간에 맞춰 본다",
                    field_config={"defaults": {"unit": "none", "min": 0, "displayName": "${__field.name}",
                                               "custom": {"drawStyle": "bars", "fillOpacity": 70, "barAlignment": -1,
                                                          "lineWidth": 1, "spanNulls": False}},
                                  "overrides": [
                                      override("연결 시도", ("color", {"mode": "fixed", "fixedColor": "blue"})),
                                      override("연결 성공", ("color", {"mode": "fixed", "fixedColor": "green"})),
                                      override("무응답 (NoReply)", ("color", {"mode": "fixed", "fixedColor": "red"}))]},
                    options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                             "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    timeline = f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "evidence" and {ENV} and r.alert_id == "${{alert_id}}" and r.raw_type == "ue_evt")
  |> filter(fn: (r) => r._field == "msg" or r._field == "dir" or r._field == "uid")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({{_time: r._time, _value: (if r.dir == "UL" then "↑ " else "↓ ") + r.msg, ue: "UE " + string(v: r.uid)}}))
  |> group(columns: ["ue"])
  |> sort(columns: ["_time"])
'''
    tl = b.add("state-timeline", "근거 KPM1 — UE별 메시지 흐름 (2~4단계 경보)", 0, 24, 7, [target(timeline)],
               "걸린 단말이 어떤 메시지를 어떤 순서로 주고받았나(27_ §6.3). UE마다 한 줄, ↑ 단말 → 망(UL) / ↓ 망 → 단말(DL). "
               "자세한 값은 아래 표",
               field_config={"defaults": {"displayName": "${__field.labels.ue}", "color": {"mode": "palette-classic"},
                                          "custom": {"fillOpacity": 80, "lineWidth": 1}}, "overrides": []},
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
      방향: if r.dir == "UL" then "↑ UL" else "↓ DL", 프로토콜: r.proto, 메시지: r.msg, 단계: r.phase, 원본: r.raw_json}}))
  |> limit(n: 1000)
'''
    b.add("table", "근거 KPM1 — 메시지 (2~4단계 경보)", 0, 24, 10, [target(messages)],
          "근거 메시지 하나 = 한 행. pre = 그 UE가 경보에 처음 실릴 때의 최근 메시지(최대 16줄), active = 경보 중 새 메시지. "
          "원본은 분석 엔진이 보낸 ue_evt 그대로(f에 메시지에서 꺼낸 값, 27_ §4.2)",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}},
                        "overrides": [override("시각", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                                      override("방향", ("custom.width", 70)), override("프로토콜", ("custom.width", 70)),
                                      override("단계", ("custom.width", 65)),
                                      override("원본", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}, new_line=True)

    # ---- 변수·주석
    variables = [
        source_variable(),
        query_variable("cell", "셀", f'''
import "influxdata/influxdb/schema"
schema.tagValues(bucket: v.defaultBucket, tag: "cell", start: -30d,
  predicate: (r) => (r._measurement == "kpm2" or r._measurement == "alert") and {ENV})
''', multi=True, include_all=True, description="상시 KPM2 그래프에 보일 셀"),
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

    # 열린 경보만 지금까지, 상태 불명은 마지막 레코드(경보·근거)까지, 닫힌 경보는 clear·end까지 칠한다
    alert_regions = f'''
import "date"
import "strings"
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)")}
summary
  |> filter(fn: (r) => contains(value: r.cell, set: ${{cell:json}}))
  |> map(fn: (r) => ({{_time: r.start,
      timeEnd: if r.status == "열림" then now() else if r.status == "상태 불명" then r.active else r.last,
      text: "경보 " + r.rule + " — " + r.status + " (단계 " + r.stage + ", " + r.class + ", 셀 " + r.cell + ")", tags: r.rule}}))
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
    sessions = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => ((r._measurement == "hello" and r._field == "seq") or (r._measurement == "f1_evt" and r._field == "msg")) and {ENV})
  |> map(fn: (r) => ({{_time: r._time,
      text: if r._measurement == "hello" then "분석 엔진 접속 — 새 세션 " + r.session else "DU·CU 재시작 (" + string(v: r._value) + ")",
      tags: r._measurement}}))
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
        annotation("세션 시작 · 재시작", sessions, "rgba(31, 120, 193, 1)", kpm_panels),
        annotation("근거 데이터 없음 (gap)", ev_gaps, "rgba(128, 128, 128, 0.25)", [ev_bars["id"]], region=True),
    ]
    return dashboard("portran-monitoring", "PortRAN 관제",
                     "탐지 엔진 레코드(27_) 실시간 관제 — 상시 KPM2, 경보 목록, 경보 상세(근거 KPM2·KPM1). docs/dashboard-design.md 2절",
                     b, variables, annotations, refresh="5s", time_from="now-1h")


# --------------------------------------------------------------------------- 쓰기

BUILDERS = {"monitoring.json": monitoring}


def render() -> dict[str, str]:
    return {name: json.dumps(build(), ensure_ascii=False, indent=2) + "\n" for name, build in BUILDERS.items()}


def main(argv: list[str]) -> int:
    outputs = render()
    if "--check" in argv:
        stale = [n for n, text in outputs.items() if not (OUT_DIR / n).exists()
                 or (OUT_DIR / n).read_text(encoding="utf-8") != text]
        if stale:
            print(f"대시보드 JSON이 grafana/build.py와 다릅니다: {', '.join(stale)} — python grafana/build.py로 다시 만드세요")
            return 1
        return 0
    for name, text in outputs.items():
        (OUT_DIR / name).write_text(text, encoding="utf-8")
        print(f"썼음: {OUT_DIR / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
