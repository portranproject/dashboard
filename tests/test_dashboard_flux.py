"""대시보드 Flux를 실제 InfluxDB(임시 bucket)에서 돌려 값을 확인한다 (D202).

정적 검사(test_dashboards.py)로는 못 잡는 것 — 구간(win) 묶기, 세션 합치기, 빈 구간 null, 표시 형식(ratio %, 셀-uid) —
을 합성 레코드로 본다. 레코드는 collector(/ingest 처리)로 넣고, 쿼리는 grafana/dashboards/*.json에서 꺼내 Grafana가
하듯 v.* 매크로·템플릿 변수를 바꿔 InfluxDB에 바로 보낸다. InfluxDB가 없으면 건너뛴다(tests/conftest.py temp_bucket).
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from collector.collector import Collector
from collector.influx_writer import InfluxWriter

REPO = Path(__file__).resolve().parent.parent
BOARDS = {name: json.loads((REPO / "grafana" / "dashboards" / f"{name}.json").read_text(encoding="utf-8"))
          for name in ("monitoring", "performance")}
ENV = "ftest"
T0 = 1_792_209_000_000  # ms — 6초 경계(3초 칸 둘이 한 6초 구간에 든다)
STOP = T0 + 24_000
GAP = (T0 + 6_000, T0 + 15_000)  # 이 사이(3초 칸 4개)는 상시 KPM2·overhead가 없다
L3_20 = "20261105T100800Z-L3-20-1-77"


def kpm2(session, t, att, succ, n=30, ue_ctx=1.0):
    return {"type": "kpm2", "ver": 1, "agg_ms": 3000, "session": session, "cell_id": 1, "t_start_ms": t,
            "t_end_ms": t + 3000, "n": n, "seq_from": 1, "seq_to": 2,
            "cc": {"RRC.ConnEstabAtt": {"total": att}, "RRC.ConnEstabSucc": {"total": succ},
                   "RRC.ConnEstabFailCause": {"NetworkReject": 0, "NoReply": att - succ, "Other": 0}},
            "si": {"RRC.ConnMean": 0.5, "RRC.ConnMax": 1}, "ext": {"UeCtxMax": ue_ctx}}


def overhead(seq, t, busy):
    return {"type": "overhead", "ver": 1, "session": "OH", "seq": seq, "node_id": "cu", "process_scope": "self",
            "t_start_ms": t, "t_end_ms": t + 3000, "cpu": {"count": 4, "node_busy_cores": busy, "process_cores": 0.5},
            "memory": {"total_bytes": 8_000, "used_bytes": 4_000, "process_rss_bytes": 1_000}, "link": []}


def ratio_alert(i, ratio):
    return {"type": "alert", "fmt": 1, "alert_id": f"S1-L3-01-V-1-{i}", "event": "raise", "rule": "L3-01-V", "stage": 1,
            "unit": "cell", "kind": "attack", "cell": 1, "t": T0 + 1_000 + i, "severity": "medium", "mode": "normal",
            "cond": ["C1"], "candidates": [], "values": {"a_w": 13, "f_w": 12, "ratio": ratio, "base": 1.0},
            "params": {}, "refs": {}}


def blind_dos_lines():
    """탐지 쪽 샘플 S20(L3-20, peers 있음)에서 du_ue_id만 uid와 다르게 바꾼 것 — 셀-uid와 셀-du_ue_id를 가리려고."""
    out = []
    for line in (REPO / "tests" / "data" / "detection" / "S20_L3-20_CONNECTED_high_evidence.jsonl").read_text(
            encoding="utf-8").splitlines():
        msg = json.loads(line)
        if msg["type"] == "alert":
            for ue in msg.get("ues", []):
                ue["du_ue_id"] = 7                     # uid 2 그대로 → 화면 1-2
                ue["peers"] = [[1, 4, 1]]              # 피해자 uid 1 → 화면 1-1
        elif msg["type"] == "evidence":
            msg["ue"] = [1, 7, 2]
            msg["raw"]["du_ue_id"] = 7
        out.append(msg)
    return out


@pytest.fixture(scope="module")
def flux(temp_bucket, tmp_path_factory):
    """합성 레코드를 넣고, (쿼리, win 기준 간격, 변수) → 행 목록을 돌려주는 함수."""
    client, settings = temp_bucket
    records = [kpm2("A", T0, 2, 2), kpm2("A", T0 + 3_000, 3, 1), kpm2("B", T0 + 3_000, 5, 5),
               kpm2("A", T0 + 18_000, 1, 1, n=20, ue_ctx=3.0),
               overhead(1, T0, 1.0), overhead(2, T0 + 3_000, 2.0), overhead(3, T0 + 18_000, 3.0),
               ratio_alert(1, 0.5714285714285714), ratio_alert(2, 0.9230769230769231), ratio_alert(3, 1.0),
               {"type": "alert", "fmt": 1, "alert_id": "S1-L3-01-V-1-1", "event": "clear", "rule": "L3-01-V", "stage": 1,
                "unit": "cell", "kind": "attack", "cell": 1, "t": T0 + 13_000, "severity": "medium", "mode": "normal",
                "duration_ms": 11_999, "evidence_sent": 0, "evidence_dropped": 0},
               *blind_dos_lines()]
    writer = InfluxWriter(settings, timeout_ms=10_000)
    collector = Collector(writer, tmp_path_factory.mktemp("rec"), batch_size=500, max_pending=10_000)
    body = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in records).encode("utf-8")
    status, result = collector.handle_request(body, ENV, "test")
    assert (status, result["rejected"]) == (200, 0), result
    collector.close()
    writer.close()

    def iso(ms):
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def run(query, window="2s", alert_id=L3_20):
        q = (query.replace("v.defaultBucket", json.dumps(settings.bucket)).replace("v.timeRangeStart", iso(T0))
             .replace("v.timeRangeStop", iso(STOP)).replace("v.windowPeriod", window)
             .replace("${source}", ENV).replace("${cell:regex}", "1").replace("${alert_id}", alert_id))
        assert not re.findall(r"\$\{[^}]+\}", q)
        return [rec.values for table in client.query_api().query(q, org=settings.org) for rec in table.records]

    return run


def panel_query(board, title, ref="A"):
    p = next(p for p in BOARDS[board]["panels"] if p.get("title") == title)
    return next(t["query"] for t in p["targets"] if t["refId"] == ref)


def annotation_query(name):
    return next(a["target"]["query"] for a in BOARDS["monitoring"]["annotations"]["list"] if a["name"] == name)


def ms(t):
    return int(t.timestamp() * 1000)


def test_kpm_bars_sum_sessions_per_window(flux):
    """긴 범위(간격 5s → 6초 구간)에서는 구간 안 3초 칸·세션을 모두 더한 막대 하나 — 세션이 바뀌는 구간에서도 하나(D202)."""
    rows = flux(panel_query("monitoring", "RRC 연결 시도 · 성공 · 무응답"), window="5s")
    bars = {ms(r["_time"]): (r["연결 시도"], r["연결 성공"], r["무응답 (NoReply)"]) for r in rows}
    assert bars == {T0: (10.0, 8.0, 2.0), T0 + 18_000: (1.0, 1.0, 0.0)}


def test_kpm_bars_equal_raw_at_3s_window(flux):
    """짧은 범위(간격 2s → 3초 구간)에서는 3초 칸 그대로 — 같은 칸의 두 세션(A·B)만 더해진다."""
    rows = flux(panel_query("monitoring", "RRC 연결 시도 · 성공 · 무응답"), window="2s")
    assert {ms(r["_time"]): r["연결 시도"] for r in rows} == {T0: 2.0, T0 + 3_000: 8.0, T0 + 18_000: 1.0}


def test_lines_null_in_empty_windows(flux):
    """데이터가 없는 구간은 값이 null인 행으로 남아 선이 끊긴다(0이 아님) — 관제 UE 선, 성능 CPU 내역."""
    rows = {ms(r["_time"]): r for r in flux(panel_query("monitoring", "UE 컨텍스트 · 연결 UE 수"), window="2s")}
    for t in range(GAP[0], GAP[1] + 1, 3_000):
        assert t in rows and rows[t]["UE 컨텍스트 수 (최대)"] is None and rows[t]["RRC 연결 UE (평균)"] is None, t
    assert rows[T0]["UE 컨텍스트 수 (최대)"] == 1.0 and rows[T0 + 18_000]["UE 컨텍스트 수 (최대)"] == 3.0
    assert rows[T0 + 3_000]["RRC 연결 UE (평균)"] == 0.5  # 세션 A·B 두 칸의 평균
    rows = {ms(r["_time"]): r for r in flux(panel_query("performance", "CPU 내역"), window="2s")}
    columns = ("분석 엔진", "그 밖 (탐지 엔진·전송기·CU 등)", "코어 수")
    for t in range(GAP[0], GAP[1] + 1, 3_000):
        assert t in rows and all(rows[t][c] is None for c in columns), (t, rows.get(t))
    assert [rows[T0 + 3_000][c] for c in columns] == [0.5, 1.5, 4.0]
    assert {r["node"] for r in rows.values()} == {"CU"}
    # 6초 구간이면 두 칸(busy 1·2)의 평균 1.5 → CPU 사용률 37.5%
    rows = {ms(r["_time"]): r for r in flux(panel_query("performance", "CPU 사용률"), window="5s")}
    assert rows[T0]["CPU 사용률"] == 37.5 and rows[T0 + 6_000]["CPU 사용률"] is None


def test_partial_annotation_ends_at_slot_end(flux):
    """n이 30보다 적은 칸 = 칸 일부 없음 주석 하나, 3초 구간이면 끝 = 칸 끝(시작 + 3초)."""
    [row] = flux(annotation_query("칸 일부 없음"), window="2s")
    assert (ms(row["_time"]), ms(row["timeEnd"])) == (T0 + 18_000, T0 + 21_000)
    assert "3초 칸 1개" in row["text"] and "n 20 / 30" in row["text"] and "셀 1" in row["text"]


def test_rep_ratio_shown_as_percent(flux):
    """대표 값 ratio는 %(정수) — 0.5714 → 57%. 다른 키(victims 등)는 그대로(사용자 요청 11/18)."""
    rows = {r["alert_id"]: r["대표 값"] for r in flux(panel_query("monitoring", "경보"))}
    assert rows["S1-L3-01-V-1-1"] == "ratio = 57%"
    assert rows["S1-L3-01-V-1-2"] == "ratio = 92%"
    assert rows["S1-L3-01-V-1-3"] == "ratio = 100%"
    assert rows[L3_20] == "victims = 1"


def test_alert_hover_fills_alert_window(flux):
    """경보 툴팁 계열(refId B): 경보 시작·끝과 그 사이 모든 구간 경계(win)에 값(심각도)이 있어 구간 어디서나 툴팁에
    보인다(D204). S1-L3-01-V-1-1은 T0+1.001초 raise ~ T0+13초 clear — 3초 경계 4개. raise만 있는 경보(상태 불명,
    길이 0)는 없다. 6초 구간이면 6초 경계만."""
    for title in ("RRC 연결 시도 · 성공 · 무응답", "UE 컨텍스트 · 연결 UE 수"):
        rows = flux(panel_query("monitoring", title, ref="B"), window="2s")
        assert {r["alert_id"] for r in rows} == {"S1-L3-01-V-1-1"}, title
        assert sorted(ms(r["_time"]) for r in rows) == [T0 + 1_001, T0 + 3_000, T0 + 6_000, T0 + 9_000, T0 + 12_000,
                                                        T0 + 13_000], title
        assert {r["_value"] for r in rows} == {1.0}
        assert {r["alert"] for r in rows} == {"공격 — UE 컨텍스트 고갈 · 셀 1 · 해제"}
    rows = flux(panel_query("monitoring", "RRC 연결 시도 · 성공 · 무응답", ref="B"), window="5s")
    assert sorted(ms(r["_time"]) for r in rows) == [T0 + 1_001, T0 + 6_000, T0 + 12_000, T0 + 13_000]


def test_ue_shown_as_cell_uid(flux):
    """걸린 UE·피해자 연결·UE_EVENT 두 패널의 UE는 셀-uid(du_ue_id 7을 넣었는데 화면엔 안 나옴, 사용자 요청 11/18)."""
    [ue] = flux(panel_query("monitoring", "걸린 UE"))
    assert (ue["UE (cell-uid)"], ue["피해자 연결"]) == ("1-2", "1-1")
    timeline = flux(panel_query("monitoring", "UE_EVENT — UE별 메시지 흐름"))
    assert {r["ue"] for r in timeline} == {"1-2"} and {r["key"] for r in timeline} == {"1-7-2"}
    messages = flux(panel_query("monitoring", "UE_EVENT — 메시지 흐름 상세"))
    assert messages and {r["UE (cell-uid)"] for r in messages} == {"1-2"}
