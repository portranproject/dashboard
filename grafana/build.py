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
# 판정 근거 값·대표 값에서 키 대신 보일 이름: 룰 → 항목 → 키 → 이름 (reference/detection/35_ 엑셀, 11/25)
EVIDENCE_KEY_NAMES = json.loads((ROOT / "evidence-key-names.json").read_text(encoding="utf-8"))["rules"]
DS ={"type": "influxdb", "uid": "portran-influxdb"}

# 데이터 출처 선택 (docs/dashboard-design.md 1절) = X-Env 값. 탐지 쪽이 11/20부터 AWS는 aws, On-Premise(우리 실물 장비)는
# on-premise로 보낸다(D213). 11/13~11/20 AWS 실측(p4)을 고르던 'AWS (이전 p4)'는 11/27에 없앴다(사용자 요청, D223 — 데이터는
# InfluxDB에 그대로 있다)
SOURCES = [("AWS", "aws"), ("On-Premise", "on-premise"), ("재생", "replay"), ("샘플", "sample")]

# 상태 불명: 열린 경보에 마지막 레코드 뒤 이 시간 동안 아무것도 없으면 (27_ §7)
STALE_NS = {"1": 15_000_000_000, "other": 90_000_000_000}
CELL_LIMIT = 96  # 셀 UE 컨텍스트 한도 (27_ §5.3, ext.UeCtxMax ≥ 90%면 high)
# 노드 CPU % 그래프 축의 소프트 최대(Grafana custom.axisSoftMax). 축이 적어도 0~이 값이고 값이 넘으면 늘어난다.
# 100 고정이면 평소 2~5%가 바닥에 붙어 안 보이고, 완전 자동이면 작은 흔들림이 꼭대기까지 튀어 과장된다(11/25)
CPU_AXIS_SOFT_MAX = 10
# 근거 KPM1 타임라인에서 UE의 마지막 메시지를 이만큼만 그린다(그 뒤는 빈칸)
TIMELINE_END_S = 1

# 상시 KPM2·overhead 칸 길이. 칸은 epoch 기준 [k·3000, (k+1)·3000) ms다(27_ §4.1, overhead는 AWS 7일 실측 모두 3000 ms)
SLOT_MS = 3000
SLOT_NS = SLOT_MS * 1_000_000
# 분석 엔진 보고 주기(hello.period_ms) 기본값 — 3초 칸이 가득 차면 n = 3000 ÷ 주기(100 ms면 30). 주기는 세션마다 다르다
# (AWS p4 11/13~11/15 세션 7개는 1,000 ms라 가득 차도 n 3 — 100 ms로 박아 두어 '칸 일부 없음'을 잘못 칠했음, D214)
KPM2_PERIOD_MS = 100
KPM2_FULL_N = SLOT_MS // KPM2_PERIOD_MS
# 시간 그래프는 3초 원본을 그대로 가져오지 않고, Grafana가 화면 폭·범위로 정한 간격(v.windowPeriod)을 3초 배수로 올린
# 구간(win)으로 묶는다(D202). 원본을 다 가져오면 7일에 셀·지표 하나가 20만 점이라 Grafana 점 수 상한(maxDataPoints × 10)·
# 시간 제한(30초)에 걸렸다. 3초 배수라 구간마다 칸 수가 같고, 구간 경계가 칸 경계와 맞는다. 1시간 화면은 3초 그대로다
WINDOW = f"win = duration(v: (int(v: v.windowPeriod) + {SLOT_NS - 1}) / {SLOT_NS} * {SLOT_NS})"
# 셀 거르기는 정규식으로 — contains()는 InfluxDB가 저장소에서 거르지 못해(pushdown 안 됨) 7일 쿼리가 30초를 넘었다(D202)
CELL_REGEX = "r.cell =~ /^${cell:regex}$/"
# 0~1 비율이라 %로 보이는 대표 값 키(27_ §5.3 — L3-01-V의 ratio뿐). 저장값은 반올림 없는 실수 그대로다
PERCENT_REP_KEYS = ("ratio",)
# 판정 근거 값 표의 행(alert 필드) → 이름 대응표의 항목. cond·conditions는 문자열 배열, 나머지는 객체다
EVIDENCE_FIELDS = {"cond_json": "cond", "conditions_json": "conditions", "values_json": "values",
                   "params_json": "params", "refs_json": "refs"}


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

# 경보 종류: 공격 경보 / 4단계 이상 유형(AN-) / 판정 보류 경보(2·3단계 룰인데 kind anomaly) — 27_ §5.5.
# rule-names.json의 shown_as_anomaly(L3-24·L3-14, 탐지 쪽 요청 11/27)는 kind attack이어도 이상 유형으로 보인다 — 화면만 바꾸고
# 레코드는 그대로. 그 룰의 판정 보류 경보(kind anomaly)는 그대로 판정 보류다. Slack 알림도 이 종류로 고른다(NOTIFY_CLASSES)
SHOWN_AS_ANOMALY = " or ".join(f'r.rule == "{rule}"' for rule in RULE_NAMES["shown_as_anomaly"]) or "false"
CLASS_EXPR = (f'if r.kind == "attack" and not ({SHOWN_AS_ANOMALY}) then "공격" '
              'else if r.kind == "attack" or strings.hasPrefix(v: r.rule, prefix: "AN-") then "이상 유형" else "판정 보류"')

ENV = 'r.env == "${source}"'


ALERT_SUMMARY_FIELDS = ("severity", "ues_total", "rep_value", "rep_key", "reason")


def alert_summary(alert_start: str, evidence_start: str | None, stop: str = "v.timeRangeStop",
                  fields: tuple[str, ...] = ALERT_SUMMARY_FIELDS) -> str:
    """경보 하나 = 한 행으로 합친 Flux(끝은 ungroup). 열: alert_id, rule, stage, kind, cell, start(raise), last(마지막 경보 레코드),
    active(경보·근거 중 마지막), event(마지막 이벤트), sev(0·1·2 최대), ues·rep·key·reason(마지막 값, 문자열), status(열림·해제·
    강제 종료 (사유)·상태 불명), class(공격·이상 유형·판정 보류).
    pivot은 경보마다 필드 구성이 달라 표 모양이 갈리므로 쓰지 않고, 값을 문자열 한 열로 모아 reduce로 합친다.
    상태 불명 판단에 쓸 마지막 근거 시각도 같은 모양으로 붙여(union) 함께 합친다(join.left는 reduce 결과에서 실패함).
    start가 지금 기준(-5m 등)이면 stop도 now()로 준다 — stop이 화면 시간 범위 끝이면, 지난 범위를 골랐을 때
    start > stop이 되어 "cannot query an empty range"로 패널이 깨진다.
    evidence_start가 None이면 근거를 읽지 않는다(성능 대시보드 — 끝난 실험을 넓은 범위로 보므로 근거를 다 읽으면 느리고,
    clear·end가 안 온 경보는 근거와 상관없이 '끝이 안 옴'으로 센다).
    fields: 읽을 경보 필드. 경보 tag(alert_id·event 등)마다 series라 읽는 시간이 필드 수에 비례한다 — 대표 값·UE 수가
    필요 없는 곳은 severity·reason만 읽는다(7일 2.9초가 대부분 이 읽기였음, AWS 프로파일 11/18). severity는 모든 이벤트에
    있어 경보 수·시작·끝 계산이 그대로다."""
    conds = [f'r._field == "{f}"' for f in fields]
    # 기본 필드는 예전 줄바꿈 그대로(알림 규칙 provisioning이 바뀌지 않게)
    field_cond = (" or ".join(conds[:3]) + "\n      or " + " or ".join(conds[3:])) if len(conds) > 3 else " or ".join(conds)
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
  |> filter(fn: (r) => {field_cond})
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


def window_by(fn: str, columns: list[str], between: str = "", fill: bool = False) -> str:
    """구간(win)으로 묶는 Flux 조각. 앞의 aggregateWindow는 range·filter 바로 뒤라 InfluxDB가 저장소에서 series(세션·agg_ms·
    노드 등)마다 계산하고, group 뒤 같은 구간을 한 번 더 묶어 series를 합친다 — 세션이 바뀌는 구간에서 같은 시각의 두 행을
    pivot이 하나만 남기지 않게. between = 두 단계 사이의 map(예: 노드 이름 합치기).
    fill이면 빈 구간을 null 행으로 남겨 선을 끊는다(insertNulls는 고정 ms라 구간 길이를 모른다). 선택 함수(max)에
    createEmpty: true를 주면 7일에 1~2초 걸려(AWS 실측), 빈 구간 채우기는 mean으로 한 번 더 묶어서 한다(값은 그대로)."""
    cols = ", ".join(f'"{c}"' for c in columns)
    parts = [f'  |> aggregateWindow(every: win, fn: {fn}, createEmpty: false, timeSrc: "_start")']
    if between:
        parts.append(between)
    parts += [f"  |> group(columns: [{cols}])",
              f'  |> aggregateWindow(every: win, fn: {fn}, createEmpty: false, timeSrc: "_start")']
    if fill:
        parts.append('  |> aggregateWindow(every: win, fn: mean, createEmpty: true, timeSrc: "_start")')
    return "\n".join(parts)


def kpm2_source(fields: list[str], extra: str = "") -> str:
    """고른 시간 범위·출처·셀의 상시 KPM2 필드. 첫 filter는 저장소에서 처리되는 모양만(contains 금지, D202).
    extra(' and …')는 필드 조건 전체에 걸린다."""
    cond = " or ".join(f'r._field == "{f}"' for f in fields)
    if extra and len(fields) > 1:
        cond = f"({cond})"
    return f'''from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "kpm2" and {ENV} and {CELL_REGEX})
  |> filter(fn: (r) => {cond}{extra})'''


def alert_hover_query() -> str:
    """경보 구간을 칠하고, 그 안 어디에 마우스를 대도 툴팁에 경보가 보이게 하는 계열(refId B, D204·D209).
    - 툴팁: Grafana 주석 글은 아래쪽 작은 마커에서만 뜨고 영역에는 그런 기능이 없다(12.4.13 AnnotationMarker2). 그래서 경보마다
      구간(win)을 빈틈없이 채운 계열을 둔다. 툴팁은 커서 칸 값이 null이면 15 px 안의 가장 가까운 값을 쓰므로 구간 끝 바로
      밖에서도 보일 수 있다.
    - 칠하기: 처음에는 '경보 구간' 주석으로 칠했는데, 새로고침(5초)마다 깜빡였다 — 쿼리가 200 ms 안에 안 끝나면 Grafana가 '로딩 중,
      빈 결과'를 먼저 내보내고(runRequest.ts timer(200)) 주석 레이어는 그것을 그대로 넘겨 그 순간 주석이 지워진다. 패널 데이터는
      로딩 중에도 이전 값을 유지하므로, 이 계열로 칠한다(값 1 = 축 끝까지 채움, ALERT_HOVER_OVERRIDE).
    - 이름 = 종류 — 공격 이름 · 셀 · 상태 · 심각도. 구간 끝 = 열림이면 지금, 상태 불명이면 마지막 레코드, 그 밖은 clear·end.
    경보 하나를 시작·끝 두 행으로 펴고(experimental.unpivot) interpolate.linear로 그 사이 구간 경계(win 배수 — KPM 구간과
    같은 시각)를 채운다. 작업량이 경보 길이에 비례한다 — aggregateWindow(createEmpty)로 경보마다 화면 범위 전체를 채우면
    7일(2016칸 × 경보 73개)에서 패널 요청이 5~11초 걸렸다. 요약 결과를 변수로 받아 두 갈래로 나눠 쓰면(union) 요약 계산을
    두 번 해서 쓰지 않는다."""
    return f'''
import "date"
import "dict"
import "experimental"
import "interpolate"
import "strings"
{WINDOW}
names = {rule_name_dict()}
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)", fields=("severity", "reason"))}
summary
  |> filter(fn: (r) => {CELL_REGEX})
  |> map(fn: (r) => {{
      end = if r.status == "열림" then now() else if r.status == "상태 불명" then r.active else r.last
      s = if r.start > v.timeRangeStart then r.start else v.timeRangeStart
      sev = if r.sev == 2 then "high" else if r.sev == 1 then "medium" else "심각도 없음"
      return {{alert_id: r.alert_id, v: 1.0, _time: s, s: s,
        e: if end < v.timeRangeStop then end else v.timeRangeStop,
        alert: r.class + " — " + dict.get(dict: names, key: r.rule, default: r.rule) + " · 셀 " + r.cell + " · " + r.status
          + " · " + sev}}
    }})
  |> filter(fn: (r) => r.e > r.s)
  |> group(columns: ["alert_id", "alert", "v"])
  |> experimental.unpivot()
  |> map(fn: (r) => ({{_time: r._value, _value: r.v, alert_id: r.alert_id, alert: r.alert}}))
  |> group(columns: ["alert_id", "alert"])
  |> sort(columns: ["_time"])
  |> interpolate.linear(every: win)
'''


# 경보 계열(refId B): 경보 구간을 연한 주황으로 축 끝까지 칠하고(값 1, 자기 숨은 축 0~1 — 다른 계열의 y축 범위에 영향 없음),
# 범례에는 없고 툴팁에는 나온다. 색·투명도는 예전 '경보 구간' 주석(rgba(255, 152, 48, 0.12))과 같게
ALERT_HOVER_OVERRIDE = {"matcher": {"id": "byFrameRefID", "options": "B"}, "properties": [
    {"id": "displayName", "value": "${__field.labels.alert}"},
    {"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}},
    {"id": "custom.drawStyle", "value": "line"},
    {"id": "custom.lineInterpolation", "value": "stepAfter"},
    {"id": "custom.lineWidth", "value": 0},
    {"id": "custom.fillOpacity", "value": 12},
    {"id": "custom.gradientMode", "value": "none"},
    {"id": "custom.showPoints", "value": "never"},
    {"id": "custom.spanNulls", "value": False},
    {"id": "custom.stacking", "value": {"mode": "none"}},
    {"id": "custom.axisPlacement", "value": "hidden"},
    {"id": "custom.thresholdsStyle", "value": {"mode": "off"}},
    {"id": "min", "value": 0}, {"id": "max", "value": 1}, {"id": "decimals", "value": 0},
    {"id": "color", "value": {"mode": "fixed", "fixedColor": "orange"}},
    {"id": "mappings", "value": [{"type": "value", "options": {"1": {"text": "경보 구간", "index": 0}}}]}]}
ALERT_HOVER_NOTE = " 주황 영역 = 경보 구간 — 영역 어디에 마우스를 대도 툴팁에 경보(종류 — 공격 이름 · 셀 · 상태 · 심각도)가 보인다"


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
            "description": "AWS = AWS 테스트베드(X-Env aws, 11/20부터) · On-Premise = 우리 실물 장비 테스트베드(on-premise) · "
                           "재생 = replay로 다시 보낸 데이터 · 샘플 = 탐지 쪽 시험 샘플"}


def query_variable(name: str, label: str, query: str, multi: bool = False, include_all: bool = False,
                   description: str = "", refresh: int = 2) -> dict:
    """refresh 2 = 시간 범위가 바뀔 때(자동 새로고침 포함)마다 다시 읽음, 1 = 대시보드를 열 때만(D103·D219)."""
    v = {"name": name, "label": label, "type": "query", "datasource": DS, "query": query.strip("\n"),
         "definition": query.strip("\n"), "refresh": refresh, "sort": 0, "multi": multi, "includeAll": include_all,
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
    # 구간 합(사용자 결정 11/18) — 1시간 화면은 3초 칸 그대로, 긴 범위는 3초 배수 구간의 합
    kpm_bars = f'''
{WINDOW}
{kpm2_source(["cc.RRC.ConnEstabAtt.total", "cc.RRC.ConnEstabSucc.total", "cc.RRC.ConnEstabFailCause.NoReply"])}
{window_by("sum", ["cell", "_field"])}
  |> map(fn: (r) => ({{_time: r._time, _value: r._value, cell: r.cell,
      _field: if r._field == "cc.RRC.ConnEstabAtt.total" then "연결 시도"
              else if r._field == "cc.RRC.ConnEstabSucc.total" then "연결 성공" else "무응답 (NoReply)"}}))
  |> group(columns: ["cell"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    bars = b.add("timeseries", "RRC 연결 시도 · 성공 · 무응답", 0, 24, 9, [target(kpm_bars), target(alert_hover_query(), "B")],
                 "상시 KPM2(TeleRAN Table II) — 셀마다 3초 칸, 긴 시간 범위에서는 3초 배수 구간의 합(막대 하나 = 구간 하나). "
                 "위쪽 셀 선택으로 거른다. "
                 "셀에 무슨 일이 일어나고 있나. UE 컨텍스트 고갈 공격(1단계)은 시도와 무응답이 함께 솟고 성공은 그대로다. "
                 "회색 영역 = 데이터 없음(gap)·칸 일부 없음, 파란 세로선 = 분석 엔진 세션 시작(hello), 보라 세로선 = DU·CU 재시작(f1_evt)."
                 + ALERT_HOVER_NOTE,
                 field_config={"defaults": {"unit": "none", "min": 0,
                                            "displayName": "${__field.name} · 셀 ${__field.labels.cell}",
                                            # 막대가 자기 구간 [시작, 시작 + win]을 덮게(시각 = 구간 시작) — 경보 구간 주석과 맞음
                                            "custom": {"drawStyle": "bars", "fillOpacity": 70, "barAlignment": 1,
                                                       "lineWidth": 1, "spanNulls": False, "stacking": {"mode": "none"}}},
                               "overrides": [
                                   override("연결 시도.*", ("color", {"mode": "fixed", "fixedColor": "blue"}), regex=True),
                                   override("연결 성공.*", ("color", {"mode": "fixed", "fixedColor": "green"}), regex=True),
                                   override("무응답.*", ("color", {"mode": "fixed", "fixedColor": "red"}), regex=True),
                                   ALERT_HOVER_OVERRIDE]},
                 options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)

    # 구간 최대(셀 한도와 비교), 평균 선만 구간 평균(사용자 결정 11/18). 두 갈래는 from을 따로 둔다 — 한 from을 변수로
    # 나눠 쓰면 저장소 계산이 안 돼 7일에 15초 걸렸다(AWS 실측)
    kpm_lines = f'''
{WINDOW}
peak = {kpm2_source(["ext.UeCtxMax", "si.RRC.ConnMax"])}
{window_by("max", ["cell", "_field"], fill=True)}
avg = {kpm2_source(["si.RRC.ConnMean"])}
{window_by("mean", ["cell", "_field"], fill=True)}
union(tables: [peak, avg])
  |> map(fn: (r) => ({{_time: r._time, _value: r._value, cell: r.cell,
      _field: if r._field == "ext.UeCtxMax" then "UE 컨텍스트 수 (최대)"
              else if r._field == "si.RRC.ConnMax" then "RRC 연결 UE (최대)" else "RRC 연결 UE (평균)"}}))
  |> group(columns: ["cell"])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    lines = b.add("timeseries", "UE 컨텍스트 · 연결 UE 수", 0, 24, 8, [target(kpm_lines), target(alert_hover_query(), "B")],
                  f"셀 자원이 고갈되고 있나. 빨간 선 = 셀 한도 {CELL_LIMIT}의 90%(1·2단계 경보가 high가 되는 기준). "
                  "UE 컨텍스트 수는 완료를 기다리는 UE까지 센 탐지 쪽 확장 지표(ext.UeCtxMax). 셀마다 3초 칸, 긴 시간 범위에서는 "
                  "3초 배수 구간의 최대(평균 선은 구간 평균). 데이터가 없는 구간에서 선이 끊긴다." + ALERT_HOVER_NOTE,
                  field_config={"defaults": {"unit": "none", "min": 0,
                                             "displayName": "${__field.name} · 셀 ${__field.labels.cell}",
                                             "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 10,
                                                        "spanNulls": False, "thresholdsStyle": {"mode": "line+area"}},
                                             "thresholds": {"mode": "absolute", "steps": [
                                                 {"color": "transparent", "value": None},
                                                 {"color": "red", "value": round(CELL_LIMIT * 0.9)}]}},
                                "overrides": [ALERT_HOVER_OVERRIDE]},
                  options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                           "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)
    kpm_panels = [bars["id"], lines["id"]]

    # ---- 경보 목록
    b.row("경보 목록")
    # 0~1 비율 대표 값(ratio)은 %로(사용자 요청 11/18): 0.5714 → 57%. ×100 뒤 반올림해야 실수 오차(56.99999…)가 없다
    percent_keys = " or ".join(f'r.key == "{k}"' for k in PERCENT_REP_KEYS)
    # 대표 값 키도 판정 근거 값과 같은 화면 이름으로(11/25, 35_ 엑셀) — % 판단은 원래 키로 한다
    rep_name = 'dict.get(dict: rep_names, key: r.rule + "|" + r.key, default: r.key)'
    alert_list = f'''
import "date"
import "dict"
import "math"
import "strings"
rep_names = {rep_name_dict()}
{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", "date.sub(d: 1h, from: v.timeRangeStart)")}
// 정렬은 map 앞에서 한다 — map으로 만든 열("시작")로 정렬하면 InfluxDB 2.7이 줄을 떨어뜨린다(해제된 경보가 목록에서 빠졌음, M11)
summary
  |> filter(fn: (r) => (r.start >= v.timeRangeStart or r.status == "열림" or r.status == "상태 불명") and {CELL_REGEX})
  |> sort(columns: ["start"], desc: true)
  |> limit(n: 300)
  |> map(fn: (r) => ({{
      시작: r.start,
      셀: r.cell,
      공격: r.rule,
      종류: r.class,
      심각도: string(v: r.sev),
      "UE 수": r.ues,
      "대표 값": if r.key == "" then ""
                else if ({percent_keys}) and r.rep != "" then {rep_name} + " = " + string(v: math.round(x: float(v: r.rep) * 100.0)) + "%"
                else {rep_name} + " = " + r.rep,
      상태: r.status,
      "길이(초)": float(v: int(v: if r.event == "raise" or r.event == "update" then now() else r.last) - int(v: r.start)) / 1000000000.0,
      alert_id: r.alert_id}}))
'''
    # 셀은 :queryparam으로(var-cell=1&var-cell=2, 전체면 var-cell=$__all) — ${cell}이면 여러 셀이 '{1,2}' 한 값이 되어
    # 셀 변수가 기본값으로 돌아갔다(11/25)
    link = {"title": "이 경보 상세 보기",
            "url": "/d/portran-monitoring/?var-source=${source}&${cell:queryparam}&var-alert_id=${__data.fields.alert_id}&${__url_time_range}"}
    # 룰별 경보 수 막대는 없애고 표를 한 줄 가득(11/16 — 맨 위 탐지 결과의 공격별 경보 수와 겹침)
    b.add("table", "경보", 0, 24, 11, [target(alert_list)],
          "고른 시간 범위의 경보(범위 전에 열려 아직 열린 것 포함), 위쪽 셀 변수로 고른 셀만. 한 행 = 경보 하나(alert_id). 심각도 = 그 경보에서 나온 최고 값, "
          "UE 수·대표 값 = 마지막 값(ratio는 % — 소수 셋째 자리에서 반올림, 키는 판정 근거 값과 같은 이름). 상태: 열림 / 해제(clear) / 강제 종료(end, 사유) / 상태 불명(마지막 레코드 뒤 1단계 15초, "
          "2~4단계 90초 동안 아무것도 없음). 행을 누르면 아래 경보 상세가 바뀐다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True},
                                     "links": [link]},
                        "overrides": [
                            override("시작", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                            override("셀", ("custom.width", 50)),
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
                  ["시작", "셀", "공격", "종류", "심각도", "UE 수", "대표 값", "상태", "길이(초)", "alert_id"])}}}],
          new_line=True)

    # ---- 경보 상세
    b.row("경보 상세 — ${alert_id}")
    sel = f'r._measurement == "alert" and {ENV} and r.alert_id == "${{alert_id}}"'
    summary = f'''
import "date"
import "strings"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel})
  |> filter(fn: (r) => r._field == "severity" or r._field == "session")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> last(column: "_time")
  |> map(fn: (r) => ({{룰: r.rule, 공격: r.rule, 종류: {CLASS_EXPR}, 셀: r.cell,
      "마지막 이벤트": r.event, 심각도: r.severity,
      세션: if exists r.session then r.session else ""}}))
'''
    b.add("table", "판정 요약", 0, 24, 4, [target(summary)],
          "이 경보의 룰·공격·종류(공격 / 이상 유형 / 판정 보류 — 경보 목록과 같은 계산, L3-24·L3-14는 kind attack이어도 이상 유형)·셀과 마지막 상태. "
          "갈래(branch)·모드(mode) 열은 없앴다(11/16, 11/18) — 값은 InfluxDB·원본 녹화에 남아 있다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("공격", ("mappings", rule_mappings()), ("custom.width", 300)),
                                      override("종류", ("mappings", KIND_MAPPINGS),
                                               ("custom.cellOptions", {"type": "color-text"})),
                                      override("심각도", ("mappings", SEVERITY_MAPPINGS),
                                               ("custom.cellOptions", {"type": "color-background"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["룰", "공격", "종류", "셀", "심각도", "마지막 이벤트", "세션"]),
          new_line=True)

    labels = [("cond_json", "성립 조건 (cond)"), ("candidates_json", "같은 모양의 다른 공격 후보 (candidates)"),
              ("conditions_json", "공격자 행동 전제 (conditions)"), ("values_json", "관측값 (values, 마지막 값)"),
              ("params_json", "설정값 (params)"), ("refs_json", "판정 창 seq 범위 (refs)")]
    detail = f'''
import "date"
import "dict"
import "strings"
{evidence_rename_fn()}
{candidate_hide_fn()}
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
      항목: dict.get(dict: labels, key: r._field, default: r._field),
      값: rename(rule: r.rule, field: r._field,
          s: if r._field == "candidates_json" then hide_candidates(rule: r.rule, s: string(v: r._value)) else string(v: r._value))}}))
  |> sort(columns: ["n"])
  |> drop(columns: ["n"])
'''
    b.add("table", "판정 근거 값", 0, 15, 9, [target(detail)],
          "왜 이 경보가 났나. raise에 실린 조건·후보·전제·설정값과, update로 덮어쓴 마지막 관측값. "
          "키는 줄임말 없는 이름으로 보인다(grafana/evidence-key-names.json — 탐지 쪽 35_ 분석표, 원래 키는 InfluxDB·녹화에 그대로). "
          "이름이 정해지지 않은 키는 원래 키. 후보(candidates)에서 상향 IMSI 노출(AN-02)의 상향 IMSI 추출(L3-25-OV)은 뺀다(11/27)",
          field_config={"defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("항목", ("custom.width", 260)),
                                      override("값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "md", "footer": {"show": False}},
          transformations=column_order(["항목", "값"]))

    candidates = f'''
import "array"
import "date"
import "strings"
{candidate_hide_fn()}
latest = from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => {sel} and r._field == "candidates_json")
  |> group()
  |> max(column: "_time")
c = latest |> findColumn(fn: (key) => true, column: "_value")
rl = latest |> findColumn(fn: (key) => true, column: "rule")
text = if length(arr: c) > 0
  then strings.replaceAll(v: strings.trim(v: hide_candidates(rule: rl[0], s: c[0]), cutset: "[]"), t: "\\"", u: "") else ""
ids = array.filter(arr: strings.split(v: text, t: ","), fn: (x) => x != "")
array.from(rows: if length(arr: ids) > 0 then array.map(arr: ids, fn: (x) => ({{ID: x, 공격: x}})) else [{{ID: "-", 공격: "후보 없음"}}])
'''
    b.add("table", "후보 공격", 15, 9, 9, [target(candidates)],
          "이 경보와 같은 모양을 만드는 다른 공격(candidates). 탐지 엔진은 경보끼리 묶지 않으므로, 같은 셀·같은 시간의 다른 경보와 "
          "함께 본다. 4단계 이상 유형은 여기 후보 가운데 하나다. 상향 IMSI 노출(AN-02)의 후보 상향 IMSI 추출(L3-25-OV)은 이름이 겹쳐 "
          "보이지 않는다(탐지 쪽 요청 11/27 — 레코드에는 그대로)",
          field_config={"defaults": {"custom": {"align": "left"}},
                        "overrides": [override("공격", ("mappings", rule_mappings())),
                                      override("ID", ("custom.width", 90))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["ID", "공격"]), new_line=True)

    # UE는 화면에서 셀-uid로 보인다(사용자 요청 11/18). InfluxDB의 ue 태그·peers는 셀-du_ue_id-uid 그대로다(덮어쓰기 방지용 키).
    # peers는 "셀-du_ue_id-uid; …" 문자열이라 칸마다 가운데를 뺀다
    ues = f'''
import "array"
import "date"
import "strings"
short = (s) => strings.joinStr(arr: array.map(arr: strings.split(v: s, t: "; "), fn: (x) => {{
    p = strings.split(v: x, t: "-")
    return if length(arr: p) == 3 then p[0] + "-" + p[2] else x
  }}), v: "; ")
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 6h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert_ue" and {ENV} and r.alert_id == "${{alert_id}}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"])
  |> map(fn: (r) => ({{"걸린 시각": r._time, "UE (cell-uid)": string(v: r.cell) + "-" + string(v: r.uid),
      "S-TMSI": if exists r.s_tmsi then r.s_tmsi else "",
      "C-RNTI": if exists r.crnti then string(v: r.crnti) else "",
      조건: if exists r.cond then r.cond else "",
      "피해자 연결": if exists r.peers then short(s: r.peers) else "",
      "UE 관측값": if exists r.values_json then r.values_json else "",
      이벤트: r.event}}))
'''
    b.add("table", "걸린 UE", 0, 24, 8, [target(ues)],
          "어느 단말 연결이 걸렸나. raise·update에 실린 UE를 모두 모은 것(update에는 새로 걸린 UE만 옴). UE는 셀-uid로 보인다"
          "(uid는 세션 안에서 유일, du_ue_id는 InfluxDB·원본 녹화에 남아 있다). 같은 단말의 여러 연결은 S-TMSI로 묶는다. "
          "피해자 연결 = Blind DoS(L3-20)에서만 — 같은 S-TMSI를 원래 쓰던 단말의 연결(셀-uid, 근거 메시지는 오지 않음). "
          "관측 오류(uncertain)·근거(evidence) 열은 없앴다(11/20) — 값은 InfluxDB·원본 녹화에 남아 있다",
          field_config={"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("걸린 시각", ("unit", "dateTimeAsIso"), ("custom.width", 165)),
                                      override("UE 관측값", ("custom.cellOptions", {"type": "json-view"}))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(["걸린 시각", "UE (cell-uid)", "S-TMSI", "C-RNTI", "조건", "피해자 연결",
                                        "UE 관측값", "이벤트"]),
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
  |> filter(fn: (r) => r._field == "msg" or r._field == "dir" or r._field == "uid" or r._field == "du_ue_id")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> map(fn: (r) => ({{_time: r._time, _value: (if r.dir == "UL" then "↑ " else "↓ ") + r.msg,
      ue: r.cell + "-" + string(v: r.uid), key: r.cell + "-" + string(v: r.du_ue_id) + "-" + string(v: r.uid)}}))
  |> group(columns: ["ue", "key"])
  |> sort(columns: ["_time"])
ends = msgs
  |> last()
  |> map(fn: (r) => ({{_time: date.add(d: {TIMELINE_END_S}s, to: r._time), _value: "", ue: r.ue, key: r.key}}))
union(tables: [msgs, ends])
  |> group(columns: ["ue", "key"])
  |> sort(columns: ["_time"])
'''
    tl = b.add("state-timeline", "UE_EVENT — UE별 메시지 흐름", 0, 24, 7, [target(timeline)],
               "경보 근거로 온 UE 메시지(ue_evt, KPM1). 걸린 단말이 어떤 메시지를 어떤 순서로 주고받았나. UE(셀-uid)마다 한 줄, "
               "↑ 단말 → 망(UL) / ↓ 망 → 단말(DL). "
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
  |> map(fn: (r) => ({{시각: r._time, "UE (cell-uid)": r.cell + "-" + string(v: r.uid),
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
          transformations=column_order(["시각", "UE (cell-uid)", "구간", "방향", "프로토콜", "메시지", "원본"]), new_line=True)

    # ---- 변수·주석
    variables = [
        source_variable(),
        query_variable("cell", "셀", f'''
import "influxdata/influxdb/schema"
schema.tagValues(bucket: v.defaultBucket, tag: "cell", start: -30d,
  predicate: (r) => (r._measurement == "kpm2" or r._measurement == "alert") and {ENV})
''', multi=True, include_all=True, description="탐지 결과·상시 KPM2 그래프·경보 목록에 넣을 셀"),
        # 경보는 대시보드를 열 때(와 출처를 바꿀 때)만 읽는다(D219). 5초 새로고침마다 다시 읽으면, 그 조회가 취소될 때
        # Grafana가 선택지를 []로 받아 값을 비우고 다음 조회에서 첫 경보로 바꿔, 행을 눌러 고른 경보가 되돌아갔다(11/25).
        # 행을 누르면 값은 주소로 들어오므로 선택지에 없어도 된다. 범위는 경보 목록과 같게 1시간 앞부터(열린 경보 포함)
        query_variable("alert_id", "경보", f'''
import "date"
from(bucket: v.defaultBucket)
  |> range(start: date.sub(d: 1h, from: v.timeRangeStart), stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "alert" and r._field == "severity" and r.event == "raise" and {ENV})
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> map(fn: (r) => ({{_value: r.alert_id}}))
  |> unique()
  |> limit(n: 500)
''', description="경보 상세에 보일 경보. 경보 목록에서 행을 누르면 바뀐다", refresh=1),
    ]
    variables[2]["sort"] = 0
    variables[2]["hide"] = 2  # 위쪽 칸은 숨긴다(11/16) — 경보 목록에서 행을 눌러 고르고, 경보 상세 행 제목에 보인다

    # 경보 구간은 주석이 아니라 KPM 두 패널의 경보 계열(refId B)로 칠한다 — 주석은 새로고침마다 깜빡였다(D209, alert_hover_query)
    gaps = f'''
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "gap" and r._field == "t_to" and {ENV})
  |> group()
  |> map(fn: (r) => ({{_time: r._time, timeEnd: time(v: r._value * 1000000), text: "데이터 없음 (gap, 경보 " + r.alert_id + ")", tags: "gap"}}))
'''
    # 칸 일부 없음 = 보고 줄 수 n이 '가득 찬 n'(3000 ÷ 그 세션의 hello.period_ms)보다 적은 3초 칸(D214). 7일이면 수만 칸이라
    # (AWS 6만) 저장소에서 series(세션·셀)마다 구간(win)으로 묶고(D202) 세션 주기는 그 뒤에 붙인다. 저장소 거르기는 고정값(n < 30,
    # agg_ms 3000)이어야 한다 — n * 주기 < agg_ms처럼 열끼리 비교하면 7일에 1.4초. 주기가 100 ms보다 짧은 세션은 n 30 미만만 본다.
    # 주기가 100 ms보다 길면 n < 30 칸 수가 일부 없는 칸 수가 아니라(가득 찬 칸도 든다) 칸 수는 빼고 가장 적은 n만 적는다.
    # 세션 → 주기는 사전으로 찾는다 — join 패키지는 한쪽이 비면(일부 없는 칸이 없으면 늘) 'cannot join on an empty table'로 깨진다.
    # hello는 세션 시작 때 한 번이라 화면 범위 앞에 있을 수 있어 처음부터 찾는다(세션 수만큼이라 가볍다). 없으면 100 ms로 본다
    partial = f'''
import "array"
import "dict"
import "strings"
{WINDOW}
hello = from(bucket: v.defaultBucket)
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "hello" and r._field == "period_ms" and {ENV})
  |> map(fn: (r) => ({{_time: r._time, kv: string(v: int(v: r._value)) + " " + r.session}}))
  |> group()
  |> findColumn(fn: (key) => true, column: "kv")
// 빈 배열이면 array.map이 형식을 잃어(fromList가 [string]으로 받음) 늘 기본 항목 하나를 붙인다(빈 세션 이름 = 쓰이지 않는 키)
periods = dict.fromList(pairs: array.map(arr: array.concat(arr: hello, v: ["{KPM2_PERIOD_MS} "]), fn: (x) => {{
    p = strings.splitN(v: x, t: " ", i: 2)
    return {{key: p[1], value: int(v: p[0])}}
}}))
part = (fn) => {kpm2_source(["n"], extra=f' and r.agg_ms == "{SLOT_MS}" and r._value < {KPM2_FULL_N}')}
  |> aggregateWindow(every: win, fn: fn, createEmpty: false, timeSrc: "_start")
  |> group(columns: ["session", "cell"])
slots = part(fn: count) |> set(key: "_field", value: "slots")
low = part(fn: min) |> set(key: "_field", value: "low")
union(tables: [slots, low])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> map(fn: (r) => {{
      p = dict.get(dict: periods, key: r.session, default: {KPM2_PERIOD_MS})
      period = if p > 0 then p else {KPM2_PERIOD_MS}
      full = {SLOT_MS} / period
      return {{_time: r._time, timeEnd: time(v: int(v: r._time) + int(v: win)), low: float(v: r.low), full: float(v: full),
        text: "칸 일부 없음 — " + (if full >= {KPM2_FULL_N} then "3초 칸 " + string(v: r.slots) + "개, " else "")
          + "가장 적은 칸 n " + string(v: r.low) + " / " + string(v: full)
          + (if period != {KPM2_PERIOD_MS} then " (보고 주기 " + string(v: period) + " ms)" else "") + " (셀 " + r.cell + ")",
        tags: "partial"}}
    }})
  |> filter(fn: (r) => r.low < r.full)
  |> keep(columns: ["_time", "timeEnd", "text", "tags"])
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

TEXT_COLOR = {"mode": "fixed", "fixedColor": "text"}


def flux_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)  # Flux 문자열 이스케이프(\" \\)는 JSON과 같다


def rule_name_dict() -> str:
    """룰 ID → 짧은 공격 이름(Flux 사전). 막대 그래프는 이름 열을 그대로 축에 쓴다."""
    names = {**RULE_NAMES["rules"], **RULE_NAMES["candidates"]}
    return "[" + ", ".join(f"{flux_str(k)}: {flux_str(short_rule_name(v))}" for k, v in names.items()) + "]"


def evidence_renames(rule: str, section: str) -> list[tuple[str, str]]:
    """그 룰·항목에서 실제로 바뀌는 (키, 이름) — 이름이 키와 같은 것은 뺀다."""
    return [(k, v) for k, v in EVIDENCE_KEY_NAMES.get(rule, {}).get(section, {}).items() if k != v]


def evidence_rename_fn() -> str:
    """Flux 함수 rename(rule, field, s): 판정 근거 값 JSON 문자열의 키를 화면 이름으로(11/25, 35_ 엑셀). 같은 키라도
    룰·항목마다 이름이 달라 룰·필드로 가른다. collector가 쓴 압축 JSON(공백 없음)이라 객체 키는 '"키":', 배열 원소는
    '"키"'로 찾는다 — 따옴표까지 맞추므로 C2가 C2a를, n_stall이 n_stall_frac을 건드리지 않는다. 대응표에 없는 키는 그대로."""
    branches = []
    for rule in EVIDENCE_KEY_NAMES:
        for field, section in EVIDENCE_FIELDS.items():
            suffix = "" if section in ("cond", "conditions") else ":"
            expr = "s"
            for key, name in evidence_renames(rule, section):
                expr = (f"strings.replaceAll(v: {expr}, t: {flux_str(json.dumps(key) + suffix)}, "
                        f"u: {flux_str(json.dumps(name) + suffix)})")
            if expr != "s":
                branches.append(f'if rule == {flux_str(rule)} and field == "{field}" then {expr}')
    return "rename = (rule, field, s) =>\n    " + "\n    else ".join(branches) + "\n    else s"


def candidate_hide_fn() -> str:
    """Flux 함수 hide_candidates(rule, s): candidates JSON 문자열에서 rule-names.json hidden_candidates의 ID를 뺀다
    (AN-02의 L3-25-OV — AN-02가 '상향 IMSI 노출'이 되어 후보 '상향 IMSI 추출'과 겹침, 탐지 쪽 요청 11/27). collector가 쓴
    압축 JSON이라 '"ID",' → ',"ID"' → '"ID"' 순으로 지우면 남은 배열이 그대로 JSON이다(따옴표까지 맞춰 다른 ID는 안 건드림)."""
    branches = []
    for rule, ids in RULE_NAMES["hidden_candidates"].items():
        expr = "s"
        for cid in ids:
            for text in (json.dumps(cid) + ",", "," + json.dumps(cid), json.dumps(cid)):
                expr = f'strings.replaceAll(v: {expr}, t: {flux_str(text)}, u: "")'
        branches.append(f"if rule == {flux_str(rule)} then {expr}")
    if not branches:
        return "hide_candidates = (rule, s) => s"
    return "hide_candidates = (rule, s) =>\n    " + "\n    else ".join(branches) + "\n    else s"


def rep_name_dict() -> str:
    """대표 값 키(rep_key, values의 키) → 화면 이름. 사전 키는 '룰|키'(룰마다 이름이 달라서)."""
    pairs = [(f"{rule}|{key}", name) for rule in EVIDENCE_KEY_NAMES for key, name in evidence_renames(rule, "values")]
    return "dict.fromList(pairs: [" + ", ".join(f"{{key: {flux_str(a)}, value: {flux_str(b)}}}" for a, b in pairs) + "])"


def alerts_in_range() -> str:
    """고른 시간 범위에서 시작한(raise) 경보 = 한 행(alert_summary). 끝난 실험을 보므로 근거는 읽지 않는다.
    탐지 결과 두 패널은 이벤트·심각도·시각만 써서 severity만 읽는다(읽는 시간이 필드 수에 비례)."""
    return f"""{alert_summary("date.sub(d: 1h, from: v.timeRangeStart)", None, fields=("severity",))}
in_range = summary
  |> filter(fn: (r) => r.start >= v.timeRangeStart and {CELL_REGEX})"""


def stat_options(fields: str = "", values: bool = False) -> dict:
    return {"colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "justifyMode": "center",
            "reduceOptions": {"calcs": [] if values else ["lastNotNull"], "fields": fields, "values": values},
            "orientation": "vertical"}


# --------------------------------------------------------------------------- 성능 — CU 자원 (수집 오버헤드, M11)

OVERHEAD = 'r._measurement == "overhead"'
# overhead는 늘 CU 박스의 분석 엔진(계측기)이 보낸다(27_ §9 R5) — 노드는 CU 하나로 보이고, 시간 그래프도 노드로 나누지 않는다
# (D215). node_id는 분석 엔진을 실행할 때 붙인 이름(--node 또는 호스트 이름)이라 cu → p4-cu → p4-e2e로 바뀌어 왔고,
# 탐지 쪽 전송기는 hello의 node_id만 cu로 바꾸고 overhead 줄은 그대로 보낸다(detection dashboard_sender.py). 한 출처 안에서
# 이름이 다른 노드가 같은 시각에 보낸 적은 없다(AWS 30일 확인, 11/20). 이름이 바뀔 때마다 범례가 둘씩 나왔다(11/16·11/20)
OVERHEAD_STALE_S = 30  # 마지막 overhead가 이보다 오래되면 '수신 멈춤'으로 칠한다(3초 구간 10개)
# 노드·CPU/메모리 평균 사용률 칸의 글자 크기(px) — 자동이면 칸 폭·값 수에 따라 달라져 요약 칸 숫자가 노드 칸보다 훨씬 컸다(사용자 요청 11/20)
OVERHEAD_STAT_TEXT = {"titleSize": 14, "valueSize": 24}


def overhead_pivot(fields: list[str], measurement: str = "overhead") -> str:
    """고른 시간 범위의 overhead 필드들을 시각(구간 시작)마다 한 행으로(원본 그대로 — 'CPU/메모리 평균 사용률' 전용).
    세션(series)마다 표가 나뉘어 있다."""
    cond = " or ".join(f'r._field == "{f}"' for f in fields)
    return f'''from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "{measurement}" and {ENV} and ({cond}))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''


def overhead_windowed(fields: list[str]) -> str:
    """시간 그래프용 overhead — 필드마다 구간(win) 평균으로 묶은 뒤(저장소에서 계산) 시각마다 한 행으로(D202).
    계산(사용률)은 묶은 값으로 한다. 빈 구간은 모든 필드가 null인 행이라, 계산식은 debug.null로 null을 낸다.
    노드·세션 구분 없이 한 계열(CU, D215)."""
    cond = " or ".join(f'r._field == "{f}"' for f in fields)
    return f'''from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => {OVERHEAD} and {ENV} and ({cond}))
{window_by("mean", ["_field"], fill=True)}
  |> group(columns: [])
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''


def null_unless(fields: list[str], expr: str) -> str:
    """fields가 모두 있을 때만 expr, 아니면 null(빈 구간에서 선을 끊으려고 — Flux에는 null 값 문법이 없다)."""
    cond = " and ".join(f"exists r.{f}" for f in fields)
    return f'if {cond} then {expr} else debug.null(type: "float")'


def timeseries_defaults(unit: str, min_zero: bool = True, **custom) -> dict:
    # 선 끊기는 쿼리의 빈 구간 null 행으로 한다(insertNulls는 고정 ms라 묶은 구간 길이를 모른다, D202)
    return {"unit": unit, **({"min": 0} if min_zero else {}), "displayName": "${__field.name}",
            "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 25, "spanNulls": False,
                       "showPoints": "never", **custom}}


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
  |> map(fn: (r) => ({{_time: r._time, 노드: "CU",
      코어: if exists r.cpu_count then r.cpu_count else 0,
      메모리: if exists r.mem_total_bytes then r.mem_total_bytes else 0,
      "마지막 수신": float(v: int(v: now()) - int(v: r._time)) / 1000000000.0}}))
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
  |> drop(columns: ["_time"])
'''
    b.add("stat", "노드", 0, 8, 4, [target(node_info)],
          "overhead를 보내는 노드와 코어 수·전체 메모리(마지막 값). overhead는 늘 CU의 분석 엔진이 보내 노드는 CU로 보인다 "
          "(node_id는 분석 엔진을 실행할 때 붙인 이름이라 p4-cu·p4-e2e 등으로 바뀌어 와서 쓰지 않는다). "
          "마지막 수신 = 마지막 3초 구간이 "
          f"시작한 뒤 지난 시간(데이터 시각 기준) — {OVERHEAD_STALE_S}초를 넘으면 빨강. 화면 시간 범위와 상관없이 최근 30일에서 찾는다",
          field_config={"defaults": {"color": TEXT_COLOR, "noValue": "overhead 없음"},
                        "overrides": [override("메모리", ("unit", "bytes")),
                                      override("마지막 수신", ("unit", "s"), ("decimals", 0),
                                               ("color", {"mode": "thresholds"}),
                                               ("thresholds", {"mode": "absolute", "steps": [
                                                   {"color": "green", "value": None},
                                                   {"color": "red", "value": OVERHEAD_STALE_S}]}))]},
          options={**stat_options("/.*/"), "text": OVERHEAD_STAT_TEXT},
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
engine = {overhead_pivot(["process_cores", "cpu_count"])}
  |> filter(fn: (r) => exists r.process_cores and exists r.cpu_count and r.cpu_count > 0)
  |> map(fn: (r) => ({{_time: r._time, _value: float(v: r.process_cores) / float(v: r.cpu_count) * 100.0}}))
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
array.from(rows: [{{"CPU 평균 사용률": pick(tables: cpu |> mean()), "메모리 평균 사용률": pick(tables: mem |> mean()),
  "분석 엔진 평균 CPU": pick(tables: engine |> mean()),
  "분석 엔진 평균 메모리": pick(tables: field(name: "process_rss_bytes") |> mean())}}])
'''
    no_data = [{"type": "value", "options": {"-1": {"text": "없음", "index": 0}}}]
    # 평균만 — 최대(3초 한 칸의 순간값)는 다른 프로그램 하나로도 튀어 대표 값이 못 되고 시간 그래프에 보인다(사용자 요청 11/20)
    SUMMARY_FIELDS = ["CPU 평균 사용률", "메모리 평균 사용률", "분석 엔진 평균 CPU", "분석 엔진 평균 메모리"]
    b.add("stat", "CPU/메모리 평균 사용률", 8, 16, 4,  # 11/20 전 '고른 시간 범위 요약'(사용자 요청)
          [target(summary)],
          "고른 시간 범위의 평균 — 왼쪽 둘은 노드 전체, 오른쪽 둘은 그 가운데 분석 엔진(계측기 프로세스, process_scope self) 몫. "
          "CPU 사용률 = 바쁜 코어 / 코어 수, 메모리 사용률 = (MemTotal − MemAvailable) / MemTotal, 분석 엔진 CPU = 분석 엔진 코어 / "
          "노드 코어 수(노드 CPU 전체의 %), 분석 엔진 메모리 = RSS. 탐지 엔진·전송기는 노드 값에만 섞여 있다. "
          "순간 최고치는 아래 시간 그래프에서 본다",
          field_config={"defaults": {"color": TEXT_COLOR, "mappings": no_data},
                        "overrides": [override("CPU 평균 사용률", ("unit", "percent"), ("decimals", 1)),
                                      override("메모리 평균 사용률", ("unit", "percent"), ("decimals", 1)),
                                      override("분석 엔진 평균 CPU", ("unit", "percent")),  # 0.01% 안팎이라 소수 자리는 자동
                                      override("분석 엔진 평균 메모리", ("unit", "bytes"))]},
          options={**stat_options("/.*/"), "text": OVERHEAD_STAT_TEXT}, new_line=True,
          transformations=[{"id": "organize", "options": {  # 전체 둘, 분석 엔진 둘 순서로 고정
              "excludeByName": {}, "renameByName": {},
              "indexByName": {name: i for i, name in enumerate(SUMMARY_FIELDS)}}}])

    # 시간 그래프는 모두 구간 평균(사용자 결정 11/18) — 3초 값의 뜻(구간 평균)을 넓힌 것. 평균은 'CPU/메모리 평균 사용률'이 원본으로
    # 왼쪽 = 노드 전체, 오른쪽 = 분석 엔진 몫. 계열이 하나라 범례는 숨긴다(사용자 요청 11/20 — '내역'(분석 엔진 + 그 밖 쌓기)과
    # 점선(코어 수·전체 메모리)을 없애고 제목을 '(전체)'·'(분석 엔진)'으로)
    imports = 'import "internal/debug"'
    window_note = " 긴 시간 범위에서는 3초 배수 구간의 평균"
    no_legend = {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
                 "tooltip": {"mode": "multi", "sort": "none"}}

    def single(title: str, x: int, fields: list[str], name: str, expr_fields: list[str], expr: str, unit: str,
               color: str, description: str, cpu_axis: bool = False) -> None:
        query = f'''
{imports}
{WINDOW}
{overhead_windowed(fields)}
  |> map(fn: (r) => ({{_time: r._time, "{name}": {null_unless(expr_fields, expr)}}}))
  |> sort(columns: ["_time"])
'''
        b.add("timeseries", title, x, 12, 8, [target(query)], description + window_note,
              field_config={"defaults": {**timeseries_defaults(unit, **({"axisSoftMax": CPU_AXIS_SOFT_MAX}
                                                                         if cpu_axis else {})),
                                         "color": {"mode": "fixed", "fixedColor": color}}, "overrides": []},
              options=no_legend, new_line=x == 12)

    single("CPU 사용률(전체)", 0, ["node_busy_cores", "cpu_count"], "CPU 사용률", ["node_busy_cores", "cpu_count"],
           "r.node_busy_cores / r.cpu_count * 100.0", "percent", "blue",
           "노드 전체. 구간(3초) 동안 노드가 바쁘게 돈 코어 수 / 코어 수. 분석 엔진·탐지 엔진·전송기·CU가 모두 들어 있다. "
           f"세로축은 0~{CPU_AXIS_SOFT_MAX}%로 시작하고 값이 넘으면 늘어난다.",
           cpu_axis=True)
    single("CPU 사용률(분석 엔진)", 12, ["process_cores", "cpu_count"], "분석 엔진", ["process_cores", "cpu_count"],
           "r.process_cores / r.cpu_count * 100.0", "percent", "orange",
           "분석 엔진(계측기 프로세스, process_scope self)이 쓴 코어 / 노드 코어 수 — 왼쪽 전체와 같은 기준(노드 CPU 전체의 %). "
           "탐지 엔진·전송기는 들어 있지 않다(전체에만). 커널 안에서 도는 eBPF 프로그램 시간은 그 이벤트를 일으킨 CU 스레드 쪽"
           "(전체)에 잡힌다.")
    single("메모리 사용량(전체)", 0, ["mem_used_bytes"], "사용 중", ["mem_used_bytes"], "r.mem_used_bytes", "bytes", "green",
           "노드 전체. 사용 중 = MemTotal − MemAvailable(구간 끝 순간값). 전체 메모리는 위 '노드' 칸.")
    single("메모리 사용량(분석 엔진)", 12, ["process_rss_bytes"], "분석 엔진 (RSS)", ["process_rss_bytes"],
           "r.process_rss_bytes", "bytes", "orange",
           "분석 엔진(계측기 프로세스)이 실제로 차지한 메모리(resident, RSS).")

    # 링크 값은 SCTP 패킷만 센다(F1AP·NGAP 시그널링 — F1-U 사용자 데이터는 빠짐, 탐지 쪽 11/13)
    def link_rate(kind: str) -> str:
        """overhead_link의 <방향>_<kind> 구간 증가분 ÷ 구간 길이 = 초당 값. Ingress·Egress × 링크마다 한 계열.
        방향 이름은 필드 이름(ingress·egress)과 같은 영어(사용자 요청 11/20 — 전에는 들어옴·나감).
        증가분을 구간(win) 평균으로 묶어(저장소에서 계산) 3초로 나눈다 — overhead 구간은 3초다(AWS 7일 217,834줄 모두 3000 ms)."""
        link = ('if not exists r.role then r.iface else if r.role == "f1" then "F1" else if r.role == "n2" then "N2" '
                'else if r.role == "f1+n2" then "F1+N2" else r.role')
        between = f'''  |> map(fn: (r) => {{
      link = {link}
      return {{r with link: link,
        dir: if r._field == "ingress_{kind}" then (if link == "F1" then "Ingress (DU → CU)" else if link == "N2" then "Ingress (AMF → CU)" else "Ingress")
             else (if link == "F1" then "Egress (CU → DU)" else if link == "N2" then "Egress (CU → AMF)" else "Egress")}}
    }})'''
        return f'''
{WINDOW}
from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "overhead_link" and {ENV} and (r._field == "ingress_{kind}" or r._field == "egress_{kind}"))
{window_by("mean", ["link", "dir", "iface"], between=between, fill=True)}
  |> map(fn: (r) => ({{_time: r._time, link: r.link, dir: r.dir, iface: r.iface,
      _value: if exists r._value then r._value / {SLOT_MS / 1000} else r._value}}))
  |> sort(columns: ["_time"])
'''

    link_note = ("선언한 NIC마다 SCTP 패킷(F1AP·NGAP 시그널링)만 센 구간 증가분 ÷ 구간 길이(3초 평균, 긴 시간 범위에서는 "
                 "3초 배수 구간의 평균) — F1-U 사용자 데이터(GTP-U)는 "
                 "들어 있지 않다. 계열 = 링크(F1: CU ↔ DU, N2: CU ↔ 코어 AMF) × 방향 — 위 = Ingress(CU로 들어옴), 아래 = Egress(CU에서 나감). "
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
                            "overrides": [override(".*Egress.*", ("custom.transform", "negative-Y"), regex=True)]},
              options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                       "tooltip": {"mode": "multi", "sort": "none"}}, new_line=x == 12)

    # 두 쿼리가 같은 win으로 묶여 칸끼리 겹친다(CPU 구간 평균, 연결 시도 구간 합)
    load = f'''
import "internal/debug"
{WINDOW}
{overhead_windowed(["node_busy_cores", "cpu_count"])}
  |> map(fn: (r) => ({{_time: r._time, "CPU 사용률": {null_unless(["node_busy_cores", "cpu_count"],
                                                              "r.node_busy_cores / r.cpu_count * 100.0")}}}))
  |> sort(columns: ["_time"])
'''
    attempts = f'''
{WINDOW}
{kpm2_source(["cc.RRC.ConnEstabAtt.total"])}
{window_by("sum", [])}
  |> map(fn: (r) => ({{_time: r._time, "RRC 연결 시도": r._value}}))
'''
    b.add("timeseries", "CPU 사용률 · RRC 연결 시도", 0, 24, 8,
          [target(load, "A"), target(attempts, "B")],
          "공격으로 연결 시도가 몰릴 때 CU CPU가 얼마나 오르나. 왼쪽 축 = 노드 CPU 사용률, 오른쪽 축(막대) = 상시 KPM2 RRC 연결 시도"
          "(위쪽 셀 변수로 고른 셀의 합). 둘 다 같은 구간(3초, 긴 시간 범위에서는 3초 배수 구간 — CPU는 평균, 연결 시도는 합)이라 "
          f"칸끼리 겹친다. 왼쪽 축은 0~{CPU_AXIS_SOFT_MAX}%로 시작하고 값이 넘으면 늘어난다. "
          "상시 KPM2가 없는 출처(샘플 등)에서는 RRC 연결 시도가 안 보인다",
          # 축 범위는 CPU 계열에만 건다 — 기본값에 두면 override의 null로 풀리지 않아 오른쪽 축까지 묶인다
          # (예전 max 100 + override max null에서 오른쪽 축이 0~100으로 고정됐음, 11/25)
          field_config={"defaults": {**timeseries_defaults("percent"),
                                     "color": {"mode": "fixed", "fixedColor": "blue"}},
                        "overrides": [override("CPU 사용률", ("custom.axisSoftMax", CPU_AXIS_SOFT_MAX)),
                                      override("RRC 연결 시도.*", ("unit", "none"),
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
      and {CELL_REGEX})
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


# --------------------------------------------------------------------------- 성능 — 수집 지연 (D211)

# 수집 지연 = collector가 /ingest로 받은 시각 − 레코드의 데이터 시각(collector/influx_writer.py DELAY_REFERENCE)
DELAY_TYPES = (("kpm2", "KPM 지연"), ("alert", "경보 지연"))  # 표의 종류 이름 = 추이 그래프 계열 이름
# 표의 열: 백분위(정렬한 값에서 순위 int((n − 1) × q))와 개수. 경보처럼 개수가 적으면 p99가 맨 위 값에 가까워 개수를 같이 보인다
DELAY_PERCENTILES = (("p50", 0.5), ("p95", 0.95), ("p99", 0.99))


def delay_source(kind: str) -> str:
    return f'''from(bucket: v.defaultBucket)
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "ingest_delay" and {ENV} and r.type == "{kind}" and r._field == "delay_ms")'''


def add_ingest_delay_rows(b: Board) -> None:
    b.row("수집 지연")
    # 백분위는 정렬한 값에서 순위로 고른다(정확값, 한 번 읽기) — quantile을 백분위마다 부르면 데이터를 그만큼 다시 읽는다.
    # 표 한 행 = 종류 하나(사용자 요청 11/20 — 처음에는 stat 숫자 6개)
    parts, rows = [], []
    for kind, label in DELAY_TYPES:
        parts.append(f'''{kind} = {delay_source(kind)}
  |> group()
  |> sort(columns: ["_value"])
  |> findColumn(fn: (key) => true, column: "_value")
{kind}_n = length(arr: {kind})''')
        cells = [f'종류: "{label}"', f"개수: {kind}_n"]
        cells += [f'{name}: if {kind}_n == 0 then -1.0 else {kind}[int(v: float(v: {kind}_n - 1) * {q})]'
                  for name, q in DELAY_PERCENTILES]
        rows.append("{" + ", ".join(cells) + "}")
    table_query = '\nimport "array"\n' + "\n".join(parts) + "\narray.from(rows: [\n  " + ",\n  ".join(rows) + "])\n"
    no_data = [{"type": "value", "options": {"-1": {"text": "없음", "index": 0}}}]
    columns = ["종류", *(name for name, _ in DELAY_PERCENTILES), "개수"]
    b.add("table", "수집 지연 백분위", 0, 10, 7, [target(table_query)],
          "탐지 엔진 전송기가 보낸 레코드가 대시보드 서버에 도착해 저장되기까지 걸린 시간(받은 시각 − 데이터 시각)의 "
          "고른 시간 범위 백분위와 개수(범위 안 레코드 전체를 정렬해 고른 값). 상시 KPM2는 3초 칸이 끝난 시각부터(전송기 1초 묶음 + 네트워크 + 저장), 경보는 탐지 엔진이 "
          "판정한 시각부터(raise·update·clear·end 모두). 경보는 개수가 적어 p99가 맨 위 값과 거의 같다. 화면에는 여기에 관제 새로고침 "
          "대기(최대 5초)와 쿼리 시간(0.5초 이하)이 더해진다. 분석 엔진 노드와 대시보드 서버의 시계가 어긋나면 그만큼 틀린다. "
          "없음 = 고른 범위에 레코드가 없음(11/20 전에는 재지 않음)",
          field_config={"defaults": {"unit": "ms", "decimals": 0, "mappings": no_data,
                                     "custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                        "overrides": [override("종류", ("unit", "string"), ("custom.width", 110)),
                                      override("개수", ("unit", "none"))]},
          options={"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
          transformations=column_order(columns))

    def trend(kind: str, fn: str, name: str, fill: bool) -> str:
        return f'''{delay_source(kind)}
{window_by(fn, ["type"], fill=fill)}
  |> map(fn: (r) => ({{_time: r._time, _value: r._value, _field: "{name}"}}))'''
    # 갈래마다 from을 따로(저장소에서 묶음), 긴 꼴로 합친 뒤 pivot — 열 이름이 다른 표끼리는 union이 안 된다.
    # 모든 갈래가 같은 win 구간(epoch 정렬)이라 시각이 맞아, 경보 점 때문에 상시 KPM2 선에 빈 행이 끼지 않는다
    trend_query = f'''
{WINDOW}
kmean = {trend("kpm2", "mean", "KPM 지연", True)}
amean = {trend("alert", "mean", "경보 지연", False)}
union(tables: [kmean, amean])
  |> group()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    b.add("timeseries", "수집 지연 추이", 10, 14, 7, [target(trend_query)],
          "수집 지연(받은 시각 − 데이터 시각)의 추세 — 그래프 구간(1시간 화면 3~6초, 7일 화면 약 5분)마다 그 안에 도착한 "
          "레코드 지연의 평균(백분위의 평균이 아님). 전송기 재시도(1~60초)나 서버가 느려진 때 올라간다. KPM 지연 = 파랑, "
          "경보 지연 = 주황(경보는 드물어 경보가 온 구간끼리 이어 그린다)",
          field_config={"defaults": timeseries_defaults("ms", showPoints="auto"),
                        "overrides": [# 경보는 드물어 구간 대부분이 비어 있다 — 점 사이를 이어 선으로(빈 구간을 건너뜀), 실제 값 자리는 점으로
                                      override("경보 지연", ("color", {"mode": "fixed", "fixedColor": "orange"}),
                                               ("custom.spanNulls", True), ("custom.showPoints", "always"),
                                               ("custom.pointSize", 4), ("custom.fillOpacity", 0)),
                                      override("KPM 지연", ("color", {"mode": "fixed", "fixedColor": "blue"}))]},
          options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                   "tooltip": {"mode": "multi", "sort": "none"}}, new_line=True)


def performance() -> dict:
    b = Board()

    # 탐지 결과는 관제로 옮기고 경보·입력 품질 줄은 없앴다(11/16 사용자 결정) — 성능은 CU 자원과 수집 지연
    # ---- CU 자원 (수집 오버헤드, M11)
    add_overhead_rows(b)
    # ---- 수집 지연 (D211)
    add_ingest_delay_rows(b)

    variables = [
        source_variable(),
        query_variable("cell", "셀", f'''
import "influxdata/influxdb/schema"
schema.tagValues(bucket: v.defaultBucket, tag: "cell", start: -30d,
  predicate: (r) => (r._measurement == "kpm2" or r._measurement == "alert") and {ENV})
''', multi=True, include_all=True, description="CPU 사용률 · RRC 연결 시도 그래프의 RRC 연결 시도에 넣을 셀"),
    ]
    return dashboard("portran-performance", "PortRAN 성능",
                     "CU 자원(수집 오버헤드 — 노드·분석 엔진 CPU·메모리, F1·N2 SCTP)과 수집 지연(레코드가 대시보드에 도착하기까지). docs/dashboard-design.md 3절",
                     b, variables, [], refresh="1m", time_from="now-24h")


# --------------------------------------------------------------------------- 알림 — Slack (M12)

# 알림은 실측(aws·on-premise)에서만 보낸다(11/13 사용자 결정 — 재생·샘플·이전 p4는 알리지 않음).
# 알림을 보내는 실측 출처 (X-Env 값, 이름, 규칙 UID 꼬리). AWS 규칙 UID는 예전 그대로(알림 상태가 이어지게),
# On-Premise는 받기 시작해 더함(11/20 사용자 결정, D213 — 11/13에는 'On-Premise는 받기 시작하면 더한다')
NOTIFY_SOURCES = (("aws", "AWS", ""), ("on-premise", "On-Premise", "-onprem"))
NOTIFY_INTERVAL = "10s"           # 규칙을 조회하는 주기
ATTACK_LOOKBACK_S = 6 * 3600      # 공격·이상 유형 경보를 찾는 범위. 이보다 오래 열린 경보는 '끝 소식 없음'으로 끝난다
COLLECT_STOP_S = 300              # 수집 멈춤: 마지막 레코드 뒤 이만큼 아무것도 없으면
COLLECT_LOOKBACK_S = 3600         # 이 범위에 아무것도 없으면 테스트베드를 끈 것으로 보고 알리지 않는다
# 알리는 경보 종류(화면 종류 — CLASS_EXPR). 처음에는 공격만(11/13 사용자 결정), 11/27부터 이상 유형도(사용자 요청, D222).
# 판정 보류는 알리지 않는다
NOTIFY_CLASSES = ("공격", "이상 유형")
ALERTING_OUT = ROOT / "provisioning" / "alerting" / "portran.json"
SLACK_ALL = "PortRAN Slack"
SLACK_NO_RESOLVE = "PortRAN Slack (해제 알림 없음)"

# 알림 메시지(Slack). 한 알림 = 경보 하나(group_by alert_id)라서 .CommonLabels·.CommonAnnotations만 쓴다.
# provisioning 파일은 환경변수를 바꿔 넣으므로 템플릿에 '$'를 쓰지 않는다.
NOTIFY_TEMPLATE = (
    '{{ define "portran.title" }}{{ if eq .CommonLabels.notify "collect" }}⚠️ PortRAN 수집 멈춤'
    '{{ else if eq .Status "firing" }}{{ if eq .CommonLabels.class "이상 유형" }}🔶 PortRAN 이상 유형'
    '{{ else }}🚨 PortRAN 공격 경보{{ end }}'
    '{{ else }}✅ PortRAN {{ if eq .CommonLabels.class "이상 유형" }}이상 유형{{ else }}공격 경보{{ end }} 끝{{ end }}'
    ' · {{ .CommonLabels.source }}{{ end }}\n'
    '{{ define "portran.text" }}{{ if eq .CommonLabels.notify "collect" }}{{ .CommonAnnotations.summary }}'
    '{{ else }}*{{ .CommonLabels.attack }}* · 셀 {{ .CommonLabels.cell }} · '
    '{{ if eq .Status "firing" }}{{ .CommonAnnotations.severity }} · 시작 {{ .CommonLabels.start }}'
    '{{ else }}{{ .CommonAnnotations.status }}{{ end }}\n'
    # ExternalURL(= GF_SERVER_ROOT_URL)은 Grafana가 늘 '/'로 끝나게 맞춘다
    '<{{ .ExternalURL }}d/portran-monitoring?var-source={{ .CommonLabels.env }}&var-alert_id={{ .CommonLabels.alert_id }}|경보 상세 보기>'
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


def source_rules(env_value: str, name: str, uid_tail: str) -> list[dict]:
    """출처 하나의 알림 규칙 두 개(공격·이상 유형 경보, 수집 멈춤). 라벨 source(이름)·env(X-Env 값)는 메시지 제목과 경보 상세 링크에,
    경보 계열의 라벨 class(종류)는 메시지 제목에 쓴다."""
    env = f'r.env == "{env_value}"'
    # 알리는 종류(NOTIFY_CLASSES — 공격·이상 유형, 11/27)의 경보마다 한 계열. 이상 유형은 4단계 AN-와 화면에서 이상 유형으로
    # 보이는 L3-24·L3-14 공격 경보(shown_as_anomaly). 판정 보류는 알리지 않는다.
    # 값: 열림(raise·update) = 1(medium)·2(high), 해제 = 0, 강제 종료 = -1. 경보 상태·종류는 alert_summary(관제 대시보드와 같은 계산)로 정한다
    classes = " or ".join(f'r.class == "{c}"' for c in NOTIFY_CLASSES)
    attacks = f'''
import "date"
import "dict"
import "strings"
names = {rule_name_dict()}
{alert_summary(f"-{ATTACK_LOOKBACK_S}s", "-5m", stop="now()").replace(ENV, env)}
summary
  |> filter(fn: (r) => {classes})
  |> map(fn: (r) => ({{alert_id: r.alert_id, rule: r.rule, cell: r.cell, class: r.class,
      attack: dict.get(dict: names, key: r.rule, default: r.rule),
      start: strings.replaceAll(v: strings.substring(v: string(v: date.add(d: 9h, to: r.start)), start: 0, end: 19), t: "T", u: " "),
      _time: now(),
      _value: if r.event == "raise" or r.event == "update" then (if r.sev == 2 then 2.0 else 1.0)
              else if r.event == "end" then -1.0 else 0.0}}))
  |> group(columns: ["alert_id", "rule", "cell", "class", "attack", "start"])
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
    labels = {"source": name, "env": env_value}
    return [
        alert_rule(f"portran-attack{uid_tail}", f"공격·이상 유형 경보 ({name})", attacks, ATTACK_LOOKBACK_S, 0,
                   {"notify": "attack", **labels},
                   # 조회 결과가 없을 때(NoData)는 .Values가 비어 있어 B를 꺼내면 템플릿이 깨진다 — with로 감싼다
                   {"severity": '{{ with .Values }}{{ if eq .B.Value 2.0 }}high{{ else }}medium{{ end }}{{ end }}',
                    "status": '{{ with .Values }}{{ if gt .B.Value 0.0 }}끝 소식 없음(6시간 안에 해제·강제 종료가 오지 않음)'
                              '{{ else if lt .B.Value 0.0 }}강제 종료{{ else }}해제{{ end }}{{ end }}',
                    "description": f"{name}(X-Env {env_value}) 공격·이상 유형 경보(관제 경보 목록의 종류 — 이상 유형은 AN-와 L3-24·L3-14)가 "
                                   "열리면 울리고, 해제·강제 종료되면 끝난다. 판정 보류 경보는 알리지 않는다(M12, 이상 유형은 11/27부터)"}),
        alert_rule(f"portran-collect-stop{uid_tail}", f"수집 멈춤 ({name})", collect, COLLECT_LOOKBACK_S, COLLECT_STOP_S,
                   {"notify": "collect", **labels},
                   {"summary": f"{name}에서 {COLLECT_STOP_S // 60}분 넘게 데이터(상시 KPM2·오버헤드·경보·근거)가 오지 않아요. "
                               "{{ with .Values }}마지막 수신 {{ printf \"%.0f\" .B.Value }}초 전. {{ end }}실험을 일부러 멈춘 거라면 무시하세요",
                    "description": f"마지막 레코드 뒤 {COLLECT_STOP_S}초. 최근 {COLLECT_LOOKBACK_S // 60}분에 아무것도 없으면 "
                                   "테스트베드를 끈 것으로 보고 울리지 않는다. 다시 들어와도 알리지 않는다"}),
    ]


def alerting() -> dict:
    rules = [rule for env_value, name, tail in NOTIFY_SOURCES for rule in source_rules(env_value, name, tail)]
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
