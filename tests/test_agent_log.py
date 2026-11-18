"""Claude Code 작업 기록 hook(.claude/hooks/agent_log.py)과 읽기 전용 가드(readonly_guard.py).

hook은 Claude 작업을 막으면 안 되고(늘 exit 0, stdout 없음), 비밀 값이 기록에 남으면 안 된다.
가드는 읽기 전용 역할(researcher·planner·reviewer)의 Bash만 막고 메인 에이전트·다른 역할은 건드리지 않는다.
"""
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))
agent_log = importlib.import_module("agent_log")
readonly_guard = importlib.import_module("readonly_guard")


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("INFLUX_TOKEN=local-dev-token-123\nINFLUX_ORG=portran\nINFLUX_ADMIN_PASSWORD=abcd\n"
                                  "GRAFANA_ADMIN_PASSWORD=pw\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("AGENT_LOG_DIR", str(tmp_path / "logs"))
    for name in (agent_log.LOG_SWITCH, agent_log.WORKFLOW_SWITCH):  # 이 PC의 켬·끔 설정과 무관하게
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "logs"


def feed(*payloads):
    for p in payloads:
        assert agent_log.record(io.StringIO(json.dumps(p, ensure_ascii=False))) == 0


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── 비밀 값 가리기 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, leaked", [
    ("INFLUX_TOKEN=abc123secret", "abc123secret"),
    ('{"GRAFANA_ADMIN_PASSWORD": "hunter22"}', "hunter22"),
    ("SLACK_WEBHOOK_URL: https://hooks.slack.com/services/T0/B0/XYZ", "T0/B0/XYZ"),
    ("curl https://hooks.slack.com/services/T1/B2/abc", "T1/B2/abc"),
    ('curl -H "Authorization: Token sekret999" localhost:8086', "sekret999"),
    ("-----BEGIN PRIVATE KEY-----\nMIIEvQ\n-----END PRIVATE KEY-----", "MIIEvQ"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEvQ (잘림)", "MIIEvQ"),
    ("key AKIAABCDEFGHIJKLMNOP", "AKIAABCDEFGHIJKLMNOP"),
    ("ghp_" + "a" * 36, "a" * 36),
    ("sk-ant-api03-abcdefghijkl", "abcdefghijkl"),
    # 키워드만 있는 이름, 따옴표 안 공백, 명령줄 옵션 (11/18 Reviewer 지적)
    ("PASSWORD=hunter2222", "hunter2222"),
    ("SECRET_KEY=topsecret99", "topsecret99"),
    ("TOKEN=abc123", "abc123"),
    ('INFLUX_TOKEN="abc def ghi"', "def ghi"),
    ("grafana cli admin reset-admin-password --password=s3cr3t", "s3cr3t"),
    ("curl -u admin:pw12 localhost", "pw12"),
    # 따옴표 붙은 옵션 값, curl 사용자 형식, 스킴 없는 Webhook (11/18 Reviewer 2차 지적)
    ('--password "s3cr3t"', "s3cr3t"), ('--password="s3cr3t"', "s3cr3t"), ("--token 'abc123'", "abc123"),
    ('curl -u admin:"pw12"', "pw12"), ("curl --user=admin:pw12", "pw12"), ("curl -uadmin:pw12", "pw12"),
    ('curl -u "admin:pw12" x', "pw12"), ("hooks.slack.com/services/T1/B2/abc", "T1/B2/abc"),
    # 이스케이프된 따옴표 안 값 — sh -c "…", JSON 안의 JSON (11/18 Reviewer 3차 지적)
    ('INFLUX_TOKEN=\\"abc123zz\\"', "abc123zz"), ('--password \\"abc123zz\\"', "abc123zz"),
    ('{\\"GRAFANA_ADMIN_PASSWORD\\": \\"abc123zz\\"}', "abc123zz"), ('authorization=\\"Basic YWRtaW46cHc=\\"', "YWRtaW46"),
    ('{\\"Authorization\\": \\"Token abc123zz\\"}', "abc123zz"),
    ('sh -c "grafana cli admin reset-admin-password --password \\"abc123zz\\""', "abc123zz"),
    # 따옴표로 감싼 Authorization 값, 닫지 않은 따옴표, 값 속 이스케이프 (11/18 Reviewer 4차 지적)
    ('Authorization: Token "abc123zz"', "abc123zz"), ('INFLUX_TOKEN="abc123zz', "abc123zz"),
    ('{"INFLUX_TOKEN": "abc\\"123zz"}', "123zz"),
])
def test_redact_hides_secrets(text, leaked):
    assert leaked not in agent_log.redact(text)


def test_redact_keeps_compose_references_and_next_line():
    # compose의 ${...} 참조는 비밀이 아니다. 빈 값 다음 줄을 가리면 안 된다
    text = "SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL:-http://127.0.0.1:9/x}\nINFLUX_TOKEN=\nINFLUX_ORG=portran"
    assert agent_log.redact(text) == text


def test_redact_is_fast_on_large_input():
    import time
    for text in ["x" * 1_000_000, ('INFLUX_TOKEN=\\"' + "a" * 50_000) * 5, "--password " * 50_000]:
        start = time.perf_counter()
        agent_log.redact(text)
        assert time.perf_counter() - start < 2


def test_redact_keeps_code():
    # 코드를 가리면 기록을 다시 읽기 어렵다: 함수 호출·비교·속성은 비밀 값이 아니다
    for text in ['INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "")', "if TOKEN == other:", "token=s.token"]:
        assert agent_log.redact(text) == text


def test_redact_env_values_anywhere():
    assert agent_log.redact("influx -t local-dev-token-123 query", ["local-dev-token-123"]) == "influx -t *** query"


def test_redact_short_env_values_as_whole_words():
    # 4자 비밀번호도 명령 어디에 나오든 가리되, 다른 낱말 속 같은 글자는 지우지 않는다
    out = agent_log.redact('reset-admin-password "abcd" ; abcdef ; xabcd ; abcd_1 ; (abcd)', ["abcd"])
    assert out == 'reset-admin-password "***" ; abcdef ; xabcd ; abcd_1 ; (***)'
    # 한글 조사가 바로 붙어도 가린다 (11/18 Reviewer 2차 지적 — 유니코드 \w는 한글을 낱말 글자로 본다)
    assert agent_log.redact("비밀번호를 abcd로 맞췄다. abcd입니다", ["abcd"]) == "비밀번호를 ***로 맞췄다. ***입니다"


def test_env_secret_values_reads_only_secret_names(logdir, tmp_path):
    # 비밀 아닌 이름(INFLUX_ORG)과 3자 미만 값(pw)은 아무 데서나 가리면 기록이 망가진다 — pw는 KEY=VALUE로만 가린다
    assert agent_log.env_secret_values(tmp_path / "project") == ["local-dev-token-123", "abcd"]


@pytest.mark.parametrize("path, secret", [
    ("/repo/.env", True), ("/repo/.env.prod", True), ("/repo/.env.example", False),
    ("/mnt/c/portran/portran-ingest.pem", True), ("certs/ingest.key", True), ("collector/ingest.py", False),
])
def test_is_secret_file(path, secret):
    assert agent_log.is_secret_file(path) is secret


def test_truncate_keeps_head_and_tail():
    text = "HEAD" + "x" * 10_000 + "TAIL"
    out = agent_log.truncate(text, 1000)
    assert out.startswith("HEAD") and out.endswith("TAIL") and "자 생략" in out and len(out) < 1100


# ── 기록 ─────────────────────────────────────────────────────────────────────

def test_record_writes_one_line_per_event_per_session(logdir):
    feed(
        {"session_id": "s1", "hook_event_name": "SessionStart", "transcript_path": "/t.jsonl", "source": "startup"},
        {"session_id": "s1", "hook_event_name": "UserPromptSubmit", "prompt": "토큰 INFLUX_TOKEN=abc123secret", "prompt_id": "p1",
         "transcript_path": "/t.jsonl"},
        {"session_id": "s2", "hook_event_name": "SessionStart", "source": "resume"},
    )
    s1 = lines(logdir / "s1.jsonl")
    assert [r["event"] for r in s1] == ["SessionStart", "UserPromptSubmit"]
    assert s1[0]["transcript_path"] == "/t.jsonl" and "transcript_path" not in s1[1]  # 경로는 시작·끝에만
    assert "abc123secret" not in json.dumps(s1) and s1[1]["prompt_id"] == "p1"
    assert len(lines(logdir / "s2.jsonl")) == 1


def test_post_tool_drops_repeated_input_and_hides_secret_file(logdir):
    env_path = "/project/.env"
    feed(
        {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_use_id": "t1",
         "tool_input": {"file_path": env_path}},
        {"session_id": "s", "hook_event_name": "PostToolUse", "tool_name": "Read", "tool_use_id": "t1",
         "tool_input": {"file_path": env_path}, "tool_response": {"file": {"content": "ODD_NAME=plainvalue"}}},
        {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_use_id": "t2",
         "tool_input": {"file_path": env_path, "content": "ODD_NAME=plainvalue"}},
    )
    pre, post, write = lines(logdir / "s.jsonl")
    assert "tool_input" not in post  # PreToolUse 줄에 있다
    assert post["tool_response"] == "[비밀 파일 내용 가림]"
    assert write["tool_input"] == {"file_path": env_path, "content": "[비밀 파일 내용 가림]"}


def test_record_never_fails_and_prints_nothing(logdir):
    # stdout은 UserPromptSubmit·SessionStart에서 Claude 컨텍스트에 들어간다 → 늘 비어야 한다
    script = HOOKS / "agent_log.py"
    for stdin in ('{"session_id":"s","hook_event_name":"Stop"}', "not json", "[1,2]", ""):
        r = subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True, text=True, timeout=30)
        assert (r.returncode, r.stdout) == (0, "")
    assert [r["event"] for r in lines(logdir / "unknown.jsonl")] == ["unparsed"] * 3


# ── 켜기·끄기 (D207) ─────────────────────────────────────────────────────────

def local_settings(logdir, env):
    path = logdir.parent / "project" / ".claude" / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"env": env}), encoding="utf-8")


def test_switch_defaults_then_env_then_local_settings(logdir, monkeypatch):
    # 기본: 작업 기록 켬, 역할 분리 꺼짐(D208 — 사용자가 요청할 때만 켬)
    assert agent_log.switch_on(agent_log.LOG_SWITCH) and not agent_log.switch_on(agent_log.WORKFLOW_SWITCH)
    local_settings(logdir, {agent_log.LOG_SWITCH: "off", agent_log.WORKFLOW_SWITCH: "켬"})
    assert not agent_log.switch_on(agent_log.LOG_SWITCH) and agent_log.switch_on(agent_log.WORKFLOW_SWITCH)
    monkeypatch.setenv(agent_log.LOG_SWITCH, "on")  # 환경변수가 파일보다 먼저
    assert agent_log.switch_on(agent_log.LOG_SWITCH)
    for value in ("OFF", "0", "false", "No", "꺼짐"):
        monkeypatch.setenv(agent_log.LOG_SWITCH, value)
        assert not agent_log.switch_on(agent_log.LOG_SWITCH), value
    for value in ("ON", "1", "true", "Yes", "켜짐"):
        monkeypatch.setenv(agent_log.WORKFLOW_SWITCH, value)
        assert agent_log.switch_on(agent_log.WORKFLOW_SWITCH), value
    monkeypatch.setenv(agent_log.WORKFLOW_SWITCH, "모름")  # 알 수 없는 값은 기본값
    assert not agent_log.switch_on(agent_log.WORKFLOW_SWITCH)
    monkeypatch.delenv(agent_log.LOG_SWITCH)
    monkeypatch.delenv(agent_log.WORKFLOW_SWITCH)
    (logdir.parent / "project" / ".claude" / "settings.local.json").write_text("{깨진 JSON", encoding="utf-8")
    assert agent_log.switch_on(agent_log.LOG_SWITCH) and not agent_log.switch_on(agent_log.WORKFLOW_SWITCH)  # 못 읽으면 기본값


def test_log_off_writes_nothing(logdir):
    local_settings(logdir, {agent_log.LOG_SWITCH: "off"})
    feed({"session_id": "s", "hook_event_name": "UserPromptSubmit", "prompt": "안녕"},
         {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert not logdir.exists() or not any(logdir.iterdir())


def test_session_start_tells_claude_what_differs_from_default(logdir):
    # 기본값(기록 켬, 역할 분리 꺼짐)이면 아무것도 안 쓴다(다른 이벤트도 늘 빈 stdout — test_record_never_fails_and_prints_nothing)
    out = io.StringIO()
    agent_log.record(io.StringIO('{"session_id":"s","hook_event_name":"SessionStart"}'), out)
    assert out.getvalue() == ""
    local_settings(logdir, {agent_log.WORKFLOW_SWITCH: "on", agent_log.LOG_SWITCH: "off"})
    script = HOOKS / "agent_log.py"
    for event in ("SessionStart", "UserPromptSubmit", "Stop"):
        r = subprocess.run([sys.executable, str(script)], input=json.dumps({"session_id": "s", "hook_event_name": event}),
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0
        if event == "SessionStart":
            assert "역할 분리 워크플로우가 켜져 있다" in r.stdout and "작업 기록 hook이 꺼져 있다" in r.stdout
            assert r.stdout.count("[PortRAN 설정]") == 2
        else:
            assert r.stdout == ""
    local_settings(logdir, {agent_log.WORKFLOW_SWITCH: "on"})
    out = io.StringIO()
    agent_log.record(io.StringIO('{"session_id":"s","hook_event_name":"SessionStart"}'), out)
    assert "역할 분리" in out.getvalue() and "작업 기록" not in out.getvalue()
    local_settings(logdir, {agent_log.WORKFLOW_SWITCH: "off"})  # 기본값과 같으면 알리지 않음
    out = io.StringIO()
    agent_log.record(io.StringIO('{"session_id":"s","hook_event_name":"SessionStart"}'), out)
    assert out.getvalue() == ""
    assert [r["event"] for r in lines(logdir / "s.jsonl")] == ["SessionStart"] * 3  # 기록은 켜져 있을 때만


def test_guard_still_denies_but_does_not_log_when_log_off(logdir):
    local_settings(logdir, {agent_log.LOG_SWITCH: "off"})
    payload = {"session_id": "g", "hook_event_name": "PreToolUse", "agent_type": "reviewer", "tool_name": "Bash",
               "tool_input": {"command": "rm -rf x"}}
    r = subprocess.run([sys.executable, str(HOOKS / "readonly_guard.py")], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and '"permissionDecision": "deny"' in r.stdout
    assert not (logdir / "g.jsonl").exists()


def test_record_keeps_own_ts_event_and_survives_surrogates(logdir):
    feed({"session_id": "s", "hook_event_name": "Stop", "ts": "payload-ts", "event": "payload-event", "msg": "\ud800"})
    (rec,) = lines(logdir / "s.jsonl")
    assert rec["event"] == "Stop" and rec["ts"] != "payload-ts"
    assert (rec["payload_ts"], rec["payload_event"]) == ("payload-ts", "payload-event")
    assert not (logdir / "_hook_errors.log").exists()


def test_record_survives_deep_nesting(logdir):
    deep = {"session_id": "s", "hook_event_name": "Stop"}
    cur = deep
    for _ in range(3000):
        cur["x"] = {}
        cur = cur["x"]
    rec = agent_log.build_record(deep, "NOW", [], 4000)
    assert rec["event"] == "Stop" and "note" in rec


def test_record_swallows_write_errors(logdir, monkeypatch):
    monkeypatch.setattr(agent_log, "append_line", lambda *a: 1 / 0)
    assert agent_log.record(io.StringIO('{"session_id":"s","hook_event_name":"Stop"}')) == 0
    assert "ZeroDivisionError" in (logdir / "_hook_errors.log").read_text()


# ── 보기 ─────────────────────────────────────────────────────────────────────

SESSION = [
    {"ts": "2026-11-18T10:00:00.000+09:00", "event": "UserPromptSubmit", "prompt": "M13 구현해줘", "prompt_id": "p1"},
    {"ts": "2026-11-18T10:00:01.000+09:00", "event": "PreToolUse", "tool_name": "Bash", "tool_use_id": "a",
     "tool_input": {"command": "pytest -q"}, "prompt_id": "p1"},
    {"ts": "2026-11-18T10:00:02.000+09:00", "event": "PreToolUse", "tool_name": "Bash", "tool_use_id": "b",
     "agent_type": "reviewer", "agent_id": "x1", "tool_input": {"command": "pytest tests/test_ingest.py"}, "prompt_id": "p1"},
    {"ts": "2026-11-18T10:00:03.000+09:00", "event": "PostToolUse", "tool_name": "Bash", "tool_use_id": "a",
     "duration_ms": 1500, "tool_response": {"stdout": "10 passed"}},
    {"ts": "2026-11-18T10:00:04.000+09:00", "event": "UserPromptSubmit", "prompt": "<task-notification> done", "prompt_id": "p2"},
    {"ts": "2026-11-18T10:00:05.000+09:00", "event": "PostToolUseFailure", "tool_name": "Bash", "tool_use_id": "b",
     "agent_type": "reviewer", "error": "Exit code 1\nE  assert 3 == 2", "prompt_id": "p1"},
    {"ts": "2026-11-18T10:00:06.000+09:00", "event": "GuardDenied", "tool_name": "Bash", "agent_type": "reviewer",
     "tool_input": {"command": "rm -rf x"}, "reason": "reviewer는 읽기 전용", "prompt_id": "p1"},
    {"ts": "2026-11-18T10:00:07.000+09:00", "event": "SubagentStop", "agent_type": "reviewer",
     "last_assistant_message": "## 판정: 수정 필요"},
]


def test_show_pairs_calls_with_results():
    out = io.StringIO()
    agent_log.show(SESSION, out=out)
    text = out.getvalue()
    assert "▶ Bash: pytest -q  → ✓ 1.5s" in text
    assert "reviewer │ ▶ Bash: pytest tests/test_ingest.py  → ✗" in text and "assert 3 == 2" in text
    assert "🔔 <task-notification>" in text and "⛔ 읽기 전용 차단" in text and "판정: 수정 필요" in text


def test_errors_shows_prompt_by_prompt_id_not_notification():
    out = io.StringIO()
    assert agent_log.errors(SESSION, out=out) == 2  # 실패 1 + 가드 차단 1
    text = out.getvalue()
    assert "프롬프트: M13 구현해줘" in text and "task-notification" not in text.split("── 실패 1")[1].split("입력")[0]
    assert '"command": "pytest tests/test_ingest.py"' in text and "(reviewer)" in text


def test_errors_include_calls_without_result():
    # 권한 거부·중단으로 결과가 없는 호출도 보인다. 가드가 막은 호출(GuardDenied)은 두 번 세지 않는다
    recs = [
        {"ts": "2026-11-18T10:00:00+09:00", "event": "UserPromptSubmit", "prompt": "정리해줘", "prompt_id": "p"},
        {"ts": "2026-11-18T10:00:01+09:00", "event": "PreToolUse", "tool_name": "Bash", "tool_use_id": "x",
         "tool_input": {"command": "ls; echo $?"}, "prompt_id": "p"},
        {"ts": "2026-11-18T10:00:02+09:00", "event": "PreToolUse", "tool_name": "Bash", "tool_use_id": "g", "agent_type": "reviewer",
         "tool_input": {"command": "rm x"}, "prompt_id": "p"},
        {"ts": "2026-11-18T10:00:02+09:00", "event": "GuardDenied", "tool_name": "Bash", "tool_use_id": "g", "agent_type": "reviewer",
         "tool_input": {"command": "rm x"}, "reason": "읽기 전용", "prompt_id": "p"},
    ]
    assert [r["tool_use_id"] for r in agent_log.unanswered_calls(recs)] == ["x"]
    out = io.StringIO()
    assert agent_log.errors(recs, out=out) == 2
    assert "결과 없음(권한 거부·중단" in out.getvalue() and "ls; echo $?" in out.getvalue()


def test_cli_list_show_errors(logdir):
    feed(*[dict(r, session_id="abc123", hook_event_name=r["event"]) for r in SESSION])
    script = HOOKS / "agent_log.py"
    run = lambda *a: subprocess.run([sys.executable, str(script), *a], capture_output=True, text=True, timeout=30)
    assert "abc123" in run("list").stdout
    assert "M13 구현해줘" in run("show", "abc").stdout
    assert "── 실패 2" in run("errors").stdout
    assert run("show", "zzz").returncode != 0


# ── 읽기 전용 가드 ───────────────────────────────────────────────────────────

def bash(agent, command):
    return {"session_id": "g", "hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_type": agent,
            "tool_input": {"command": command}}


@pytest.mark.parametrize("command", [
    "git diff dev...HEAD", "git status", "git log --oneline -5", "git branch -a",
    "pytest -q -rs 2>&1 | tail -20", "python grafana/build.py --check", 'grep -n "a > b" x.py',
    "ls 2>/dev/null; echo ok", "python3 - <<'PY'\nprint(1 > 0)\nPY\n", "docker compose ps",
    "curl -s -X POST --data-binary @t.jsonl http://localhost:8088/ingest",
    # 읽기만 하는 git·출력 (11/18 Reviewer 지적: 오탐)
    "git -C /mnt/c/portran/dashboard log --oneline -3", "git --no-pager diff", "git stash list", "git stash show -p",
    "git tag -l", "git tag", "git worktree list", "git branch", "git branch --contains abc123", "git config --get user.name",
    "git remote -v", "git fetch origin", "echo x > /dev/stderr", "ls &>/dev/null",
    "curl -s -o /dev/null -w '%{http_code}' localhost", "wget -qO- localhost:3000/api/health", "docker compose logs --tail 5 grafana",
    "for f in *.py; do wc -l $f; done", "grep -rn 'then rm' .", "git reflog", "git reflog show", "ls > >(cat)",
    "diff <(ls a) <(ls b)", "curl -X GET localhost", "curl -sS -w '%{http_code}' -o /dev/null localhost",
    # build.py를 읽기만 하는 명령, 문자열 속 글자, git grep -o, PDF를 화면으로 (11/18 Reviewer 4차 지적: 오탐)
    "git diff HEAD -- grafana/build.py", "git log -p grafana/build.py", "git show HEAD:grafana/build.py",
    "git blame grafana/build.py", "grep -n CELL_LIMIT grafana/build.py", "git log -1 --format='%h %s' -- grafana/build.py",
    'grep -n "curl -X DELETE" docs/x.md', "grep -rn 'bash -c \"rm x\"' tests",
    "python3 - <<'PY'\nprint('bash -c \"git stash\"', \"curl -X 'PUT'\")\nPY\n", "git grep -o foo",
    "pdftotext reference/TeleRAN.pdf -", ".venv/bin/python grafana/build.py --check",
    # 안쪽 명령·경로가 읽기뿐인 것 (11/18 Reviewer 2차 지적 뒤)
    "git format-patch -1 --stdout", "git sparse-checkout list", "docker compose exec influxdb influx query 'x'",
    "docker compose exec -T grafana ls /etc/grafana", 'bash -c "pytest -q"', "cd grafana && python build.py --check",
    "sed -n '1,5p' f", "find . -name '*.py' -newer x", "cat docs/rm.md", "git log --format=%h!",
])
def test_guard_allows_checks(command):
    assert readonly_guard.decide(bash("reviewer", command)) is None


@pytest.mark.parametrize("command", [
    "rm -rf grafana", "echo x > collector/a.py", "pytest 2> err.log", "sed -i s/a/b/ f.py",
    "git checkout -- .", "git stash", "git commit -m x", 'find . -name "*.pyc" -exec rm {} \\;', "ls | xargs rm",
    "pip install foo", "docker compose down", "python grafana/build.py", "cd x && mv a b",
    "cat > f.py <<'EOF'\nx = 1\nEOF\n",
    # 명령 앞 공백·감싸는 명령·제어 구문, git 전역 옵션 (11/18 Reviewer 지적: 우회)
    " rm -rf x", "if true; then rm x; fi", "for f in a; do rm $f; done", "echo `rm x`", "echo $(rm x)", "time rm x",
    "env FOO=1 rm x", "FOO=1 rm x", "command rm x", "timeout 5 rm x", "ls | xargs -0 rm",
    "git -C . commit -m x", "git -c core.x=y commit", "git --no-pager stash", "git branch newname",
    "git branch -D old", "git tag v1", "git worktree add ../x", "git config user.name foo", "git remote add o url", "git restore .",
    "curl -o out.html localhost", "curl -O localhost/x", "wget localhost/x", "docker compose -f a.yml down",
    "docker compose exec grafana grafana cli admin reset-admin-password pw", "influx write -b x 'm v=1'", "tar xf a.tar",
    # 따옴표 안 명령, 제어 구문, 옵션 값, 절대 경로, docker exec 안, 지우는 요청 (11/18 Reviewer 2차 지적)
    'bash -c "rm -rf x"', "sh -c 'git commit -m x'", 'eval "rm x"', "{ rm x; }", "! rm x", "if rm x; then echo; fi",
    "while git stash; do :; done", "ls | xargs -n 1 rm", "nice -n 10 rm x", "sudo -u root rm x", "/bin/rm x",
    "/usr/bin/git commit -m x", "find . -delete", "docker compose exec grafana rm -rf /var/lib/grafana", "docker volume rm x",
    "docker system prune -f", "docker rmi img", "git bisect start", "git sparse-checkout set a", "git format-patch -1",
    "git diff --output=x.patch", "cd grafana && python build.py", 'sed -e "s/a/b/" -i f',
    "curl -X DELETE http://localhost:3000/api/dashboards/uid/x", "curl --request PUT localhost",
    # 따옴표 메서드, 붙여 쓴 짧은 옵션, 남은 git·파일 명령, 옵션 값 있는 감싸기 (11/18 Reviewer 3차 지적)
    'curl -X "DELETE" localhost', "curl -sSo x localhost", "curl -Lo x localhost", "curl -sO localhost/x",
    "git reflog expire --all", "git checkout-index -a", "git read-tree HEAD", "git fetch --prune origin", "rsync a b",
    "unlink f", "npm i x", "python3 grafana/build.py --checkout", "xargs -I {} rm {}", "timeout -s KILL 5 rm x",
    # build.py 실행의 여러 꼴, PDF 변환 파일, 아주 긴 명령 (11/18 Reviewer 4차 지적 뒤)
    ".venv/bin/python grafana/build.py", "python3 -m grafana.build", "./grafana/build.py", "pdftotext reference/TeleRAN.pdf",
    "pdftoppm -png a.pdf out", "ls " * 12_000,
])
@pytest.mark.parametrize("agent", ["reviewer", "researcher"])
def test_guard_denies_changes(agent, command):
    out = readonly_guard.decide(bash(agent, command))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert agent in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_guard_is_fast_on_repeated_wrappers():
    # 감싸는 명령을 여러 갈래로 해석할 수 있으면 정규식이 지수적으로 느려져 hook 제한 시간(10초)을 넘긴다
    import time
    for prefix in ("env -i ", "sudo -u -u ", "nice -n 1 ", "timeout 5 ", "sudo -u root nice -n 5 ", "xargs -I {} "):
        start = time.perf_counter()
        readonly_guard.violation(prefix * 300 + "ls")
        assert time.perf_counter() - start < 1, prefix


def test_guard_reason_is_one_line():
    assert "\n" not in readonly_guard.violation("ls \nrm x")


@pytest.mark.parametrize("agent", [None, "general-purpose", "Explore"])
def test_guard_ignores_main_and_other_agents(agent):
    assert readonly_guard.decide(bash(agent, "rm -rf x")) is None


def test_guard_records_denial_and_never_fails(logdir):
    script = HOOKS / "readonly_guard.py"
    r = subprocess.run([sys.executable, str(script)], input=json.dumps(bash("reviewer", "git reset --hard")),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert lines(logdir / "g.jsonl")[0]["event"] == "GuardDenied"
    for stdin in ("not json", "", json.dumps(bash("reviewer", "git status"))):
        r = subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True, text=True, timeout=30)
        assert (r.returncode, r.stdout) == (0, "")


def test_settings_register_hooks():
    settings = json.loads((HOOKS.parent / "settings.json").read_text())["hooks"]
    events = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionDenied",
              "SubagentStart", "SubagentStop", "Stop", "StopFailure", "PreCompact", "SessionEnd")
    assert set(settings) == set(events)
    for event in events:
        commands = [h["command"] for group in settings[event] for h in group["hooks"]]
        assert any("agent_log.py" in c for c in commands), event
    guards = [g for g in settings["PreToolUse"] if any("readonly_guard.py" in h["command"] for h in g["hooks"])]
    assert [g["matcher"] for g in guards] == ["Bash"]


def test_agent_definitions_are_read_only():
    agents = HOOKS.parent / "agents"
    for name in readonly_guard.READ_ONLY_AGENTS:
        front = (agents / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
        meta = dict(line.split(":", 1) for line in front.strip().splitlines())
        tools = {t.strip() for t in meta["tools"].split(",")}
        assert meta["name"].strip() == name
        assert not tools & {"Edit", "Write", "NotebookEdit"}, name
