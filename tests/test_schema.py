import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from common.schema import SCHEMA_PATH, is_valid, validation_errors

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_FENCE = re.compile(r"```json\n(.*?)```", re.DOTALL)


def doc_examples(path: Path) -> list[dict]:
    return [json.loads(block) for block in JSON_FENCE.findall(path.read_text(encoding="utf-8"))]


def test_schema_file_is_valid_json_schema():
    Draft202012Validator.check_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


ALL_TYPES = ["alert", "evidence", "f1_evt", "gap", "hello", "kpm2", "overhead"]
DETECTION_SAMPLES = sorted((REPO_ROOT / "tests" / "data" / "detection").glob("*.jsonl"))


def test_schema_doc_has_one_example_per_type_and_all_pass():
    examples = doc_examples(REPO_ROOT / "schema" / "SCHEMA.md")
    assert sorted(m["type"] for m in examples) == ALL_TYPES
    for msg in examples:
        assert validation_errors(msg) == [], msg


def test_claude_md_examples_pass():
    examples = doc_examples(REPO_ROOT / "CLAUDE.md")
    assert examples, "CLAUDE.md 5절에 예시가 없음"
    for msg in examples:
        assert validation_errors(msg) == [], msg


def test_detection_samples_exist():
    assert len(DETECTION_SAMPLES) == 32  # 탐지 쪽이 11/05에 보낸 경보 경로 샘플 (reference/detection/ 분석표)


OVERHEAD_SAMPLES = sorted((REPO_ROOT / "tests" / "data" / "overhead").glob("*.jsonl"))


def test_overhead_samples_exist():
    assert [p.name for p in OVERHEAD_SAMPLES] == ["overhead-sample-3s-30.jsonl"]  # 탐지 쪽 실제 출력(11/13)


@pytest.mark.parametrize("path", DETECTION_SAMPLES + OVERHEAD_SAMPLES, ids=lambda p: p.stem)
def test_detection_sample_lines_pass(path):
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        assert validation_errors(json.loads(line)) == [], f"{path.name}:{i}"


EXAMPLES = {m["type"]: m for m in doc_examples(REPO_ROOT / "schema" / "SCHEMA.md")}


def mutated(msg_type, mutate):
    msg = copy.deepcopy(EXAMPLES[msg_type])
    mutate(msg)
    return msg


def test_new_records_accept_unknown_fields_and_nulls():
    # 탐지 쪽은 fmt·ver를 올리지 않고 필드를 더할 수 있다 (27_ §2.4)
    assert is_valid(mutated("alert", lambda m: m.update(new_field={"x": 1})))
    assert is_valid(mutated("evidence", lambda m: m.update(note="x")))
    assert is_valid(mutated("evidence", lambda m: m["raw"].update(type="something_new", t_ms="?")))  # raw는 해석 안 함
    assert is_valid(mutated("gap", lambda m: m.update(seq_from=None)))
    assert is_valid(mutated("kpm2", lambda m: m.update(extra_section={})))
    assert is_valid(mutated("kpm2", lambda m: m["cc"].update({"RRC.ConnEstabAtt": None})))
    assert is_valid(mutated("kpm2", lambda m: m.pop("partial")))
    assert is_valid(mutated("hello", lambda m: m.update(cells=[{"cell_id": 2, "max_conn": 96}])))
    assert is_valid(mutated("f1_evt", lambda m: m.update(cells=None, du_ue_ids=[1, 2])))
    assert is_valid(mutated("alert", lambda m: m.update(severity="critical", rule="L3-99")))  # 새 값은 화면이 처리
    # ue_evt: 목록 밖 메시지 이름, du_ue_id null(NGAP에서만 본 NAS 줄), 모르는 필드, f·via·sht 없음 (27_ §4.2)
    assert is_valid(mutated("evidence", lambda m: m["raw"].update(msg="ProtectedNAS", du_ue_id=None, new_key=[1])))
    assert is_valid(mutated("evidence", lambda m: [m["raw"].pop(k, None) for k in ("f", "cu_ue_id", "crnti", "ver")]))
    assert is_valid(mutated("evidence", lambda m: m["raw"].update(proto="F1AP", msg="UEContextReleaseComplete")))
    alert_ue = {"cell": 1, "du_ue_id": 2, "uid": 2, "cu_ue_id": None, "crnti": None, "s_tmsi": None,
                "seq_range": None, "values": {"known": "alloc"}, "evidence": False}
    assert is_valid(mutated("alert", lambda m: m.update(ues=[alert_ue], ues_total=1)))


def test_overhead_accepts_nulls_empty_links_and_unknown_fields():
    """overhead(11/13 탐지 쪽 형식, SCHEMA.md 6절): 못 읽은 값은 null, link 방향은 빈 객체일 수도, node_id는 없을 수도."""
    assert is_valid(mutated("overhead", lambda m: m.update(new_section={"x": 1})))
    assert is_valid(mutated("overhead", lambda m: m.pop("node_id")))
    assert is_valid(mutated("overhead", lambda m: m["cpu"].update(process_cores=None, node_busy_cores=None)))
    assert is_valid(mutated("overhead", lambda m: m["cpu"].update(node_busy_cores=3.9, process_cores=0)))  # 0은 측정값
    assert is_valid(mutated("overhead", lambda m: m["memory"].update(process_rss_bytes=None)))
    assert is_valid(mutated("overhead", lambda m: m.update(link=[{"interface_name": "br-6afe", "role": "n2",
                                                                  "ingress": {}, "egress": {}}])))
    assert is_valid(mutated("overhead", lambda m: m.update(link=[{"interface_name": "ens5", "role": "f1+n2", "ingress": {
        "sctp_packet_count": None, "wire_byte_count": None}}])))  # 첫 구간
    assert is_valid(mutated("overhead", lambda m: m.pop("link")))


def test_old_overhead_format_is_rejected():
    """v0.4까지의 overhead(ns ts·node·ebpf_on·cpu_pct·mem_mb)는 v0.5에서 받지 않는다."""
    old = {"type": "overhead", "ts": 1763280000000000000, "node": "cu", "ebpf_on": True, "cpu_pct": 23.4, "mem_mb": 512}
    assert not is_valid(old)


INVALID = {
    # 공통
    "no type": ("alert", lambda m: m.pop("type")),
    "unknown type": ("alert", lambda m: m.update(type="log")),
    "removed old type metric": ("overhead", lambda m: m.update(type="metric")),  # 옛 메시지는 M10에서 지움
    "not an object": (None, None),
    # 숫자
    "value NaN": ("overhead", lambda m: m["cpu"].update(node_busy_cores=float("nan"))),
    "value Infinity": ("overhead", lambda m: m["cpu"].update(node_busy_cores=float("inf"))),
    "value as bool": ("overhead", lambda m: m["cpu"].update(node_busy_cores=True)),
    # overhead (SCHEMA.md 6절)
    "overhead ver 2": ("overhead", lambda m: m.update(ver=2)),
    "overhead missing ver": ("overhead", lambda m: m.pop("ver")),
    "overhead missing session": ("overhead", lambda m: m.pop("session")),
    "overhead missing seq": ("overhead", lambda m: m.pop("seq")),
    "overhead missing cpu": ("overhead", lambda m: m.pop("cpu")),
    "overhead missing memory": ("overhead", lambda m: m.pop("memory")),
    "overhead t_start_ms in ns": ("overhead", lambda m: m.update(t_start_ms=m["t_start_ms"] * 1_000_000)),
    "overhead t_end_ms in seconds": ("overhead", lambda m: m.update(t_end_ms=m["t_end_ms"] // 1000)),
    "overhead cpu count 0": ("overhead", lambda m: m["cpu"].update(count=0)),
    "overhead cpu count as float": ("overhead", lambda m: m["cpu"].update(count=4.0)),
    "overhead negative cores": ("overhead", lambda m: m["cpu"].update(process_cores=-0.1)),
    "overhead bytes as float": ("overhead", lambda m: m["memory"].update(used_bytes=1.0)),
    "overhead negative bytes": ("overhead", lambda m: m["memory"].update(total_bytes=-1)),
    "overhead link without interface_name": ("overhead", lambda m: m.update(link=[{"role": "f1"}])),
    "overhead link not array": ("overhead", lambda m: m.update(link={"interface_name": "ens5"})),
    "overhead negative packets": ("overhead", lambda m: m["link"][0]["ingress"].update(sctp_packet_count=-1)),
    # alert (27_ §5)
    "alert fmt 2": ("alert", lambda m: m.update(fmt=2)),
    "alert missing fmt": ("alert", lambda m: m.pop("fmt")),
    "alert missing alert_id": ("alert", lambda m: m.pop("alert_id")),
    "alert empty alert_id": ("alert", lambda m: m.update(alert_id="")),
    "alert unknown event": ("alert", lambda m: m.update(event="resolve")),
    "alert stage 5": ("alert", lambda m: m.update(stage=5)),
    "alert stage as string": ("alert", lambda m: m.update(stage="1")),
    "alert bad kind": ("alert", lambda m: m.update(kind="warning")),
    "alert bad unit": ("alert", lambda m: m.update(unit="cells")),
    "alert t in ns": ("alert", lambda m: m.update(t=m["t"] * 1_000_000)),
    "alert t in seconds": ("alert", lambda m: m.update(t=m["t"] // 1000)),
    "alert t as float": ("alert", lambda m: m.update(t=float(m["t"]))),
    "alert cell as string": ("alert", lambda m: m.update(cell="1")),
    "alert cond not array": ("alert", lambda m: m.update(cond="C1")),
    "alert values not object": ("alert", lambda m: m.update(values=[1])),
    "alert ues entry missing uid": ("alert", lambda m: m.update(ues=[{"cell": 1, "du_ue_id": 2}])),
    "alert negative ues_total": ("alert", lambda m: m.update(ues_total=-1)),
    # evidence (27_ §6)
    "evidence bad phase": ("evidence", lambda m: m.update(phase="during")),
    "evidence missing raw": ("evidence", lambda m: m.pop("raw")),
    "evidence raw without type": ("evidence", lambda m: m["raw"].pop("type")),
    "evidence raw not object": ("evidence", lambda m: m.update(raw="{}")),
    "evidence ue of two": ("evidence", lambda m: m.update(ue=[1, 3])),
    "evidence seq as float": ("evidence", lambda m: m.update(seq=12.0)),
    # evidence.raw가 ue_evt(KPM1)일 때 타임라인에 쓰는 필드 (SCHEMA.md 3.7)
    "ue_evt missing t_ms": ("evidence", lambda m: m["raw"].pop("t_ms")),
    "ue_evt t_ms in ns": ("evidence", lambda m: m["raw"].update(t_ms=m["raw"]["t_ms"] * 1_000_000)),
    "ue_evt missing msg": ("evidence", lambda m: m["raw"].pop("msg")),
    "ue_evt empty msg": ("evidence", lambda m: m["raw"].update(msg="")),
    "ue_evt bad dir": ("evidence", lambda m: m["raw"].update(dir="up")),
    "ue_evt bad proto": ("evidence", lambda m: m["raw"].update(proto="rrc")),
    "ue_evt missing proto": ("evidence", lambda m: m["raw"].pop("proto")),
    "ue_evt cell_id as string": ("evidence", lambda m: m["raw"].update(cell_id="1")),
    "ue_evt missing du_ue_id": ("evidence", lambda m: m["raw"].pop("du_ue_id")),
    "ue_evt du_ue_id as string": ("evidence", lambda m: m["raw"].update(du_ue_id="3")),
    # gap
    "gap missing t_to": ("gap", lambda m: m.pop("t_to")),
    "gap t_from in ns": ("gap", lambda m: m.update(t_from=m["t_from"] * 1_000_000)),
    # kpm2 (27_ §4.1)
    "kpm2 without agg_ms (100 ms 원본)": ("kpm2", lambda m: m.pop("agg_ms")),
    "kpm2 ver 2": ("kpm2", lambda m: m.update(ver=2)),
    "kpm2 missing n": ("kpm2", lambda m: m.pop("n")),
    "kpm2 counter as string": ("kpm2", lambda m: m["cc"].update({"RRC.RelWithoutSuspendConfig": "0"})),
    "kpm2 sub counter as string": ("kpm2", lambda m: m["cc"]["RRC.ConnEstabAtt"].update(total="21")),
    "kpm2 nested too deep": ("kpm2", lambda m: m["cc"]["RRC.ConnEstabAtt"].update(total={"x": 1})),
    "kpm2 cell_id as string": ("kpm2", lambda m: m.update(cell_id="1")),
    "kpm2 agg_ms zero": ("kpm2", lambda m: m.update(agg_ms=0)),
    # hello·f1_evt
    "hello missing session": ("hello", lambda m: m.pop("session")),
    "hello ue_evt as string": ("hello", lambda m: m.update(ue_evt="true")),
    "f1_evt missing t_ms": ("f1_evt", lambda m: m.pop("t_ms")),
    "f1_evt cells as string": ("f1_evt", lambda m: m.update(cells="1")),
    # 상시로 보내지 않는 원본 줄 (27_ §4.2)
    "ue_evt standalone": ("evidence", lambda m: m.update(m.pop("raw"))),  # evidence를 벗긴 원본 ue_evt 한 줄
}


@pytest.mark.parametrize("case", INVALID.keys())
def test_invalid_messages_are_rejected(case):
    msg_type, mutate = INVALID[case]
    msg = ["not", "an", "object"] if msg_type is None else mutated(msg_type, mutate)
    assert not is_valid(msg)
    assert validation_errors(msg)


def test_error_message_points_to_field():
    errors = validation_errors(mutated("alert", lambda m: m.update(event="resolve")))
    assert any("event" in e for e in errors), errors
