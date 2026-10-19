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


@pytest.mark.parametrize("doc", ["schema/SCHEMA.md", "CLAUDE.md"])
def test_doc_examples_cover_all_types_and_pass(doc):
    examples = doc_examples(REPO_ROOT / doc)
    assert sorted(m["type"] for m in examples) == ["attack_run", "detection", "metric", "overhead"]
    for msg in examples:
        assert validation_errors(msg) == [], msg


EXAMPLES = {m["type"]: m for m in doc_examples(REPO_ROOT / "schema" / "SCHEMA.md")}


def mutated(msg_type, mutate):
    msg = copy.deepcopy(EXAMPLES[msg_type])
    mutate(msg)
    return msg


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
