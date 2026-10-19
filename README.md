# PortRAN Observability

O-RAN 기반 5G 기지국 위협 탐지 솔루션의 **수집기 · 대시보드 · 검증 파이프라인**.

```
mock 생성기 / eBPF 에이전트 / 탐지 엔진 / 공격 도구
        │  JSON Lines (UDP 127.0.0.1:9999 또는 파일)
        ▼
    collector ──> InfluxDB ──> Grafana (실시간 관제 / 성능 검증)
        │
        └─> recordings/raw-*.jsonl ──> replay
    evaluator ──> eval_result (InfluxDB) + reports/
```

- 메시지 형식: [`schema/SCHEMA.md`](schema/SCHEMA.md) ← **다른 파트 담당자는 이것만 보면 된다**
- 진행 현황: [`docs/progress.md`](docs/progress.md). M1~M6(스키마, mock 생성기, collector, 실시간 관제·성능 검증 대시보드, evaluator, replay) 완료. 남은 것은 실제 파트(eBPF 에이전트·탐지 엔진·공격 도구)와의 연동이다.

## 준비물

| 항목 | 비고 |
|---|---|
| Docker + Docker Compose | Windows는 Docker Desktop 실행 + Settings → Resources → WSL integration에서 사용하는 배포판 켜기 |
| Python 3.10+ | Ubuntu/WSL에서 venv가 없으면 `sudo apt install python3-venv` |

## 처음 실행하기

```bash
# 1. 접속 정보 준비 (필요하면 토큰·비밀번호를 바꾼다)
cp .env.example .env

# 2. InfluxDB + Grafana 기동
docker compose up -d
docker compose ps        # 둘 다 running, influxdb는 (healthy)

# 3. Python 환경
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. 테스트
pytest
```

접속:

| 서비스 | 주소 | 로그인 |
|---|---|---|
| Grafana | http://localhost:3000 | `.env`의 `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` |
| InfluxDB UI | http://localhost:8086 | `.env`의 `INFLUX_ADMIN_USER` / `INFLUX_ADMIN_PASSWORD` |

Grafana의 **Connections → Data sources → InfluxDB**가 자동으로 등록되어 있어야 한다. 들어가서 **Save & test**를 누르면 bucket 연결 성공 메시지가 나온다.

## 자주 쓰는 명령

```bash
docker compose logs -f grafana     # provisioning 오류 확인
docker compose down                # 중지 (데이터 유지)
docker compose down -v             # 중지 + 데이터 전부 삭제
```

> **`.env`의 InfluxDB 값(토큰, org, bucket, 계정)은 최초 기동 때만 적용된다.**
> 나중에 바꾸면 Grafana는 새 토큰으로 접속을 시도하지만 InfluxDB에는 옛 토큰이 남아 있어 인증이 실패한다.
> 바꾼 뒤에는 `docker compose down -v && docker compose up -d`로 초기화한다(저장된 데이터가 지워진다).

## collector 실행하기

메시지를 받아 스키마로 검증하고, InfluxDB에 쓰고, 받은 그대로 녹화한다.

```bash
# 터미널 1: collector (기본 UDP 127.0.0.1:9999, Ctrl+C로 종료 — 남은 배치를 쓰고 끝냄)
python -m collector.collector

# 터미널 2: mock 데이터 보내기
python -m mock.generator --duration 600 --seed 42
```

```bash
# 파일을 끝까지 읽어서 넣고 종료 (mock 파일을 한 번에 넣을 때)
python -m collector.collector --in file://recordings/mock.jsonl --once

# 여러 입력을 동시에 (예: 탐지 엔진은 UDP, eBPF 에이전트는 파일)
python -m collector.collector --in udp://0.0.0.0:9999 --in file:///var/log/ebpf-agent.jsonl

# InfluxDB 없이 검증·녹화만 (다른 파트에서 메시지 형식을 확인할 때)
python -m collector.collector --dry-run
```

| 옵션 | 설명 |
|---|---|
| `--in` | `udp://host:port` 또는 `file://path`. 여러 번 줄 수 있음. 기본은 `.env`의 `COLLECTOR_UDP_HOST:PORT` |
| `--once` | 파일 입력을 끝까지 읽고 종료 (없으면 `tail -f`처럼 계속 기다림) |
| `--from-end` | 파일의 기존 내용은 건너뛰고 새로 추가되는 줄만 읽음 (기본은 처음부터) |
| `--dry-run` | InfluxDB에 쓰지 않음 |
| `--recordings` | 녹화 폴더 (기본 `.env`의 `RECORDINGS_DIR`) |

결과물 (`recordings/`, git 제외):
- `raw-<날짜시각>.jsonl`: 검증을 통과한 메시지를 받은 그대로. replay 입력으로 쓴다
- `rejected.jsonl`: 거부된 메시지와 사유 (`received_at`, `source`, `reasons`, `raw`). 실행할 때마다 이어 붙는다

1초마다 `수신 / 저장 / 거부` 건수가 로그로 나온다. InfluxDB가 잠시 죽어도 메시지를 메모리에 들고 있다가(최대 `COLLECTOR_MAX_PENDING`건) 복구되면 쓴다.
UDP는 손실이 날 수 있으므로, 많은 양을 한 번에 넣을 때는 파일 + `--once`를 쓴다.

> **collector가 준비된 뒤에 보낸다.** 시작해서 UDP 포트를 열기까지 몇 초(WSL의 `/mnt/c`에서는 4~5초) 걸린다. 로그에 `녹화 recordings/raw-…`가 나오기 전에 보낸 UDP 메시지는 사라진다.

## 대시보드 보기

`docker compose up -d`만 하면 Grafana의 **PortRAN** 폴더에 대시보드가 올라온다(provisioning). collector와 mock을 돌리면 바로 채워진다.

```bash
python -m collector.collector                      # 터미널 1
python -m mock.generator --duration 600 --seed 42  # 터미널 2 (실시간, 1배속)
```

**실시간 관제** — http://localhost:3000/d/portran-realtime (새로고침 5초, 기본 최근 15분)

| 행 | 패널 |
|---|---|
| 요약 | 최근 5분 탐지 건수, 최고 severity, 수집 상태(소스별 마지막 수신 후 경과), 접속 UE 수(`RRC.ConnMax` 최대 · `RRC.ConnMean` 평균), 데이터 출처(mock 여부) |
| 핵심 비교 | 위: 표준 KPM, 아래: eKPM(UE별 텔레메트리를 초당 건수로 집계). 같은 시간축. 빨간 세로선 = 탐지 이벤트, 주황 영역 = 공격 구간(`attack_run`) |
| 이벤트 | 탐지 이벤트 표(시각·공격 유형·severity·대상·룰·룰셋·지연·event_id), 공격 유형별 탐지 건수 |
| 근거 | 선택한 이벤트의 evidence(출처·지표·값·연산자·임계값·윈도우) |

- 위쪽 변수: `룰셋`(기본 full), `노드`, `공격 유형`, `이벤트`. 이벤트 표의 event_id를 누르면 근거 표가 그 이벤트로 바뀐다.
- 위쪽 토글로 annotation(공격 구간, 탐지)을 끄고 켤 수 있다.
- 대시보드의 기준은 `grafana/dashboards/*.json`이다. UI에서 고쳐도 저장되지 않으므로, 고친 뒤 **Share → Export → JSON**으로 내보내 파일을 바꾸고 커밋한다. 쿼리는 bucket 이름 대신 `v.defaultBucket`(datasource 설정)을 쓴다.
- eKPM 패널은 코드값(예: `rrc_msg_id` 0 = RRCSetupRequest)으로 센다. 코드표([`schema/SCHEMA.md`](schema/SCHEMA.md) 6.3절)가 바뀌면 같이 고친다(`pytest`가 어긋남을 잡는다).

**성능 검증** — http://localhost:3000/d/portran-evaluation (아래 evaluator를 한 번 이상 돌려야 채워진다)

| 행 | 패널 |
|---|---|
| 평가 정보 | 데이터 출처(mock이면 빨간색), 평가 구간, 공격 run 수·grace |
| 탐지 성능 | 시나리오 × 룰셋 표(탐지율·precision·오탐 수를 full / kpm_only 나란히), 탐지율 막대 |
| 탐지 지연 | 지연 분포 히스토그램(구간 안 모든 탐지), p50/p95 표(run별 첫 매칭 탐지) |
| 수집 오버헤드 | 노드별 CPU·메모리, eBPF on / off |

- 위쪽 변수 `평가`로 evaluator 실행 하나를 고른다(기본은 가장 최근). 히스토그램·오버헤드는 그 평가의 구간 데이터를 쓰므로 시간 선택과 상관없다.

## 성능 평가하기 (evaluator)

```bash
python -m evaluator.evaluate --from 2026-11-20T10:00:00 --to 2026-11-20T12:00:00 --grace-sec 5
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--from` | (필수) | 평가 시작. 시간대가 없으면 로컬 시각 |
| `--to` | `now` | 평가 끝 |
| `--grace-sec` | `.env`의 `EVAL_GRACE_SEC` (5) | 공격 종료 후 탐지를 인정하는 시간 |
| `--source` | `auto` | 리포트에 적을 데이터 출처. `auto`는 attack_run의 mock 표시로 판단. replay 데이터면 `replay`로 지정 |
| `--reports-dir` | `.env`의 `REPORTS_DIR` | 리포트 폴더 |
| `--no-write` | | InfluxDB `eval_result`에 쓰지 않고 리포트만 |

결과:
- 콘솔: 시나리오 × 룰셋별 탐지율·precision·오탐·지연
- `reports/eval-<날짜시각>.md`·`.csv` (git 제외. 발표용으로 남길 것은 따로 옮겨 커밋)
- InfluxDB `eval_result` → 성능 검증 대시보드

매칭 규칙(CLAUDE.md 10절): 같은 공격 유형이고 `ts_detected`가 `[ts_start, ts_end + grace]` 안이면 그 run에 매칭. 매칭된 탐지가 있는 run = TP(여러 개여도 1건), 없는 run = FN, 어떤 run에도 안 맞는 탐지 = 오탐.
- run은 `--from`~`--to` 안에서 **시작한** 것을 센다. 구간 끝에 걸친 run의 탐지는 `--to` 뒤 grace까지 찾는다.
- `--from` 전 `EVAL_LOOKBACK_SEC`(1시간) 안에 시작한 run은 세지 않지만, 그 run의 탐지가 오탐으로 세지지 않도록 매칭에는 쓴다.
- **mock 데이터로 낸 숫자는 성능 결과가 아니다.** 리포트와 대시보드에 데이터 출처가 표시된다.

## 녹화 재생하기 (replay) — 발표 시연 백업

collector가 남긴 녹화(`recordings/raw-<날짜시각>.jsonl`)를 다시 보낸다. 테스트베드 시연이 안 될 때 쓴다.

```bash
# 터미널 1: collector (로그에 "녹화 …"가 뜰 때까지 기다린다)
python -m collector.collector
# 터미널 2: 녹화를 지금 시각으로 옮겨 1배속으로 재생 → 실시간 대시보드에 바로 보인다
python -m replay.replay recordings/raw-20261120-100000.jsonl --speed 1 --out udp://127.0.0.1:9999 --retime now
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `file` | (필수) | 녹화 파일 |
| `--speed` | `1` | 배속. `0`이면 기다리지 않음 |
| `--out` | `.env`의 `udp://COLLECTOR_UDP_HOST:COLLECTOR_UDP_PORT` | `udp://host:port` 또는 `file://path` |
| `--retime` | `now` | `now`: 첫 메시지를 지금으로 옮김(간격은 원본 그대로) / `none`: 원본 시각 그대로 / `2026-12-04T14:00:00`: 첫 메시지를 그 시각으로 |

- 메시지는 시각 순으로 정렬해 보낸다. 시각 필드는 모두 같은 만큼 옮기므로 탐지 지연 같은 간격은 원본과 같다.
- 재생한 `attack_run`의 `params`에 `replay` 표시가 붙는다. 실시간 대시보드의 "데이터 출처"가 "녹화 재생"(원본이 mock이면 "mock 재생")으로 바뀌고, evaluator도 이걸로 데이터 출처를 판단한다.
- event_id·run_id는 원본 그대로다. 같은 녹화를 짧은 간격으로 두 번 재생하면 대시보드에 같은 event_id가 두 번 보인다.
- `--speed`를 1보다 크게 하면 메시지 시각이 실제 시각보다 앞서 나간다(원본 간격을 유지하므로). 실시간 대시보드용으로는 `--speed 1`.

**발표 전 준비**: 테스트베드로 시연을 한 번 성공시켜 녹화를 만들어 두고, 그 파일로 재생 리허설을 해 둔다. 녹화는 git에서 제외되므로 따로 백업한다.

## mock 데이터 만들기

실제 eBPF 에이전트·탐지 엔진·공격 도구 대신 쓰는 가짜 데이터 생성기. 숫자(절차 타이밍, 공격 강도, 탐지율, 지연)와 코드표는 전부 [`mock/scenarios.yaml`](mock/scenarios.yaml)에 있다.

지표는 TeleRAN 논문 기준이다: **Table I → eKPM**(UE별 식별자·상태·보안 알고리즘·메시지 ID, 숫자 코드), **Table II → 표준 KPM**(TS 28.552 셀 단위 카운터·통계). 이름과 코드표는 [`schema/SCHEMA.md`](schema/SCHEMA.md) 6절.
mock은 정상 UE 3대의 RRC/NAS 절차(등록·연결·해제·일시 중지·재개·재수립)를 흉내 내고, 같은 절차에서 eKPM(메시지마다)과 KPM(1초 집계)을 함께 뽑는다. 공격 구간에는 공격 절차가 끼어든다.

| 공격 | 표준 KPM | eKPM |
|---|---|---|
| `RRC_SIGNALING_STORM` (5G-Spector의 BTS Resource Depletion) | 연결 시도·성공이 늘고 연결 UE 수가 크게 오름 | 위조 연결마다 다른 C-RNTI로 인증 요청까지 간 뒤 응답 없이 몇 초 만에 해제(transient UE) — 어느 UE가 가짜인지 보임 |
| `ABNORMAL_UE_ATTACH` | 연결 시도가 조금 늘 뿐 | 같은 패턴의 인증 실패·등록 거절, 시도마다 바뀌는 S-TMSI |
| `F1AP_MSG_TAMPER` | 거의 그대로 | 보안 알고리즘이 NEA0/NIA0으로 떨어짐, C-RNTI 불일치 |

> **mock 데이터로 나온 탐지율·지연은 성능 결과가 아니다.** mock이 만든 `attack_run`의 `params`에는 `"generator": "mock"`이 들어간다.

```bash
# 실시간으로 collector(UDP)에 보내기 — 10분, 공격 유형 섞음
python -m mock.generator --scenario mixed --duration 600 --seed 42

# 파일로 10분치 바로 만들기 (--speed 0 = 기다리지 않음)
python -m mock.generator --duration 600 --seed 42 --speed 0 --out file://recordings/mock.jsonl

# 특정 공격만 / 공격 없이 평상시만
python -m mock.generator --scenario RRC_SIGNALING_STORM --duration 120
python -m mock.generator --scenario normal --duration 600
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--scenario` | `mixed` | `mixed`, `normal`, 또는 공격 유형 이름(`RRC_SIGNALING_STORM`, `ABNORMAL_UE_ATTACH`, `F1AP_MSG_TAMPER`) |
| `--duration` | `600` | 시뮬레이션 길이(초) |
| `--seed` | 무작위 | 같은 seed + 같은 `--start`면 출력이 완전히 같다. 생략하면 로그에 쓴 seed가 찍힌다 |
| `--out` | `.env`의 `udp://COLLECTOR_UDP_HOST:COLLECTOR_UDP_PORT` | `udp://host:port` 또는 `file://path` (파일은 덮어씀) |
| `--speed` | `1` | 배속. `0`이면 기다리지 않고 바로 출력 |
| `--start` | `now` | 첫 메시지 시각. 예: `2026-11-20T10:00:00` (시간대 없으면 로컬 시각) |

- `--speed`를 1보다 크게 하면 메시지 시각이 실제 시각보다 앞서 나간다(10배속 10분이면 마지막 메시지는 약 9분 뒤 시각). 실시간 대시보드에서 바로 보려면 `--speed 1`을 쓴다.
- 처음 30초는 평상시이고, 공격 사이에는 40~90초 평상시가 들어간다. 그래서 너무 짧은 `--duration`(예: 60초)에는 공격이 없을 수 있다.
- 10분 mixed(seed 42)는 약 1만 3천 건이다. 대부분 1초 주기 KPM(14개 × 600초)이다.

## 문제 해결

**`permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`**
Docker Desktop의 WSL integration을 켠 직후에는 계정이 `docker` 그룹에 들어가 있어도, 이미 열려 있던 터미널에는 적용되지 않는다.
WSL 터미널을 모두 닫고 다시 열거나, PowerShell에서 `wsl --shutdown` 후 다시 연다.
당장은 `sg docker -c "docker compose up -d"`처럼 실행해도 된다.

**venv 안에서 `pip`가 없거나 `ImportError`가 난다**
venv 생성이 중간에 깨진 경우다. `rm -rf .venv` 후 다시 만든다.

**PC·WSL을 재시작한 뒤 Grafana에 대시보드가 없다 (`Dashboard not found`)**
Docker Desktop이 컨테이너를 자동으로 다시 띄울 때 Windows 디스크(`/mnt/c/...`)의 설정 폴더 마운트가 비어 있는 채로 붙는 경우가 있다.
`docker compose exec grafana ls /etc/grafana/dashboards`가 비어 있으면 `docker compose up -d --force-recreate grafana`로 다시 만든다(데이터는 볼륨에 있어 유지된다).

## 브랜치 규칙

| 브랜치 | 용도 |
|---|---|
| `main` | 배포·발표용. `dev` → `main` PR로만 반영 |
| `dev` | 개발 통합 (default 브랜치) |
| `feat/dashboard-M<n>` | 마일스톤 작업. `dev`에서 만들고 `dev`로 PR |
| `fix/<내용>`, `docs/<내용>` | 작은 수정 |

```bash
git switch dev && git pull
git switch -c feat/dashboard-M3
# ... 작업, 커밋 ...
git push -u origin feat/dashboard-M3   # 이후 GitHub에서 dev로 PR
```

## 메시지 검증

모든 메시지는 [`schema/messages.schema.json`](schema/messages.schema.json)으로 검증한다. Python에서는:

```python
from common.schema import validation_errors
validation_errors({"type": "metric", ...})   # [] 이면 통과, 아니면 사유 목록
```

## 디렉터리

| 경로 | 내용 |
|---|---|
| `reference/` | 참고 논문(TeleRAN, 5G-Spector)과 요약 `README.md` |
| `docs/progress.md` | 마일스톤별 진행 기록, 팀 확인 대기 항목 |
| `schema/` | 메시지 스키마 (사람용 `SCHEMA.md`, 기계용 `messages.schema.json`) |
| `common/` | `.env` 로딩(`config.py`), 스키마 검증·메시지 시각(`schema.py`), UDP·파일 송수신·배속 전송(`transport.py`) |
| `mock/` | mock 생성기(`generator.py`)와 설정(`scenarios.yaml`) |
| `collector/` | 수신 → 검증 → InfluxDB 저장 → raw 녹화 (`collector.py`), 메시지 → InfluxDB 변환(`influx_writer.py`) |
| `evaluator/` | 탐지율·오탐·지연 계산, 리포트(`reports/`)·`eval_result` 저장 (`evaluate.py`) |
| `replay/` | 녹화 데이터 재생 (`replay.py`) |
| `grafana/` | datasource·대시보드 provisioning, 대시보드 JSON |
| `recordings/` | raw 녹화, 거부 로그 (git 제외) |
| `tests/` | pytest |
