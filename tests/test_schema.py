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


ALL_TYPES = ["alert", "attack_run", "detection", "evidence", "f1_evt", "gap", "hello", "kpm2", "metric", "overhead"]
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


@pytest.mark.parametrize("path", DETECTION_SAMPLES, ids=lambda p: p.stem)
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


def test_optional_fields_can_be_omitted():
    assert is_valid(mutated("metric", lambda m: m.pop("labels")))
    assert is_valid(mutated("metric", lambda m: m.update(labels={})))
    assert is_valid(mutated("detection", lambda m: m.update(target={"node": "du"})))
    assert is_valid(mutated("attack_run", lambda m: m.update(params={})))
    assert is_valid(mutated("metric", lambda m: m.update(unit="")))
    assert is_valid(mutated("overhead", lambda m: m.update(cpu_pct=250.0)))  # 멀티코어 합산


INVALID = {
    # 공통
    "no type": ("metric", lambda m: m.pop("type")),
    "unknown type": ("metric", lambda m: m.update(type="log")),
    "not an object": (None, None),
    # 시각
    "ts in seconds": ("metric", lambda m: m.update(ts=1763280000)),
    "ts in ms": ("metric", lambda m: m.update(ts=1763280000123)),
    "ts as float": ("metric", lambda m: m.update(ts=1763280000123456789.0)),
    "ts as string": ("metric", lambda m: m.update(ts="1763280000123456789")),
    "negative ts": ("overhead", lambda m: m.update(ts=-1)),
    "ts as bool": ("overhead", lambda m: m.update(ts=True)),
    # 숫자
    "value NaN": ("metric", lambda m: m.update(value=float("nan"))),
    "value Infinity": ("metric", lambda m: m.update(value=float("inf"))),
    "value as bool": ("metric", lambda m: m.update(value=True)),
    # metric
    "metric bad src": ("metric", lambda m: m.update(src="snmp")),
    "metric bad node": ("metric", lambda m: m.update(node="ru")),
    "metric bad kind": ("metric", lambda m: m.update(kind="custom")),
    "metric missing value": ("metric", lambda m: m.pop("value")),
    "metric missing unit": ("metric", lambda m: m.pop("unit")),
    "metric value as string": ("metric", lambda m: m.update(value="120")),
    "metric name with space": ("metric", lambda m: m.update(name="rrc setup")),
    "metric empty name": ("metric", lambda m: m.update(name="")),
    "metric unknown field": ("metric", lambda m: m.update(extra=1)),
    "metric unknown label": ("metric", lambda m: m["labels"].update(rnti="17921")),
    "metric numeric cell": ("metric", lambda m: m["labels"].update(cell=1)),
    # detection
    "detection bad severity": ("detection", lambda m: m.update(severity="fatal")),
    "detection bad ruleset": ("detection", lambda m: m.update(ruleset="ekpm_only")),
    "detection unknown attack_type": ("detection", lambda m: m.update(attack_type="RRC_STORM")),
    "detection typo field": ("detection", lambda m: m.update(ts_detect=m.pop("ts_detected"))),
    "detection empty evidence": ("detection", lambda m: m.update(evidence=[])),
    "detection evidence bad op": ("detection", lambda m: m["evidence"][0].update(op="gt")),
    "detection evidence missing threshold": ("detection", lambda m: m["evidence"][0].pop("threshold")),
    "detection evidence float window": ("detection", lambda m: m["evidence"][0].update(window_ms=1000.5)),
    "detection target missing node": ("detection", lambda m: m["target"].pop("node")),
    "detection target ue not array": ("detection", lambda m: m["target"].update(ue="0x4601")),
    "detection empty event_id": ("detection", lambda m: m.update(event_id="")),
    # attack_run
    "attack_run bad scenario": ("attack_run", lambda m: m.update(scenario="mixed")),
    "attack_run missing ts_end": ("attack_run", lambda m: m.pop("ts_end")),
    "attack_run missing params": ("attack_run", lambda m: m.pop("params")),
    # overhead
    "overhead ebpf_on as string": ("overhead", lambda m: m.update(ebpf_on="true")),
    "overhead negative cpu": ("overhead", lambda m: m.update(cpu_pct=-1)),
    "overhead missing mem": ("overhead", lambda m: m.pop("mem_mb")),
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
    errors = validation_errors(mutated("detection", lambda m: m.update(severity="fatal")))
    assert any("severity" in e for e in errors), errors
