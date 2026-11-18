#!/usr/bin/env python3
"""Claude Code 작업 기록 — hook 이벤트를 `logs/agent/<세션 ID>.jsonl`에 한 줄씩 남기고, 다시 읽어 보여 준다.

기록 (.claude/settings.json의 hook이 인자 없이 부른다. stdin = hook 입력 JSON):
    python3 .claude/hooks/agent_log.py

보기 (세션 = 세션 ID 앞부분. 생략하면 마지막 세션):
    python3 .claude/hooks/agent_log.py list                 # 세션 목록
    python3 .claude/hooks/agent_log.py show [세션] [--full]  # 프롬프트 → 도구 호출 → 결과 타임라인
    python3 .claude/hooks/agent_log.py errors [세션]         # 실패한 도구 호출, 그 직전 프롬프트와 입력·오류

원칙
- hook은 Claude 작업을 막지 않는다. 어떤 오류든 삼키고 exit 0. stdout에는 아무것도 쓰지 않는다
  (UserPromptSubmit·SessionStart hook의 stdout은 Claude 컨텍스트에 들어간다). 예외 하나: SessionStart에서 아래 켬·끔 설정
  가운데 기본값과 다른 것이 있으면 그 사실을 한 줄씩 쓴다. 기록기 자체 오류는 `_hook_errors.log`로.
- 켬·끔(D207·D208): `PORTRAN_AGENT_LOG`(작업 기록, 기본 켬), `PORTRAN_ROLE_WORKFLOW`(역할 분리, 기본 꺼짐) — 각자
  `.claude/settings.local.json`의 `env`에 `"off"`·`"on"`(`switch_on`).
- 비밀 값은 쓰기 전에 가린다: `.env`의 비밀 값, 토큰·비밀번호 이름의 KEY=VALUE, Slack Webhook, 개인 키, AWS·GitHub·Slack·Anthropic 키,
  Authorization 헤더. 비밀 파일(.env, *.pem 등)을 읽고 쓴 내용은 통째로 가린다.
- 긴 문자열은 앞·뒤만 남긴다(오류 메시지는 보통 끝에 있어 뒤를 더 남긴다). 전체는 SessionStart 줄의 `transcript_path`에 있다
  (Claude Code가 cleanupPeriodDays(기본 30일) 뒤 지우므로, 오래 남길 것은 이 기록이다).
- 표준 라이브러리만 쓴다(.venv 없이도 돈다). Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# ── 설정 ─────────────────────────────────────────────────────────────────────


def _env_int(name: str, default: int) -> int:
    try:
        return max(200, int(os.environ.get(name, default)))
    except ValueError:
        return default


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def log_dir() -> Path:
    return Path(os.environ.get("AGENT_LOG_DIR") or project_dir() / "logs" / "agent")


def max_chars() -> int:
    return _env_int("AGENT_LOG_MAX_CHARS", 4000)


# ── 켜기·끄기 (사용자 요청 11/18, D207·D208) ─────────────────────────────────
# 작업 기록은 기본 켬, 역할 분리 워크플로우는 기본 꺼짐(D208 — 사용자가 요청할 때만 켬).
# 바꾸려면 각자 PC의 .claude/settings.local.json(git 제외)에
#   {"env": {"PORTRAN_AGENT_LOG": "off", "PORTRAN_ROLE_WORKFLOW": "on"}}
# 다음 세션부터 적용된다. Claude Code가 그 env를 hook에도 넘기지만, 넘기지 않는 경우에도 같게 파일을 직접 읽는다.
LOG_SWITCH = "PORTRAN_AGENT_LOG"           # 작업 기록(이 기록기와 가드의 GuardDenied 줄)
WORKFLOW_SWITCH = "PORTRAN_ROLE_WORKFLOW"  # 역할 분리 워크플로우(CLAUDE.md 12절 10항) — 켜면 세션 시작 때 Claude에게 알린다
DEFAULTS = {LOG_SWITCH: True, WORKFLOW_SWITCH: False}
OFF_VALUES = {"off", "0", "false", "no", "끔", "꺼짐"}
ON_VALUES = {"on", "1", "true", "yes", "켬", "켜짐"}


def switch_on(name: str) -> bool:
    """켬·끔 설정. 환경변수가 먼저, 없으면 .claude/settings.local.json의 env, 둘 다 없거나 알 수 없는 값이면 기본값."""
    value = os.environ.get(name)
    if value is None:
        try:
            local = json.loads((project_dir() / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
            value = (local.get("env") or {}).get(name)
        except Exception:
            value = None
    text = str(value).strip().lower() if value is not None else ""
    if text in OFF_VALUES:
        return False
    if text in ON_VALUES:
        return True
    return DEFAULTS.get(name, True)


def session_notice() -> str:
    """세션 시작 때 Claude 컨텍스트에 넣을 글(SessionStart hook의 stdout). 기본값과 다른 설정만 알린다 — 기본이면 빈 글."""
    lines = []
    if switch_on(WORKFLOW_SWITCH):
        lines.append(f"역할 분리 워크플로우가 켜져 있다({WORKFLOW_SWITCH}=on): CLAUDE.md 12절 10항대로 작업 크기에 맞춰 "
                     "researcher·planner·reviewer 서브에이전트를 쓴다.")
    if not switch_on(LOG_SWITCH):
        lines.append(f"작업 기록 hook이 꺼져 있다({LOG_SWITCH}=off): 이 세션은 logs/agent/에 기록되지 않는다 "
                     "(agent_log.py errors·show로 이 세션을 볼 수 없다). 읽기 전용 가드는 그대로 돈다.")
    return "\n".join(f"[PortRAN 설정] {line}" for line in lines)


# ── 비밀 값 가리기 ───────────────────────────────────────────────────────────

MASK = "***"
SECRET_NAME = re.compile(r"TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|ACCESS_KEY|PRIVATE_KEY|WEBHOOK_URL|CREDENTIAL")

# (패턴, 바꿀 문자열). 순서대로 적용한다.
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 개인 키 블록 (끝 표시가 잘렸어도 끝까지)
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[개인 키 가림]"),
    (re.compile(r"\bhooks\.slack\.com/services/[\w/-]+"), "hooks.slack.com/services/" + MASK),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),          # AWS access key ID
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), MASK),             # GitHub 토큰
    (re.compile(r"\bxox[abprs]-[\w-]{10,}"), MASK),                  # Slack 토큰
    (re.compile(r"\bsk-ant-[\w-]{10,}"), MASK),                      # Anthropic API 키
    (re.compile(r"(?i)(authorization(?:\\?[\"'])?\s*[:=]\s*(?:\\?[\"'])?(?:token|bearer|basic)\s+(?:\\?[\"'])?)[^\s\"'\\]+"), r"\1" + MASK),
]
# 값: 이스케이프된 따옴표 값(\"…\", sh -c "… \"값\" …" 안), 따옴표 값(공백 포함), 따옴표 없는 값
# 닫는 따옴표가 같은 줄에 없으면 줄 끝까지를 값으로 본다
_VALUE = (r"(\\\"(?:[^\"\\\n]|\\[^\"])*\\\"|\\'[^'\n]*\\'|\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*'"
          r"|\"[^\"\n]+|'[^'\n]+|[^\s\"'\\]+)")
# 명령줄 옵션: --password=…, --token "…", curl -u 사용자:비밀번호 / --user=사용자:비밀번호 / -u사용자:비밀번호
SECRET_OPTIONS = [
    re.compile(r"(?i)(--(?:password|passwd|token|secret|api-key)(?:=|[ \t]+))" + _VALUE),
    re.compile(r"((?:^|\s)(?:-u[ \t]*|--user(?:=|[ \t]+))(?:\\?[\"'])?[^\s:\"'\\]+:)" + _VALUE),
]

# PASSWORD=…, INFLUX_TOKEN="a b", "GRAFANA_ADMIN_PASSWORD": "…", SLACK_WEBHOOK_URL: … (이름은 대문자 환경변수 형태만)
# 남기는 값: ${...}·$VAR(compose 참조), 함수 호출·첨자 같은 코드(`os.environ.get(`), 이미 가린 값.
# 줄바꿈은 넘지 않는다(빈 값 다음 줄을 가리지 않게). `==`는 대입이 아니다.
ENV_ASSIGN = re.compile(
    r"\b([A-Z0-9_]*(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|ACCESS_KEY|PRIVATE_KEY|WEBHOOK_URL|CREDENTIAL)[A-Z0-9_]*)"
    r"((?:\\?[\"'])?[ \t]*[=:](?!=)[ \t]*)" + _VALUE
)
CODE_VALUE = re.compile(r"^[A-Za-z_][\w.]*[(\[]")


def _mask_value(value: str) -> str:
    """따옴표는 두고 안쪽만 가린다. ${…}·$VAR 참조, 코드(함수 호출·첨자), 이미 가린 값은 그대로."""
    quote = value[:2] if value[:2] in ("\\\"", "\\'") else value[:1] if value[:1] in ("'", '"') else ""
    inner = value[len(quote):-len(quote)] if quote else value
    if quote and not value.endswith(quote):  # 닫는 따옴표가 없는 조각(-u "user:pw")
        quote, inner = "", value
    if not inner or inner.startswith("$") or inner.strip(quote) == MASK or (not quote and CODE_VALUE.match(inner)):
        return value
    return f"{quote}{MASK}{quote}"


def _mask_assign(m: re.Match[str]) -> str:
    return f"{m.group(1)}{m.group(2)}{_mask_value(m.group(3))}"


def _mask_option(m: re.Match[str]) -> str:
    return f"{m.group(1)}{_mask_value(m.group(2))}"


MIN_SECRET_LEN = 3      # 이보다 짧은 .env 값은 KEY=VALUE 형태일 때만 가린다
SHORT_SECRET_LEN = 6    # 이보다 짧은 값은 낱말 단위로만 가린다(다른 낱말 속 글자를 지우지 않게)


def env_secret_values(root: Path) -> list[str]:
    """`.env`에서 비밀 이름(TOKEN·PASSWORD·WEBHOOK_URL 등)인 값. 명령·출력 어디에 나와도 가린다. 긴 것부터."""
    try:
        text = (root / ".env").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    values = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip("\"'")
        if SECRET_NAME.search(key) and len(value) >= MIN_SECRET_LEN:
            values.add(value)
    return sorted(values, key=len, reverse=True)


def redact(text: str, secret_values: Iterable[str] = ()) -> str:
    for value in secret_values:
        if len(value) >= SHORT_SECRET_LEN:
            text = text.replace(value, MASK)
        else:  # 짧은 값(예: 4자 비밀번호)은 앞뒤가 ASCII 낱말 글자가 아닐 때만 — '<값>로'처럼 한글 조사가 붙어도 가린다
            text = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", MASK, text)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    for pattern in SECRET_OPTIONS:
        text = pattern.sub(_mask_option, text)
    return ENV_ASSIGN.sub(_mask_assign, text)


def is_secret_file(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if name in (".env", ".credentials.json", "credentials.json"):
        return True
    if name.startswith(".env.") and not name.endswith((".example", ".sample", ".template")):
        return True
    return name.endswith((".pem", ".key", ".p12", ".pfx"))


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 5
    tail = limit - head
    return f"{text[:head]}\n…[{len(text) - limit}자 생략]…\n{text[-tail:]}"


def clean(obj: Any, secret_values: list[str], limit: int) -> Any:
    if isinstance(obj, str):
        return truncate(redact(obj, secret_values), limit)
    if isinstance(obj, dict):
        return {str(k): clean(v, secret_values, limit) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v, secret_values, limit) for v in obj]
    return obj


# ── 기록 ─────────────────────────────────────────────────────────────────────

TOOL_RESULT_EVENTS = {"PostToolUse", "PostToolUseFailure"}
GUARD_EVENT = "GuardDenied"  # readonly_guard.py가 막은 호출
# 파일 내용이 들어가는 tool_input 키 — 비밀 파일이면 가린다
CONTENT_KEYS = ("content", "old_string", "new_string", "edits", "new_source")


def build_record(payload: dict[str, Any], now: str, secret_values: list[str], limit: int) -> dict[str, Any]:
    event = str(payload.get("hook_event_name") or "unknown")
    rec: dict[str, Any] = {"ts": now, "event": event}
    for key, value in payload.items():
        if key == "hook_event_name":
            continue
        if key in ("ts", "event"):  # 기록기가 붙인 값을 덮어쓰지 않게
            key = "payload_" + key
        # 전체 대화 파일 경로는 세션 시작·끝에만(줄마다 같은 값)
        if key == "transcript_path" and event not in ("SessionStart", "SessionEnd"):
            continue
        # 결과 줄에는 입력을 다시 쓰지 않는다 — 같은 tool_use_id의 PreToolUse 줄에 있다
        if key == "tool_input" and event in TOOL_RESULT_EVENTS and payload.get("tool_use_id"):
            continue
        rec[key] = value

    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path") or tool_input.get("notebook_path") if isinstance(tool_input, dict) else None
    if isinstance(path, str) and is_secret_file(path):
        if isinstance(rec.get("tool_input"), dict):
            rec["tool_input"] = {k: ("[비밀 파일 내용 가림]" if k in CONTENT_KEYS else v) for k, v in rec["tool_input"].items()}
        if "tool_response" in rec:
            rec["tool_response"] = "[비밀 파일 내용 가림]"
    try:
        return clean(rec, secret_values, limit)
    except RecursionError:  # 비정상적으로 깊게 중첩된 입력 — 내용 없이 이벤트만 남긴다
        return {"ts": now, "event": event, "session_id": str(payload.get("session_id", "")),
                "note": "입력이 너무 깊게 중첩돼 내용을 남기지 않음"}


def session_file(session_id: Any) -> Path:
    safe = re.sub(r"[^\w-]", "_", str(session_id or "unknown"))[:100] or "unknown"
    return log_dir() / f"{safe}.jsonl"


def append_line(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8", errors="backslashreplace") as f:
        try:  # 병렬 도구 호출의 hook이 동시에 쓸 수 있다
            import fcntl

            fcntl.flock(f, fcntl.LOCK_EX)
        except Exception:
            pass
        f.write(line)


def record(stdin=None, stdout=None) -> int:
    """hook 진입점. 무슨 일이 있어도 0을 돌려준다. SessionStart에서 기본값과 다른 설정이 있으면 그 사실만 stdout에 쓴다
    (Claude 컨텍스트에 들어감) — 그 밖에는 stdout에 아무것도 쓰지 않는다."""
    try:
        raw = (stdin or sys.stdin).read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            payload = {"hook_event_name": "unparsed", "raw": raw}
        if payload.get("hook_event_name") == "SessionStart":
            notice = session_notice()
            if notice:
                print(notice, file=stdout or sys.stdout)
        if not switch_on(LOG_SWITCH):
            return 0
        now = datetime.now().astimezone().isoformat(timespec="milliseconds")
        rec = build_record(payload, now, env_secret_values(project_dir()), max_chars())
        append_line(session_file(payload.get("session_id")), rec)
    except Exception:
        try:
            d = log_dir()
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "_hook_errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} {traceback.format_exc()}\n")
        except Exception:
            pass
    return 0


# ── 보기 ─────────────────────────────────────────────────────────────────────


def read_session(path: Path) -> list[dict[str, Any]]:
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def session_files() -> list[Path]:
    d = log_dir()
    if not d.is_dir():
        return []
    return sorted((p for p in d.glob("*.jsonl")), key=lambda p: p.stat().st_mtime)


def find_session(query: str | None) -> Path:
    files = session_files()
    if not files:
        raise SystemExit(f"기록이 없다: {log_dir()}")
    if not query or query == "latest":
        return files[-1]
    hits = [p for p in files if p.stem.startswith(query)]
    if not hits:
        raise SystemExit(f"'{query}'로 시작하는 세션이 없다. `list`로 확인")
    if len(hits) > 1:
        raise SystemExit(f"'{query}'로 시작하는 세션이 {len(hits)}개다: " + ", ".join(p.stem[:12] for p in hits))
    return hits[0]


def text_of(value: Any) -> str:
    """도구 결과·오류에서 사람이 읽을 글만 모은다."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("error", "stderr", "message", "text", "result", "content", "stdout", "output"):
            if value.get(key):
                return text_of(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(t for t in (text_of(v) for v in value) if t)
    return str(value)


def one_line(text: str, width: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def rel(path: str) -> str:
    root = str(project_dir()).rstrip("/") + "/"
    return path[len(root):] if path.startswith(root) else path


def summarize_input(tool: str, ti: Any) -> str:
    if not isinstance(ti, dict):
        return one_line(text_of(ti))
    if tool == "Bash":
        return one_line(ti.get("command", ""))
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        return rel(str(ti.get("file_path") or ti.get("notebook_path") or ""))
    if tool == "Grep":
        return one_line(f"{ti.get('pattern', '')}  ({ti.get('path') or ti.get('glob') or '.'})")
    if tool == "Glob":
        return one_line(str(ti.get("pattern", "")))
    if tool in ("Agent", "Task"):
        return one_line(f"[{ti.get('subagent_type') or 'general'}] {ti.get('description', '')}")
    if tool == "WebFetch":
        return one_line(str(ti.get("url", "")))
    if tool == "WebSearch":
        return one_line(str(ti.get("query", "")))
    return one_line(json.dumps(ti, ensure_ascii=False))


def who(rec: dict[str, Any]) -> str:
    if rec.get("agent_type"):
        return str(rec["agent_type"])
    if rec.get("agent_id"):
        return "sub:" + str(rec["agent_id"])[:6]
    return "main"


def _ts(rec: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(rec.get("ts")))
    except ValueError:
        return None


def _duration(pre: dict[str, Any], post: dict[str, Any]) -> str:
    ms = post.get("duration_ms")
    if not isinstance(ms, (int, float)):
        a, b = _ts(pre), _ts(post)
        if not (a and b):
            return "?"
        ms = (b - a).total_seconds() * 1000
    return f"{ms:.0f}ms" if ms < 1000 else f"{ms / 1000:.1f}s"


def is_failure(rec: dict[str, Any]) -> bool:
    if rec.get("event") == "PostToolUseFailure":
        return True
    resp = rec.get("tool_response")
    return isinstance(resp, dict) and (resp.get("is_error") is True or resp.get("interrupted") is True)


FAILURE_EVENTS = ("PermissionDenied", "StopFailure", GUARD_EVENT)


def is_notification(prompt: str) -> bool:
    """백그라운드 작업 완료 알림 — 사용자가 친 프롬프트가 아니다."""
    return prompt.lstrip().startswith("<task-notification>")


def unanswered_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """결과(PostToolUse·Failure)도 가드 차단·PermissionDenied도 없는 PreToolUse — 권한 거부·중단(또는 아직 실행 중)."""
    seen = {str(r.get("tool_use_id")) for r in records
            if r.get("tool_use_id") and (r.get("event") in TOOL_RESULT_EVENTS or r.get("event") in FAILURE_EVENTS)}
    return [r for r in records if r.get("event") == "PreToolUse" and str(r.get("tool_use_id")) not in seen]


def results_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["tool_use_id"]): r for r in records if r.get("event") in TOOL_RESULT_EVENTS and r.get("tool_use_id")}


def show(records: list[dict[str, Any]], full: bool = False, out=None) -> None:
    out = out or sys.stdout
    results = results_by_id(records)
    pre_ids = {str(r.get("tool_use_id")) for r in records if r.get("event") == "PreToolUse"}

    def emit(rec: dict[str, Any], text: str) -> None:
        print(f"{str(rec.get('ts', ''))[11:19]} {who(rec):>10} │ {text}", file=out)

    def detail(text: str) -> None:
        if full and text:
            for line in text.splitlines():
                print(f"{'':>19} │     {line}", file=out)

    for rec in records:
        ev = rec.get("event")
        tool = str(rec.get("tool_name", ""))
        if ev == "SessionStart":
            emit(rec, f"══ 세션 시작 ({rec.get('source', '')}) {rec.get('model', '')}".rstrip())
            if rec.get("transcript_path"):
                emit(rec, f"   전체 대화: {rec['transcript_path']}")
        elif ev == "UserPromptSubmit":
            prompt = str(rec.get("prompt", ""))
            mark = "🔔 " if is_notification(prompt) else "👤 "
            emit(rec, mark + (prompt if full else one_line(prompt, 200)))
        elif ev == "PreToolUse":
            post = results.get(str(rec.get("tool_use_id")))
            if post is None:
                status = "… 결과 없음(중단·거부)"
            elif is_failure(post):
                status = f"✗ {_duration(rec, post)}  {one_line(text_of(post.get('error') or post.get('tool_response')), 120)}"
            else:
                status = f"✓ {_duration(rec, post)}"
            emit(rec, f"▶ {tool}: {summarize_input(tool, rec.get('tool_input'))}  → {status}")
            if full:
                detail(json.dumps(rec.get("tool_input"), ensure_ascii=False, indent=2))
                if post is not None:
                    detail(text_of(post.get("error") or post.get("tool_response")))
            elif post is not None and tool in ("Agent", "Task"):
                resp = post.get("tool_response")
                if isinstance(resp, dict) and resp.get("status") == "async_launched":
                    emit(post, f"   ↳ 백그라운드로 시작 (agent {resp.get('agentId', '')}) — 결과는 '서브에이전트 끝' 줄")
                else:
                    emit(post, "   ↳ " + one_line(text_of(resp), 200))
        elif ev in TOOL_RESULT_EVENTS:
            if str(rec.get("tool_use_id")) not in pre_ids:  # 짝 없는 결과만 따로 보인다
                mark = "✗" if is_failure(rec) else "✓"
                emit(rec, f"{mark} {tool}: {one_line(text_of(rec.get('error') or rec.get('tool_response')), 160)}")
        elif ev == GUARD_EVENT:
            emit(rec, f"⛔ 읽기 전용 차단 {tool}: {summarize_input(tool, rec.get('tool_input'))}  ({rec.get('reason', '')})")
        elif ev == "PermissionDenied":
            emit(rec, f"⛔ 권한 거부 {tool}: {summarize_input(tool, rec.get('tool_input'))}")
        elif ev == "SubagentStart":
            emit(rec, f"┌ 서브에이전트 시작 [{rec.get('agent_type', '')}]")
        elif ev == "SubagentStop":
            msg = rec.get("last_assistant_message")
            emit(rec, f"└ 서브에이전트 끝 [{rec.get('agent_type', '')}]" + (f"  {one_line(str(msg), 160)}" if msg else ""))
        elif ev == "Stop":
            msg = rec.get("last_assistant_message")
            emit(rec, "■ 응답 끝" + (f"  {one_line(str(msg), 160)}" if msg and not full else ""))
            if msg and full:
                detail(str(msg))
        elif ev == "StopFailure":
            emit(rec, f"✗ 응답 실패: {one_line(text_of(rec.get('error') or rec), 200)}")
        elif ev == "PreCompact":
            emit(rec, f"… 대화 요약(compact, {rec.get('trigger', '')})")
        elif ev == "SessionEnd":
            emit(rec, f"══ 세션 끝 ({rec.get('reason', '')})")
        else:
            emit(rec, f"· {ev}")


def errors(records: list[dict[str, Any]], out=None) -> int:
    """실패한 도구 호출마다 직전 프롬프트·누가·입력·오류를 보인다. 실패 개수를 돌려준다."""
    out = out or sys.stdout
    pre = {str(r["tool_use_id"]): r for r in records if r.get("event") == "PreToolUse" and r.get("tool_use_id")}
    prompts = {}  # prompt_id → 그 호출을 낳은 사용자 프롬프트 (서브에이전트 호출도 같은 prompt_id)
    unanswered = {id(r) for r in unanswered_calls(records)}
    last_prompt = ""
    count = 0
    for rec in records:
        ev = rec.get("event")
        if ev == "UserPromptSubmit":
            prompt = str(rec.get("prompt", ""))
            if not is_notification(prompt):
                last_prompt = prompt
                if rec.get("prompt_id"):
                    prompts[str(rec["prompt_id"])] = prompt
            continue
        failed = (ev in TOOL_RESULT_EVENTS and is_failure(rec)) or ev in FAILURE_EVENTS
        if ev == "PreToolUse" and id(rec) in unanswered:
            failed, ev = True, "결과 없음(권한 거부·중단, 또는 아직 실행 중)"
        if not failed:
            continue
        count += 1
        tool = str(rec.get("tool_name", ""))
        call = pre.get(str(rec.get("tool_use_id")), rec)
        prompt = prompts.get(str(rec.get("prompt_id")), last_prompt)
        print(f"── 실패 {count}: {str(rec.get('ts', ''))[:19]}  {ev}  {tool}  ({who(rec)})", file=out)
        print(f"   프롬프트: {one_line(prompt, 200) or '(없음)'}", file=out)
        if call.get("tool_input") is not None:
            print("   입력:", file=out)
            for line in json.dumps(call.get("tool_input"), ensure_ascii=False, indent=2).splitlines():
                print("     " + line, file=out)
        print("   오류:", file=out)
        for line in (text_of(rec.get("error") or rec.get("tool_response") or rec.get("reason")) or "(내용 없음)").splitlines():
            print("     " + line, file=out)
        print(file=out)
    if count == 0:
        print("실패·차단·결과 없는 도구 호출이 없다.", file=out)
    return count


def list_sessions(out=None) -> None:
    out = out or sys.stdout
    files = session_files()
    if not files:
        print(f"기록이 없다: {log_dir()}", file=out)
        return
    print(f"{'시작':<19}  {'세션':<8}  {'프롬프트':>4}  {'도구':>4}  {'실패':>4}  {'서브':>4}  첫 프롬프트", file=out)
    for path in files:
        recs = read_session(path)
        if not recs:
            continue
        prompts = [r for r in recs if r.get("event") == "UserPromptSubmit" and not is_notification(str(r.get("prompt", "")))]
        calls = sum(1 for r in recs if r.get("event") == "PreToolUse")
        fails = sum(1 for r in recs if (r.get("event") in TOOL_RESULT_EVENTS and is_failure(r)) or r.get("event") in FAILURE_EVENTS)
        fails += len(unanswered_calls(recs))
        subs = sum(1 for r in recs if r.get("event") == "SubagentStart")
        first = one_line(str(prompts[0].get("prompt", "")), 50) if prompts else ""
        print(f"{str(recs[0].get('ts', ''))[:19]:<19}  {path.stem[:8]:<8}  {len(prompts):>4}  {calls:>4}  {fails:>4}  {subs:>4}  {first}",
              file=out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return record()
    parser = argparse.ArgumentParser(prog="agent_log.py", description="Claude Code 작업 기록 보기")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="세션 목록")
    p_show = sub.add_parser("show", help="타임라인")
    p_show.add_argument("session", nargs="?", help="세션 ID 앞부분 (생략: 마지막 세션)")
    p_show.add_argument("--full", action="store_true", help="입력·결과 전체")
    p_err = sub.add_parser("errors", help="실패한 도구 호출")
    p_err.add_argument("session", nargs="?", help="세션 ID 앞부분 (생략: 마지막 세션)")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        list_sessions()
    elif args.cmd == "show":
        show(read_session(find_session(args.session)), full=args.full)
    elif args.cmd == "errors":
        errors(read_session(find_session(args.session)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
