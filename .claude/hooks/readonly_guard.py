#!/usr/bin/env python3
"""읽기 전용 역할(researcher·planner·reviewer)이 Bash로 저장소·환경을 바꾸지 못하게 막는 PreToolUse hook.

.claude/agents/의 세 역할은 Edit·Write 도구가 없지만 Bash로는 파일을 바꿀 수 있다. 서브에이전트 안의 도구 호출에는
hook 입력에 `agent_type`이 실려 오므로, 그 값이 읽기 전용 역할이면 바꾸는 명령을 거부하고 이유를 모델에 돌려준다.
막은 호출은 작업 기록(logs/agent/)에 `GuardDenied`로 남는다.

- 메인 에이전트(agent_type 없음)와 다른 서브에이전트에는 아무것도 하지 않는다.
- 막는 것: 파일 쓰기 리다이렉션·rm·mv·cp·tee·sed -i·find -delete 등, git 상태를 바꾸는 명령(전역 옵션 `-C`·`-c` 뒤도),
  패키지 설치, docker 생명주기·볼륨 삭제, Grafana·InfluxDB 설정 변경, curl·wget 파일 저장, curl DELETE·PUT·PATCH,
  `--check` 없는 `build.py`. `bash -c "…"`·`eval "…"`·`docker exec` 안의 명령도 다시 검사한다.
  읽기만 하는 git(`diff`·`log`·`status`·`stash list`·`tag -l`·`branch -a` 등), 로컬 서비스 확인 요청(GET, `/ingest` POST 시험)·
  pytest는 검증에 필요해 막지 않는다.
- 우회할 수 없는 샌드박스가 아니라 실수를 막는 안전장치다(예: `python -c "open(...).write()"`, 변수에 담은 명령
  `c=rm; $c x`, 스크립트 파일 안의 명령은 못 잡는다).
- 이 스크립트가 실패하면 막지 않는다(작업을 멈추지 않게). 오류는 logs/agent/_hook_errors.log.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_log  # noqa: E402

READ_ONLY_AGENTS = {"researcher", "planner", "reviewer"}

# 명령이 시작되는 자리: 줄 처음·; & | ( { ! 줄바꿈 백틱 $( 뒤, then·do·else·elif·if·while·until 뒤, find -exec 뒤.
# 그 뒤에 sudo·xargs·env·time·timeout N·command·nohup·nice 같은 감싸는 명령(옵션 값 포함)과 VAR=값 대입이 몇 개 와도 된다.
# 명령 이름 앞의 경로(/bin/rm, /usr/bin/git)도 받는다.
_LEAD = r"(?:^|[;&|({!\n`]|\$\(|\b(?:then|do|else|elif|if|while|until)\b|-exec(?:dir)?\b)"
_WRAPPERS = r"sudo|xargs|exec|env|time|command|builtin|nohup|nice|stdbuf|timeout"
# 옵션 값은 '-'로 시작하지 않고 감싸는 명령 이름도 아닌 토큰 하나. 숫자 인자(timeout 5)는 timeout에만 둔다 —
# 한 문자열을 여러 갈래로 해석할 수 있으면 정규식이 지수적으로 되돌아간다(`nice -n 1 ` 반복, 11/18 Reviewer 3차)
_OPT = r"-\S+\s+(?:(?!(?:" + _WRAPPERS + r")\s)[^-\s]\S*\s+)?"
_WRAP = (r"(?:(?:" + _WRAPPERS.replace("|timeout", "") + r")\s+(?:" + _OPT + r")*"
         r"|timeout\s+(?:" + _OPT + r")*\d\S*\s+|\w+=\S*\s+)*")
_CMD = _LEAD + r"\s*" + _WRAP + r"(?:[\w.~-]*/)*"
_END = r"(?![\w.-])"
_DEV_OK = r"/dev/(?:null|stdout|stderr|tty|fd/\d+)\b"

RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(_CMD + r"(rm|rmdir|mv|cp|tee|touch|mkdir|ln|chmod|chown|truncate|dd|install|unzip|tar|patch|shred|unlink|rsync)" + _END),
     "파일을 만들거나 바꾸거나 지우는 명령"),
    (re.compile(r"\b(sed|perl)\b[^;&|\n]*?\s(-[a-zA-Z]*i\S*|--in-place\S*)"), "파일을 제자리에서 고치는 명령"),
    (re.compile(r"\bfind\b[^;&|\n]*\s(-delete|-fprint\S*|-fls)\b"), "find로 파일 지우기·쓰기"),
    (re.compile(r"\b(pip|pip3|uv|poetry|npm|pnpm|yarn|apt|apt-get)\s+(install|i|ci|uninstall|un|add|remove|rm|update|upgrade|sync)\b"), "패키지 설치·삭제"),
    (re.compile(r"\bdocker(\s+compose|-compose)?\s+(?:-\S+\s+(?:\S+\s+)?)*?(up|down|restart|stop|start|kill|rm|rmi|run|build|pull|create|cp)\b"),
     "컨테이너를 띄우거나 멈추는 명령"),
    (re.compile(r"\bdocker\s+(volume|system|image|container|network|builder)\s+(rm|prune|create)\b"), "docker 볼륨·이미지를 지우는 명령"),
    (re.compile(r"\bgrafana(?:\s+cli|-cli)\b[^;&|\n]*\b(admin|plugins\s+(?:install|uninstall|remove|update))\b"), "Grafana 설정을 바꾸는 명령"),
    (re.compile(r"\binflux\s+(write|delete|setup|(?:bucket|auth|user|org|task)\s+(?:create|delete|update|password))\b"), "InfluxDB 데이터·설정을 바꾸는 명령"),
    (re.compile(r"\bcurl\b[^;&|\n]*\s(?:-[a-zA-Z]*o\s*(?!" + _DEV_OK + r")\S|--output[ =](?!" + _DEV_OK + r")\S|-[a-zA-Z]*O\b|--remote-name)"),
     "curl로 파일 저장"),
    (re.compile(_CMD + r"wget\b(?![^;&|\n]*(?:-q?O\s*-(?:\s|$)|-q?O\s*/dev/null|--spider))"), "wget으로 파일 저장"),
    (re.compile(_CMD + r"(?:python3?(?:\.\d+)?\s+(?:-\S+\s+)*)?(?:[\w.~-]*/)*build\.py\b(?![^;&|\n]*--check(?![\w-]))"),
     "grafana/build.py는 --check로만 실행 (대시보드 JSON을 다시 쓰지 않게)"),
    (re.compile(_CMD + r"python3?(?:\.\d+)?\s+-m\s+grafana\.build\b(?![^;&|\n]*--check(?![\w-]))"),
     "grafana/build.py는 --check로만 실행 (대시보드 JSON을 다시 쓰지 않게)"),
    (re.compile(_CMD + r"pdftotext\b(?![^;&|\n]*\s-(?:\s|$))|" + _CMD + r"pdftoppm\b"),
     "PDF 변환 파일 만들기 (pdftotext는 `<파일> -`로 화면에만)"),
]

# curl 메서드는 따옴표를 벗긴 글에서 본다(curl -X "DELETE")
CURL_METHOD = re.compile(_CMD + r"curl\b[^;&|\n]*\s(?:-X\s*|--request[ =])[\"']?(DELETE|PUT|PATCH)\b", re.I)

# 따옴표 안 명령도 다시 검사한다: bash -c "…", sh -c '…', eval "…"
INNER_SHELL = re.compile(_CMD + r"(?:bash|sh|zsh|dash)\s+(?:-\w+\s+)*-\w*c\w*\s+(['\"])(.*?)\1|" + _CMD + r"eval\s+(['\"])(.*?)\3", re.S)
# docker exec 안에서 도는 명령: 옵션·서비스 이름을 건너뛰고 나머지를 다시 검사한다
DOCKER_EXEC = re.compile(r"\bdocker(?:\s+compose|-compose)?\s+exec\s+([^;&|\n]*)")
DOCKER_EXEC_OPT_WITH_ARG = {"-e", "--env", "-u", "--user", "-w", "--workdir", "--index", "--env-file"}


# git: 전역 옵션(-C 경로, -c 키=값, --no-pager 등)을 건너뛰고 하위 명령·인자로 판정한다
GIT = re.compile(_CMD + r"git((?:\s+[^\s;&|\n`)]+)*)")
GIT_OPT_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GIT_WRITE = {"add", "commit", "checkout", "switch", "reset", "restore", "push", "pull", "merge", "rebase", "cherry-pick",
             "revert", "clean", "rm", "mv", "am", "apply", "init", "clone", "gc", "prune", "update-ref", "update-index",
             "submodule", "notes", "replace", "filter-branch", "commit-tree", "symbolic-ref", "bisect", "checkout-index",
             "read-tree", "pack-refs", "repack"}


def _git_change(args: list[str]) -> str | None:
    """git 인자(전역 옵션 포함)가 저장소 상태를 바꾸면 하위 명령 이름, 아니면 None."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_OPT_WITH_ARG else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    flags = [a for a in rest if a.startswith("-")]
    positional = [a for a in rest if not a.startswith("-")]
    if sub in GIT_WRITE:
        return sub
    if any(a == "--output" or a.startswith("--output=") for a in rest):  # git diff --output=x.patch 등
        return f"{sub} --output"
    if sub == "reflog":
        return sub if positional[:1] and positional[0] in {"expire", "delete"} else None
    if sub == "fetch":  # 원격 추적 ref만 갱신하는 fetch는 허용, ref를 지우는 --prune은 거부
        return sub if set(flags) & {"-p", "--prune", "-P", "--prune-tags"} else None
    if sub == "format-patch":
        return None if "--stdout" in rest else sub
    if sub == "sparse-checkout":
        return None if rest[:1] == ["list"] else sub
    if sub == "stash":
        return None if rest[:1] in (["list"], ["show"]) else sub  # 맨 `git stash`는 push와 같다
    if sub == "tag":
        return None if not rest or set(flags) & {"-l", "--list", "-n", "--contains", "--points-at", "--merged"} else sub
    if sub == "worktree":
        return None if rest[:1] == ["list"] else sub
    if sub == "branch":
        destructive = {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete", "--move", "--copy", "--force",
                       "-u", "--set-upstream-to", "--unset-upstream", "--edit-description"}
        if set(flags) & destructive or any(f.startswith("--set-upstream-to=") for f in flags):
            return sub
        listing = {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort", "--format"}
        if rest and not rest[0].startswith("-"):
            return sub  # `git branch <이름>` = 새 브랜치
        return None if not positional or set(flags) & listing or "--list" in flags or "-l" in flags else sub
    if sub == "config":
        reading = {"--get", "--get-all", "--get-regexp", "-l", "--list", "--show-origin", "--show-scope"}
        if set(flags) & reading:
            return None
        return sub if len(positional) >= 2 or set(flags) & {"--unset", "--unset-all", "--add", "--replace-all", "-e", "--edit"} else None
    if sub == "remote":
        return sub if positional[:1] and positional[0] in {"add", "remove", "rm", "rename", "set-url", "set-head", "prune"} else None
    return None


# 파일로 내보내는 리다이렉션 (/dev/null·/dev/stderr 등과 fd 복제는 허용). 따옴표 안은 보지 않는다.
REDIRECT = re.compile(r">>?\s*(?![&(])[^\s>]")  # >(…)는 프로세스 치환
SAFE_REDIRECT = re.compile(r"(?:\d*|&)>>?\s*" + _DEV_OK + r"|\d*>&\d+")
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
# heredoc 본문(<<EOF … EOF) — 안의 파이썬 비교식 같은 '>'를 리다이렉션으로 오인하지 않게 뺀다
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n.*?\n\s*\2\s*(?=\n|$)", re.S)


def _docker_exec_inner(args: str) -> str:
    tokens = args.split()
    i = 0
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in DOCKER_EXEC_OPT_WITH_ARG else 1
    return " ".join(tokens[i + 1:])  # tokens[i] = 서비스(컨테이너) 이름


MAX_COMMAND_CHARS = 30_000  # 이보다 긴 명령은 판정이 hook 제한 시간에 가까워진다(11/18 Reviewer 4차: 80 KB → 9초)


def violation(command: str, depth: int = 0) -> str | None:
    unheredoc = HEREDOC.sub(lambda m: "<<" + m.group(2) + m.group(3), command)
    if len(unheredoc) > MAX_COMMAND_CHARS:
        return f"명령이 너무 길어 판정하지 않음({len(unheredoc):,}자 > {MAX_COMMAND_CHARS:,}자) — 나눠서 실행"
    if depth < 3:
        for m in INNER_SHELL.finditer(unheredoc):
            why = violation(m.group(2) if m.group(2) is not None else m.group(4) or "", depth + 1)
            if why:
                return why
    bare = QUOTED.sub("''", unheredoc)
    if depth < 3:
        for m in DOCKER_EXEC.finditer(bare):
            why = violation(_docker_exec_inner(m.group(1)), depth + 1)
            if why:
                return f"docker exec 안에서 {why}"
    for pattern, reason in RULES:
        m = pattern.search(bare)
        if m:
            return f"{reason}: `{' '.join(m.group(0).split()).strip(' ;&|({!`$')}`"
    m = CURL_METHOD.search(unheredoc)
    if m:
        return f"curl로 지우거나 바꾸는 요청: `{m.group(1).upper()}`"
    for m in GIT.finditer(bare):
        sub = _git_change(m.group(1).split())
        if sub:
            return f"git 상태를 바꾸는 명령: `git {sub}`"
    if REDIRECT.search(SAFE_REDIRECT.sub("", bare)):
        return "파일로 내보내는 리다이렉션(>, >>)"
    return None


def decide(payload: dict) -> dict | None:
    """막아야 하면 hook 출력 JSON, 아니면 None."""
    agent = str(payload.get("agent_type") or "")
    if agent not in READ_ONLY_AGENTS or payload.get("tool_name") != "Bash":
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    why = violation(command)
    if why is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{agent}는 읽기 전용이다(CLAUDE.md 12절 10항) — {why}. "
                "고치지 말고 찾은 문제와 재현 명령을 보고에 적어라. 확인에 꼭 필요한 명령이면 그 이유를 보고에 쓰고 메인 에이전트에게 맡겨라."
            ),
        }
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        out = decide(payload)
        if out is None:
            return 0
        print(json.dumps(out, ensure_ascii=False))
        if not agent_log.switch_on(agent_log.LOG_SWITCH):  # 작업 기록을 끄면 막기만 하고 남기지 않는다(D207)
            return 0
        try:  # 작업 기록에 남긴다
            rec = dict(payload, hook_event_name=agent_log.GUARD_EVENT,
                       reason=out["hookSpecificOutput"]["permissionDecisionReason"])
            now = datetime.now().astimezone().isoformat(timespec="milliseconds")
            agent_log.append_line(
                agent_log.session_file(payload.get("session_id")),
                agent_log.build_record(rec, now, agent_log.env_secret_values(agent_log.project_dir()), agent_log.max_chars()),
            )
        except Exception:
            pass
    except Exception:
        try:
            d = agent_log.log_dir()
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "_hook_errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} readonly_guard: {sys.exc_info()[1]!r}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
