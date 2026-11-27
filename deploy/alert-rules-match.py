"""서버 Grafana의 알림 규칙이 provisioning 파일과 같은지 본다 (배포 헬스 체크, D221).

사용: curl …/api/v1/provisioning/alert-rules | python3 deploy/alert-rules-match.py grafana/provisioning/alerting/portran.json
파일의 규칙마다 서버에 같은 UID가 있고 제목·조회(data의 model.query)가 같으면 0, 아니면 다른 규칙을 적고 1.
표준 라이브러리만 쓴다(EC2 호스트의 python3로 돈다).
"""
import json
import sys


def queries(rule: dict) -> list[str]:
    return [d.get("model", {}).get("query", "") for d in rule.get("data", [])]


def mismatches(file_rules: list[dict], server_rules: list[dict]) -> list[str]:
    server = {r.get("uid"): r for r in server_rules}
    out = []
    for r in file_rules:
        s = server.get(r["uid"])
        if s is None:
            out.append(f"{r['uid']}: 서버에 없음")
        elif s.get("title") != r["title"] or queries(s) != queries(r):
            out.append(f"{r['uid']}: 제목 또는 조회가 다름")
    return out


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as f:
        file_rules = [r for g in json.load(f)["groups"] for r in g["rules"]]
    bad = mismatches(file_rules, json.load(sys.stdin))
    for line in bad:
        print(f"  알림 규칙 {line}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
