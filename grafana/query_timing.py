"""대시보드 쿼리를 실제 Grafana에 보내 걸린 시간·오류·점 수를 잰다 (읽기 전용, D202).

    python grafana/query_timing.py --dashboard monitoring --range 7d                       # 로컬 Grafana, AWS(aws)
    python grafana/query_timing.py --url http://<탄력적 IP>:3000 --source aws --range 7d \\
        --max-seconds 2 --parallel --parallel-max-seconds 5

저장소의 grafana/dashboards/<이름>.json(build.py가 만든 것)에서 패널·주석 쿼리를 꺼내, Grafana `/api/ds/query`로 보낸다.
브라우저처럼 패널 하나의 쿼리(refId A·B …)는 한 요청으로 보낸다 — 한 요청의 쿼리는 차례로 돌아 시간이 더해진다.
배포하지 않은 쿼리도 실제 서버 데이터로 잴 수 있다. 템플릿 변수는 브라우저처럼 바꿔 넣는다: `${source}` = --source,
`${cell:*}` = 셀 변수의 모든 값(All), `${alert_id}` = 경보 변수의 첫 값. maxDataPoints는 패널 폭에 비례(24칸 = 1850 px),
간격은 Grafana처럼 (범위 ÷ maxDataPoints)를 반올림한 값이다.

관제는 5초마다 새로고침하고, 새로고침은 진행 중인 쿼리를 취소한다 — 패널 요청이 5초 안에 끝나야 화면에 나온다.
실패(오류·점 수 초과·시간 초과)가 있으면 1로 끝난다. 관리자 계정은 .env의 GRAFANA_ADMIN_USER/PASSWORD(출력하지 않음).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = ROOT / "grafana" / "dashboards"
DS = {"type": "influxdb", "uid": "portran-influxdb"}
FULL_WIDTH_PX = 1850     # 24칸 패널의 그래프 폭(1920 화면 기준)
ANNOTATION_PX = 1920     # 주석 쿼리는 maxDataPoints = 창 폭
POINTS_FACTOR = 10       # Grafana InfluxDB(Flux)는 프레임 하나가 maxDataPoints × 10행을 넘으면 오류
RECORD_ONLY = {"근거 KPM"}  # 경보 하나의 100 ms 근거 — 시간·점 수 판정에서 빼고 기록만
RANGES = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}

# Grafana rangeutil.roundInterval — (상한 ms, 간격 ms)
_ROUND = [(15, 10), (35, 20), (75, 50), (150, 100), (350, 200), (750, 500), (1500, 1000), (3500, 2000),
          (7500, 5000), (12500, 10000), (17500, 15000), (25000, 20000), (45000, 30000), (90000, 60000),
          (210000, 120000), (450000, 300000), (750000, 600000), (1050000, 900000), (1500000, 1200000),
          (2700000, 1800000), (5400000, 3600000), (9000000, 7200000), (16200000, 10800000),
          (32400000, 21600000), (86400000, 43200000), (604800000, 86400000)]


def round_interval(ms: float) -> int:
    for limit, value in _ROUND:
        if ms < limit:
            return value
    return 604800000


def range_ms(text: str) -> int:
    m = re.fullmatch(r"(\d+)([mhd])", text)
    if not m:
        raise SystemExit(f"--range는 30m·24h·7d 꼴: {text}")
    return int(m.group(1)) * RANGES[m.group(2)]


def load_env() -> dict[str, str]:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class Grafana:
    def __init__(self, url: str, user: str, password: str, rng: str, timeout: float):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.rng = rng
        self.span = range_ms(rng)
        self.timeout = timeout

    def query(self, flux: str | list[tuple[str, str]], max_points: int) -> dict:
        """쿼리 하나(문자열) 또는 패널의 쿼리 여럿([(refId, Flux)]) — 브라우저처럼 패널의 쿼리를 한 요청으로 보낸다."""
        interval = round_interval(self.span / max_points)
        targets = [("A", flux)] if isinstance(flux, str) else flux
        body = {"queries": [{"refId": ref, "datasource": DS, "query": q, "maxDataPoints": max_points,
                             "intervalMs": interval} for ref, q in targets], "from": f"now-{self.rng}", "to": "now"}
        req = urllib.request.Request(self.url + "/api/ds/query", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": self.auth})
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                code, data = resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                data = {"message": raw[:200].decode(errors="replace")}
        except (urllib.error.URLError, TimeoutError) as e:
            code, data = 0, {"message": str(e)}
        seconds = time.monotonic() - start
        results = [data.get("results", {}).get(ref, {}) for ref, _ in targets]
        frames = [f for r in results for f in r.get("frames", [])]
        rows = max((len(f["data"]["values"][0]) if f.get("data", {}).get("values") else 0 for f in frames), default=0)
        error = "; ".join(r["error"] for r in results if r.get("error")) or (data.get("message") if code != 200 else "")
        return {"code": code, "seconds": seconds, "rows": rows, "limit": max_points * POINTS_FACTOR,
                "error": error or "", "values": [f["data"]["values"] for f in frames if f.get("data", {}).get("values")]}


def substitute(flux: str, values: dict[str, str]) -> str:
    out = flux
    for key, value in values.items():
        out = out.replace(key, value)
    left = re.findall(r"\$\{[^}]+\}", out)
    if left:
        raise SystemExit(f"바꾸지 못한 변수: {sorted(set(left))}")
    return out


def regex_value(values: list[str]) -> str:
    escaped = [re.sub(r"([-\[\]{}()*+?.,\\^$|#\s/])", r"\\\1", v) for v in values]
    return escaped[0] if len(escaped) == 1 else "(" + "|".join(escaped) + ")"


def variable_values(g: Grafana, board: dict, source: str) -> dict[str, str]:
    """브라우저가 하는 것처럼 변수 값을 정한다: cell = 모든 값(All), alert_id = 첫 값."""
    values = {"${source}": source}
    variables = {v["name"]: v for v in board.get("templating", {}).get("list", [])}
    if "cell" in variables:
        res = g.query(substitute(variables["cell"]["query"], values), 1000)
        cells = sorted({str(x) for vals in res["values"] for x in vals[-1] if x is not None})
        values["${cell:json}"] = json.dumps(cells)
        values["${cell:regex}"] = regex_value(cells) if cells else "()"
    if "alert_id" in variables:
        res = g.query(substitute(variables["alert_id"]["query"], values), 1000)
        ids = [x for vals in res["values"] for x in vals[-1] if x]
        values["${alert_id}"] = ids[0] if ids else ""
    return values


def collect(board: dict) -> list[tuple[str, list[tuple[str, str]], int]]:
    """(이름, [(refId, Flux)], maxDataPoints) — 패널 하나(쿼리 여럿이면 한 요청)와 주석 하나씩."""
    items = []
    for p in board["panels"]:
        if p.get("type") == "row":
            continue
        width = max(1, round(FULL_WIDTH_PX * p["gridPos"]["w"] / 24))
        targets = [(t.get("refId", "A"), t["query"]) for t in p.get("targets", []) if t.get("query")]
        if targets:
            items.append((f'{p["title"]} [{",".join(ref for ref, _ in targets)}]', targets, width))
    for a in board.get("annotations", {}).get("list", []):
        q = a.get("target", {}).get("query")
        if q:
            items.append((f'주석: {a["name"]}', [("Anno", q)], ANNOTATION_PX))
    return items


def main(argv: list[str]) -> int:
    env = load_env()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=f"http://localhost:{env.get('GRAFANA_PORT', '3000')}")
    ap.add_argument("--source", default="aws", help="데이터 출처(env 태그): aws·on-premise·p4(11/20 전 AWS)·replay·sample")
    ap.add_argument("--dashboard", choices=["monitoring", "performance"], default="monitoring")
    ap.add_argument("--range", default="7d", help="지금부터 거꾸로 잴 범위: 1h·24h·7d")
    ap.add_argument("--max-seconds", type=float, default=5.0, help="요청(패널 하나·주석 하나)의 시간 상한")
    ap.add_argument("--parallel", action="store_true", help="순서대로 잰 뒤, 모든 쿼리를 동시에 보내 가장 늦은 응답도 잰다")
    ap.add_argument("--parallel-max-seconds", type=float, default=5.0, help="동시에 보냈을 때 가장 늦은 응답의 상한")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args(argv)

    board = json.loads((DASHBOARDS / f"{args.dashboard}.json").read_text(encoding="utf-8"))
    g = Grafana(args.url, env.get("GRAFANA_ADMIN_USER", "admin"), env.get("GRAFANA_ADMIN_PASSWORD", ""),
                args.range, args.timeout)
    values = variable_values(g, board, args.source)
    items = [(name, [(ref, substitute(q, values)) for ref, q in targets], mdp) for name, targets, mdp in collect(board)]
    print(f"{args.dashboard} · {args.url} · source={args.source} · now-{args.range} · 요청 {len(items)}개(패널·주석) · "
          f"셀 {values.get('${cell:json}', '-')}")

    failures = 0

    def judge(name: str, r: dict, limit_s: float) -> str:
        nonlocal failures
        problems = []
        if r["code"] != 200 or r["error"]:
            problems.append(f'오류 {r["code"]}: {r["error"][:200]}')
        if r["rows"] > r["limit"]:
            problems.append(f'행 {r["rows"]} > 상한 {r["limit"]}')
        if r["seconds"] > limit_s:
            problems.append(f'{r["seconds"]:.2f}s > {limit_s}s')
        if name.split(" [")[0] in RECORD_ONLY:
            return "기록만" + (f" ({'; '.join(problems)})" if problems else "")
        if problems:
            failures += 1
            return "실패: " + "; ".join(problems)
        return "통과"

    print(f"{'초':>7} {'최대 행':>8} {'상한':>7}  쿼리 — 판정")
    for name, flux, mdp in items:
        r = g.query(flux, mdp)
        print(f'{r["seconds"]:7.2f} {r["rows"]:8d} {r["limit"]:7d}  {name} — {judge(name, r, args.max_seconds)}')

    if args.parallel:
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(items)) as pool:
            results = list(pool.map(lambda it: g.query(it[1], it[2]), items))
        wall = time.monotonic() - start
        slowest = max(r["seconds"] for (name, _, _), r in zip(items, results) if name.split(" [")[0] not in RECORD_ONLY)
        print(f"동시에 {len(items)}개: 전체 {wall:.2f}s, 가장 늦은 응답(기록만 제외) {slowest:.2f}s")
        for (name, _, _), r in zip(items, results):
            verdict = judge(name, r, args.parallel_max_seconds)
            if verdict != "통과":
                print(f'  {name} — {verdict}')

    print("결과:", "통과" if failures == 0 else f"실패 {failures}건")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
