# PortRAN Observability — 수집기 · 대시보드 · 검증 파이프라인

이 문서는 Claude Code가 이 저장소에서 작업할 때 따르는 기준이다. 작업 전에 끝까지 읽는다.

**답변은 항상 한국어로 한다.** 대화 답변, 질문 창(질문·선택지·설명 모두), 진행 보고, 문서가 모두 해당한다. 코드 식별자·명령·파일 경로·필드 이름은 원문 그대로 쓴다.

## 0. 작업 시작 전 필수: 참고 논문 읽기

**세션을 시작하면(첫 컨텍스트에서) 코드를 보거나 고치기 전에 `reference/`의 두 논문을 먼저 끝까지 읽는다.** 이 저장소의 지표 정의, 공격 유형, 탐지 규칙, 평가 방식의 근거가 이 논문들이다.

| 파일 | 논문 | 이 저장소에서 쓰는 곳 |
|---|---|---|
| `reference/TeleRAN.pdf` | TeleRAN: eBPF 기반 OpenRAN 텔레메트리 (FutureG 2026) | Table I → KPM1(eKPM), Table II → KPM2(표준 KPM). `schema/SCHEMA.md` 4절(탐지 엔진 레코드와의 대응), 대시보드 |
| `reference/5GSpector.pdf` | 5G-Spector: O-RAN L3 공격 탐지 (NDSS 2024) | MobiFlow 텔레메트리, L3 공격 유형과 탐지 규칙, 탐지 지연·오버헤드 평가 방식 |

- 요약과 이 저장소와의 대응 관계는 `reference/README.md`에 있다. 요약만 읽고 넘어가지 말고 원문을 읽는다.
- 대화가 길어져 요약된 뒤 논문 내용이 필요하면 해당 부분을 다시 읽는다.
- PDF를 읽을 수 없으면(Read 도구가 `pdftoppm`을 못 찾는 경우) 사용자에게 별도 Ubuntu 터미널에서 `sudo apt install poppler-utils`를 실행해 달라고 요청한다.
- 논문과 이 문서의 내용이 다르면 임의로 고르지 말고 사용자에게 묻는다.

## 1. 프로젝트 배경

- 팀 프로젝트: **O-RAN 기반 5G 기지국 위협 탐지 솔루션** (5인, 최종 발표 2026-12-04)
- 전체 파이프라인: eBPF로 기지국 SW(OCUDU CU/DU) 무수정 텔레메트리 수집 → 보안 지표 eKPM으로 가공 → 룰 기반 탐지 엔진(C++) → 대시보드
- 테스트베드: OAI nrUE ↔ USRP B210 ↔ OCUDU(CU/DU 분리) ↔ Open5GS, FlexRIC(E2SM-KPM)
- 프로젝트 핵심 주장: **표준 KPM만으로는 못 잡는 위협을 eKPM + 룰로 탐지한다.** 대시보드와 검증은 이 주장을 숫자와 화면으로 보여주는 역할이다.

### 1.1 테스트베드 환경 두 곳 = 대시보드의 데이터 출처

원본 그림: [`docs/images/아키텍쳐.png`](docs/images/아키텍쳐.png). 아래는 그 내용을 글로 옮긴 것이다.

```
┌ AWS · 서울 리전(ap-northeast-2) ─────────────────────────────────────────┐
│ 골든 AMI(공통 설치 이미지) ──복제──> 사람마다 CU·DU 세트 하나              │
│                                                                           │
│ ┌ 보안 그룹 — 내 CU·DU만 묶고 다른 세트와 격리 ─────────────────────────┐ │
│ │ SSH(22)는 내 IP만 허용, 세트 안(CU ↔ DU)은 자유 통신                   │ │
│ │                                                                        │ │
│ │  CU 인스턴스 (c6i.xlarge)   ◀── F1 / E2 ──▶   DU 인스턴스 (c6i.2xlarge)  │ │
│ │  CU · RIC · 5G Core                            DU · UE(단말)            │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
│ 사설 IP는 고정(F1·E2에 사용), 공인 IP는 껐다 켜면 바뀜                       │
└───────────────────────────────────────────────────────────┬───────────────┘
                                                            ├──> 대시보드
┌ On-Premise · 연구실 ─────────────────────────────────────┐ │
│ 실물 테스트베드 (노트북 여러 대 + 무선 장비)                ├─┘
└───────────────────────────────────────────────────────────┘
```

| 출처 | 무엇 | `X-Env` | 대시보드 선택지 | 지금 |
|---|---|---|---|---|
| **AWS** | 위 CU·DU 세트. 탐지 쪽이 실험에 쓰는 세트가 `p4`이고, 그 CU 인스턴스는 탄력적 IP `43.202.191.147`로 공인 IP가 고정돼 있다(27_ §3) | `p4` | AWS | **받는다** |
| **On-Premise** | 연구실 실물 테스트베드(실험 노트북) | `lab` | On-Premise (선택지만 있음) | 나중 (2026-11-09 사용자 결정 — 우선 AWS만) |

- 분석 엔진(eBPF)·탐지 엔진·전송기는 CU 인스턴스에서 돈다(27_ §9 R5 "p4 CU 박스"). 전송기가 HTTPS `POST /ingest`로 **대시보드 EC2**(테스트베드 세트와 별개, t3.small, `docs/deploy.md`)에 보낸다.
- 두 출처는 같은 대시보드에서 데이터 출처 선택(`env` 태그)으로 고른다. 설계는 `docs/dashboard-design.md` 1절.

## 2. 이 저장소의 범위 (내 담당)

처음에는 다른 팀원 담당(공격 도구, eBPF 에이전트, 탐지 엔진)이 없어서 mock 생성기로 먼저 개발했다(M1~M7). 탐지 엔진 출력 형식이 확정되어(2026-11-05, 5절) 실제 경로로 바꿨고(M8~M10), mock 생성기·evaluator와 처음 메시지 형식은 M10에서 지웠다. 수집 오버헤드는 탐지 쪽 형식(11/13)으로 M11에서 바꿨다.

```
분석 엔진(eBPF) ─> 탐지 엔진 ─> 전송기 ─HTTPS POST /ingest─> nginx(TLS) ─> collector ─> InfluxDB ─> Grafana (관제·성능)
                                                                                  │
                                                       raw 녹화(.jsonl) <─────────┘──> replay ─> /ingest (시연·백업)
```

eBPF 에이전트(분석 엔진)는 대시보드로 직접 보내지 않는다. 탐지 엔진이 받은 줄 가운데 상시 KPM2(`kpm2` 3초 묶음)·`hello`·`f1_evt`·수집 오버헤드(`overhead`, 3초)를 경보(`alert`·`evidence`·`gap`)와 같은 전송기로 보낸다. 공격 정답 기록은 받지 않는다(5.1절).

포함하는 것:
1. 메시지 스키마 정의 (팀 공용 기준 문서)
2. collector (수신 → 검증 → InfluxDB 저장 → raw 녹화)
3. Grafana 대시보드 2개 (관제, 성능)
4. replay (녹화·샘플을 지금 시각으로 다시 보내기 — 개발·시연 데이터, 발표 시연 백업)
5. AWS 배포 · CI/CD (M7·M9). AWS에는 대시보드 스택만 올린다. 절차는 `docs/deploy.md`
6. 평가(탐지율·오탐·지연)는 전체 파이프라인 완성 뒤 탐지 쪽과 방식을 정해 다시 만든다(27_ §9)

포함하지 않는 것: 탐지 로직, eBPF 코드, 공격 코드, 기지국 제어(대응)

## 3. 기술 스택

| 구분 | 선택 |
|---|---|
| 언어 | Python 3.10+ |
| 의존성 | `influxdb-client`(InfluxDB 2.x용), `pyyaml`, `jsonschema`, `pytest` |
| DB | InfluxDB 2.7 (Docker), 타임스탬프 precision = ns |
| 시각화 | Grafana OSS (Docker), datasource와 대시보드는 **provisioning 파일로 코드화** |
| 실행 | `docker compose` (InfluxDB + Grafana), Python 프로그램은 호스트에서 실행. AWS 배포만 collector 등도 컨테이너로 띄운다(`docker-compose.aws.yml`, M7) |

- Docker 이미지는 `latest` 대신 고정 버전 태그를 쓴다.
- 접속 정보(토큰, org, bucket, 포트, Slack Webhook)는 `.env`로 관리하고 `.env.example`만 커밋한다.

## 4. 디렉터리 구조

```
.
├── CLAUDE.md
├── README.md                     # 실행 방법 (처음 보는 팀원 기준)
├── .claude/                      # Claude Code 설정 (12절 10·11항, 설명은 docs/agent-workflow.md)
│   ├── settings.json             # hook 등록: 모든 작업 이벤트 → agent_log.py, 읽기 전용 역할의 Bash → readonly_guard.py
│   ├── hooks/agent_log.py        # 작업 기록기(logs/agent/<세션 ID>.jsonl, 비밀 값 가림)이자 보기 도구(list·show·errors)
│   ├── hooks/readonly_guard.py   # researcher·planner·reviewer가 Bash로 파일·git 상태를 바꾸지 못하게 막음
│   └── agents/                   # 역할별 서브에이전트: researcher.md · planner.md · reviewer.md
├── logs/agent/                   # Claude Code 작업 기록 (.gitignore)
├── reference/                    # 참고 논문 (0절). 작업 전에 읽는다
│   ├── README.md                 # 논문 요약, 이 저장소와의 대응 관계
│   ├── TeleRAN.pdf
│   ├── 5GSpector.pdf
│   └── detection/                # 탐지 엔진 담당 명세 27_(레코드 형식 기준, 5절)와 샘플 분석표
├── docs/
│   ├── progress.md               # 마일스톤별 진행 기록 (12절 8항)
│   ├── agent-workflow.md         # AI 작업 흐름: 역할 분리 · 작업 기록 (12절 10·11항, 사람용 설명)
│   ├── deploy.md                 # AWS(EC2) 배포 절차 (M7·M9)
│   └── dashboard-design.md       # 관제·성능 대시보드 설계도 (M10, 데이터 출처 선택 AWS / On-Premise — 우선 AWS만)
├── .github/
│   └── workflows/
│       ├── ci.yml                # CI: PR마다 전체 테스트 (M7)
│       └── deploy.yml            # CD: main push 시 EC2 배포 (M7)
├── deploy/                       # CD용 서버 스크립트(server-deploy.sh)와 AWS 설정 JSON(aws/) (M7),
│                                 #   /ingest 앞단 nginx 설정(nginx/)과 인증서 스크립트(ingest-cert.sh) (M9)
├── docker-compose.yml
├── docker-compose.aws.yml        # AWS 배포용 override: collector 컨테이너화, 내부 포트 잠금 (M7)
├── Dockerfile                    # AWS 배포용 Python 이미지 (M7)
├── .env.example
├── requirements.txt
├── schema/
│   ├── SCHEMA.md                 # 팀 공유용 스키마 설명 (사람이 읽는 문서)
│   └── messages.schema.json      # JSON Schema (기계 검증용, 단일 기준)
├── common/
│   ├── config.py                 # .env 로딩
│   ├── schema.py                 # 스키마 검증 (collector·replay·테스트 공용)
│   └── transport.py              # UDP / 파일 송수신 공통 코드
├── collector/
│   ├── collector.py
│   ├── ingest.py                 # POST /ingest HTTP 수신, 중복 키 (M8)
│   └── influx_writer.py
├── replay/
│   └── replay.py
├── grafana/
│   ├── provisioning/datasources/influxdb.yml
│   ├── provisioning/dashboards/dashboards.yml
│   ├── provisioning/alerting/portran.json   # Slack 알림 규칙·연락처·템플릿 (M12, build.py가 만든다)
│   ├── build.py                  # 대시보드 JSON 생성기 (JSON은 이것으로만 고친다, M10)
│   ├── query_timing.py           # 대시보드 쿼리를 실제 Grafana에 보내 시간·오류·점 수를 잰다 (읽기 전용, D202)
│   ├── rule-names.json           # 룰 ID → 공격 이름 (27_ §5.3)
│   └── dashboards/{monitoring.json, performance.json}   # 관제·성능 (grafana/build.py가 만든다)
├── recordings/                   # raw 녹화 (.gitignore)
└── tests/
    └── data/detection/           # 탐지 쪽 경보 경로 샘플 32개 (11/05, 지금 탐지 엔진 코드 출력)
        data/overhead/            # 탐지 쪽 overhead 실제 출력 30줄 (11/13, M11)
        test_dashboard_flux.py    # 대시보드 Flux를 실제 InfluxDB 임시 bucket에서 돌려 값 확인 (D202)
```

## 5. 메시지 스키마

스키마의 단일 기준은 `schema/messages.schema.json`이다. collector, replay, 테스트 모두 이 파일로 검증한다. 사람이 읽는 설명은 `schema/SCHEMA.md`(v0.5).

| 갈래 | `type` | 보내는 곳 | 기준 |
|---|---|---|---|
| **탐지 엔진 레코드** | `alert` · `evidence` · `gap` · `kpm2` · `hello` · `f1_evt` | 탐지 엔진 전송기 → HTTPS `POST /ingest` | 탐지 엔진 담당 명세 `reference/detection/27_탐지엔진_1-4단계-대시보드-지표_명세서.md`(2026-11-05 확정, 이하 27_). **형식은 27_ 그대로 받는다** |
| **수집 오버헤드** | `overhead` | 분석 엔진(계측기)이 3초마다 → 전송기 → HTTPS `POST /ingest` | 탐지 쪽이 11/13에 보낸 형식(27_ 밖, R5). `schema/SCHEMA.md` 6절(M11) |

공통 규칙:
- 전송 단위: **JSON 한 줄 = 메시지 하나** (JSON Lines, UTF-8)
- 모든 레코드(`overhead` 포함): 시각은 **Unix epoch 밀리초 정수**(분석 엔진이 붙인 데이터 시각). 모르는 필드는 받고(녹화에 남기고 화면에서 무시), `alert.fmt`·`kpm2`·`hello`·`f1_evt`·`overhead`의 `ver`가 1이 아니면 거부한다. `null`은 "모름"이다.
- v0.4까지 `overhead`만 쓰던 규칙(ns 시각, 모르는 필드 거부, UDP)은 v0.5(M11)에서 없앴다. UDP·파일 입력은 시험용으로 남아 있다.

### 5.1 탐지 엔진 레코드 (27_)

| `type` | 뜻 | 언제 오나 | 27_ |
|---|---|---|---|
| `alert` | 경보 생애 `raise` → `update` → `clear`/`end`. 룰 13개, 단계 1~4, `kind` `attack`·`anomaly` | 늘 | §5 |
| `evidence` | 경보 근거. `raw`에 분석 엔진의 원본 줄(1단계 100 ms `kpm2`, 2~4단계 `ue_evt`)을 그대로 담음 | 늘 | §6 |
| `gap` | 경보 중 그 셀의 `kpm2`가 끊긴 구간 | 늘 | §6.4 |
| `kpm2` | 상시 KPM2 — 셀마다 3초(`agg_ms`)로 묶은 Table II 카운터 | 전송기 설정으로 켤 때 (실험 때 켬) | §4.1 |
| `hello` | 분석 엔진 접속 = 새 `session` 시작 | 위와 같음 | §4.3 |
| `f1_evt` | DU·CU 재시작 | 위와 같음 | §4.3 |

```json
{"type":"alert","fmt":1,"alert_id":"S1-L3-01-V-1-65","event":"raise","rule":"L3-01-V","stage":1,"unit":"cell","kind":"attack","cell":1,"t":1792209006400,"severity":"medium","mode":"normal","cond":["C1","C2","C2a"],"candidates":["L3-11"],"values":{"a_w":13,"f_w":12,"ratio":0.9230769230769231,"base":1.0,"sigma":0.0},"params":{"z":3.0,"theta":0.5,"f_abs_frac":0.1,"f_abs":10},"refs":{"a":[46,55],"f":[56,65]}}
```

- **KPM2 = TeleRAN Table II**(셀 카운터): `kpm2`의 `cc`·`si` 키가 Table II 14개 이름 그대로다(+ 탐지 쪽 확장 `ext` 3개). **KPM1 = Table I**(UE별, 팀 용어 eKPM): `ue_evt` 한 줄 = UE 메시지 하나. **상시로는 오지 않고** 경보 근거(`evidence.raw`)로만 온다. 탐지 엔진이 이것으로 2~4단계를 판정하고, 대시보드는 판정 결과(`alert`)와 근거(`evidence`)를 보여 준다. `ue_evt` 형식은 `schema/SCHEMA.md` 3.7절(타임라인 필드 7개만 검사), Table I·II 대응표는 4절.
- 받는 방법(`/ingest`·`X-Env`·응답 코드·중복 키)은 8절과 `schema/SCHEMA.md` 2절.
- `alert`에는 `session`이 없다. 같은 `alert_id`의 첫 `evidence`의 `raw.session`이 그 경보의 세션이다(27_ §7).
- 평가 결과(R1 `eval`·R2 `eval_run`)·경보별 지연(R3)은 전체 파이프라인(분석 엔진 → 탐지 엔진 → 대시보드, 실제 공격)이 완성된 뒤 탐지 쪽과 함께 정한다(27_ §9).

### 5.2 overhead — 수집 오버헤드 (M11)

분석 엔진(계측기)이 `kpm2`·`ue_evt`·`f1_evt`와 같은 소켓·번호열(`session`·`seq`)로 3초 구간(`t_start_ms`~`t_end_ms`)마다 한 줄 낸다. 노드 CPU(`count`·`node_busy_cores` — 바쁜 코어 수 평균)·메모리(바이트), 계측기 프로세스 몫(`process_cores`·`process_rss_bytes`, `process_scope: self`), 선언한 NIC별 F1·N2 패킷·바이트 증가분(`link[]`). `node_id`는 `cu`로 통일(11/13, AWS 실제 값은 `p4-cu` — 화면에는 둘 다 CU로, D192). 점유율(%)은 보내는 쪽이 나누지 않고 화면이 계산한다. 필드·예시는 `schema/SCHEMA.md` 6절. 처음 스키마의 `metric`·`detection`·`attack_run`(mock 전용)은 M10에서, 옛 `overhead` 형식(ns `ts`·`ebpf_on`·`cpu_pct`·`mem_mb`)은 M11에서 지웠다.

## 6. InfluxDB 매핑

탐지 엔진 레코드 (ms 시각을 ns로 바꿔 씀):

| measurement | time | tags | fields |
|---|---|---|---|
| `alert` | `t` | env, alert_id, rule, stage, kind, event, cell | severity, mode, unit, fmt, branch, reason, ues_total, duration_ms, evidence_sent, evidence_dropped, session, rep_key, rep_value, `<cond·candidates·conditions·values·params·refs·ues>_json` |
| `evidence` | `raw.t_ms`(또는 `raw.t_start_ms`) + `seq` | env, alert_id, phase, raw_type, cell, session | seq, du_ue_id, uid, raw_json, (KPM1) msg·dir·proto, (KPM2) `cc.*`·`si.*`·`ext.*` |
| `gap` | `t_from` | env, alert_id, cell | t_to, seq_from, seq_to, session |
| `kpm2` | `t_start_ms` | env, session, cell, agg_ms | t_end_ms, n, seq_from, seq_to, partial_json, `cc.<이름>[.<하위 키>]`·`si.<이름>`·`ext.<이름>` |
| `hello` | 받은 시각 | env, session | seq, producer, node_id, clock, period_ms, noreply_timeout_ms, si_sample_ms, ue_evt, cells_json |
| `f1_evt` | `t_ms` + `seq` | env, session | seq, msg, cells_json, du_ue_ids_json |

- `env` = `X-Env`(UDP·파일 입력은 collector `--env`). 환경마다 데이터가 갈린다. 대시보드의 데이터 출처 선택은 AWS(`p4`)·On-Premise(`lab`)·재생(`replay`)·샘플(`sample`)이다. On-Premise는 선택지만 있고 **지금은 AWS만 받는다**. 단계 비교(`p4` vs `replay-kpm-only`)는 대시보드에서 없앴다(11/13).
- **같은 series·같은 시각이면 InfluxDB가 덮어쓴다.** 그래서 다른 레코드끼리 겹치지 않게 정했다: 같은 ms의 여러 줄은 ns 자리의 `seq`로, 두 경보에 함께 실린 같은 원본 줄은 `alert_id` tag로 가른다. 같은 줄을 다시 쓰면 같은 점에 덮어써져 결과가 그대로다.
- `alert_id`는 값마다 고유하지만 tag로 둔다(아래 원칙의 예외). 경보는 공격마다 하나라 series 수가 경보 수에 비례하는 정도이고, 위의 덮어쓰기를 막는 데 필요하다.
- `kpm2` 지표는 모두 실수로 쓰고 `null`은 뺀다(그래프에서 '데이터 없음'). 룰마다 다른 묶음(`values`·`params`·`ues`)은 JSON 문자열로 통째 저장한다(27_ §7.1).
- 대표 값 `rep_value`는 27_ §5.3의 룰별 '대표 값', 판정 보류 경보는 `held_w`.

`alert_ue` (걸린 UE 한 칸 = 점 하나, `ues_json`을 행으로 그리려고 따로 둠, M10): time `ues[].t_hit`, tags env·alert_id·ue(`<cell>-<du_ue_id>-<uid>`), fields cell·du_ue_id·uid·cu_ue_id·crnti·s_tmsi·cond·uncertain·conditions·peers·seq_from·seq_to·evidence·values_json·event.

| measurement | time | tags | fields |
|---|---|---|---|
| `overhead` | `t_start_ms` | env, session, node(`node_id`) | t_end_ms, seq, process_scope, cpu_count, node_busy_cores·process_cores(늘 실수), mem_total_bytes·mem_used_bytes·process_rss_bytes |
| `overhead_link` | `t_start_ms` | env, session, node, iface, role | t_end_ms, seq, ingress_sctp_packets, ingress_wire_bytes, egress_sctp_packets, egress_wire_bytes |

- `overhead_link`: `link[]` 한 칸(NIC 하나) = 점 하나(`alert_ue`와 같은 이유). 값은 구간 증가분 그대로, 초당 값은 화면에서 구간 길이로 나눈다. `null`·빈 객체·키 없음은 필드를 뺀다.

- 값마다 고유한 것은 원칙적으로 tag로 두지 않는다(cardinality 폭증 방지). `alert_id`·`alert_ue.ue`는 위의 이유로 예외다.

## 7. 개발·시연 데이터

mock 생성기는 M10에서 지웠다. 화면 개발·시연에는 아래 데이터를 쓴다.

| 데이터 | 어디에 | 쓰는 법 |
|---|---|---|
| 탐지 쪽 샘플 32개 (경보 경로, 탐지 엔진 실제 코드 출력·합성 입력) | `tests/data/detection/` | `python -m replay.replay tests/data/detection/*.jsonl --env sample --speed 0 --retime <시각>` |
| collector 녹화 (실측·연동 시험) | `recordings/raw-<시각>-<환경>.jsonl` | `python -m replay.replay recordings/raw-…-p4.jsonl --env replay` |
| 실측 | `X-Env: p4` | 탐지 쪽 전송기 |

- 샘플·재생 데이터는 `X-Env`를 `sample`·`replay`로 보내 실측(`p4`)과 섞지 않는다. 대시보드의 데이터 출처 선택(AWS / On-Premise / 재생 / 샘플)이 이 값으로 거른다.
- 상시 KPM2(`kpm2` 3초 묶음) 샘플은 저장소에 없다(연동 시험 때 서버 녹화에만 있음, progress Q19).

## 8. collector 요구사항

- UDP, 파일(tail -f 방식), HTTP `POST /ingest` 입력을 지원한다. HTTP는 탐지 엔진 전송기용이고 TLS는 앞단이 맡는다(collector는 서버 안에서 평문으로 받음).
- 메시지마다 JSON Schema로 검증하고, 실패한 메시지는 버리지 말고 `recordings/rejected.jsonl`에 사유와 함께 남긴다.
- 정상 메시지는 원본 그대로 녹화한다(replay용). 모든 레코드를 환경별로 `recordings/raw-<날짜시각>-<환경>.jsonl`에.
- `/ingest` 약속(27_ §3, 대시보드 2차 답변서 D1~D3, `schema/SCHEMA.md` 2절):
  - 헤더 `X-Env`를 환경으로 저장한다(없으면 `unknown`). 토큰은 쓰지 않는다(HTTPS + 보안 그룹 IP 제한).
  - **원본 녹화와 InfluxDB 저장이 끝난 뒤에** 답한다. `200 {"accepted","rejected","duplicates"}`(틀린 줄은 거부 로그로 보내고 나머지는 저장), 본문을 못 읽으면 `400`, 상한(1 MiB)을 넘으면 `413`, InfluxDB 일시 장애면 `503`(그 요청은 아무것도 반영하지 않음 — 전송기가 다시 보냄).
  - 다시 보낸 줄은 환경 + 레코드별 중복 키로 걸러 한 번만 저장한다.
- InfluxDB에는 배치로 쓴다(예: 500건 또는 1초마다).
- 종료(Ctrl+C) 시 남은 배치를 flush한다.
- 1초마다 수신·저장·거부 건수를 로그로 출력한다.

## 9. Grafana 대시보드

datasource와 대시보드 모두 provisioning으로 띄운다. `docker compose up` 한 번으로 대시보드까지 떠야 한다. 대시보드 JSON은 `grafana/dashboards/`에 커밋한다.

- **대시보드 JSON은 `grafana/build.py`로 만든다.** 손으로 고치지 않는다(`python grafana/build.py`로 다시 쓰고, 테스트가 `--check`로 커밋된 JSON과 같은지 본다). 룰 ID → 공격 이름은 `grafana/rule-names.json`(27_ §5.3).
- 설계(패널마다 답하는 질문과 쓰는 레코드, 데이터 없음 처리)는 `docs/dashboard-design.md`.
- 모든 쿼리는 데이터 출처 변수 `source`(= `env` 태그)로 거른다. 선택지: AWS(`p4`)·On-Premise(`lab`, 아직 받지 않음)·재생(`replay`)·샘플(`sample`).

### 9.1 관제 (`monitoring.json`, uid `portran-monitoring`), 새로고침 5초
| 행 | 패널 |
|---|---|
| 탐지 결과 | 고른 시간 범위에 시작한 경보: 공격별 경보 수(막대), 경보 길이 분포, 공격별 경보 결과 표. 요약 줄 대신 성능에서 옮김(11/16) |
| KPM (상시 KPM2) | 셀별 3초 연결 시도·성공·무응답 막대, UE 컨텍스트·연결 UE 수(셀 한도 96). 긴 시간 범위는 3초 배수 구간으로 묶는다(막대 합, UE 수 최대·평균 선은 평균, 11/18). 경보 구간·gap·칸 일부 없음·세션 시작 주석. 경보 구간 어디에 마우스를 대도 툴팁에 경보(그래프에 안 그리는 계열 refId B, 11/18) |
| 경보 목록 | 경보 하나 = 한 행(시작·셀·룰·공격 이름·종류·심각도·UE 수·대표 값·상태·길이). 행을 누르면 경보 상세로. 표가 한 줄 가득(룰별 경보 수 막대는 11/16에 없앰) |
| 경보 상세 | 변수 `alert_id`. 판정 요약, 판정 근거 값(cond·candidates·conditions·values·params·refs), 후보 공격, 걸린 UE(`alert_ue`), 근거 KPM(근거 KPM2 100 ms, 셀 지표 경보), UE_EVENT — UE별 메시지 흐름·메시지 흐름 상세(근거 KPM1 `ue_evt`, UE 메시지 경보). 줄·패널 제목은 짧게(11/16) |

변수: `source`, `cell`, `alert_id`(위쪽 칸은 숨김 — 경보 목록 행을 눌러 고른다, 11/16). 그래프 위 주석은 늘 켜 두고 토글을 숨긴다(11/16). 상태 불명 = 열린 경보에 마지막 레코드 뒤 1단계 15초·2~4단계 90초 동안 아무것도 없음(27_ §7). 화면에는 단계(1~4)를 표시하지 않는다(11/13 — 열·제목에서 뺌, 판정 기준에만 씀). 공격 이름은 두 대시보드 모두 짧은 이름(`grafana/build.py` `short_rule_name` — '#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈').

Flux 주의(InfluxDB 2.7): `pivot`은 경보마다 필드 구성이 달라 표 모양이 갈리므로 경보 합치기에는 쓰지 않는다. `reduce` 결과에 `join.left`를 쓰면 실패하고, `map` 결과에 그대로 옮긴 열이 하나도 없으면 조건식 값이 null이 된다(`grafana/build.py` 주석). **정렬은 `map` 앞에서, 원래 열로 한다** — `map`으로 만든 열로 `sort`하면 줄이 빠진다(관제 경보 목록에서 해제된 경보가 빠졌음, M11). `range`의 start와 stop은 같은 기준으로 준다 — 화면 시간 범위(`v.timeRangeStart`~`v.timeRangeStop`)끼리, 또는 지금 기준(`-5m`~`now()`)끼리. 섞으면 지난 범위를 골랐을 때 start > stop이 되어 `cannot query an empty range`로 패널이 깨진다(`tests/test_dashboards.py`가 검사). `map`이 만든 열은 순서가 정해져 있지 않으니, 표 패널에는 반드시 `column_order()`로 열 순서를 박는다(안 하면 새로고침마다 열이 뒤섞인다, 테스트가 검사).

긴 시간 범위(11/18, D202 — 관제 KPM이 7일에서 시간 초과·점 수 초과로 비었음):
- `range` 바로 뒤 `filter`에는 `contains()`를 쓰지 않는다 — InfluxDB가 저장소에서 거르지 못해 데이터를 다 읽는다(7일 30초 초과). 셀은 정규식 `r.cell =~ /^${cell:regex}$/`. 열끼리 비교(`r._value * 100 < int(v: r.agg_ms)`)도 저장소에서 안 되니 고정값으로 거른다. 한 `from`을 변수로 받아 두 갈래로 나눠 쓰지 말고 갈래마다 `from`을 둔다(같은 이유, 7일 15초). `test_storage_filters_have_no_contains`가 검사.
- 상시 KPM2·overhead 원본(3초 칸)을 그리는 시간 그래프·주석은 `aggregateWindow(every: win, …)`로 묶는다. `win`은 `v.windowPeriod`를 3초 배수로 올린 값(`grafana/build.py` `WINDOW`), 묶기는 `range`·`filter` 바로 뒤(저장소에서 계산)에 두고, 세션 series는 `group` 뒤 한 번 더 묶는다(`window_by`). 원본을 다 가져오면 Grafana가 프레임당 maxDataPoints × 10행에서 자른다(`too many datapoints`). `test_raw_series_are_windowed`가 검사.
- 선은 빈 구간을 null 행으로 남겨 끊는다 — 마지막에 `aggregateWindow(fn: mean, createEmpty: true)`(값은 그대로). `max` 같은 선택 함수에 `createEmpty: true`를 주면 느리다(7일 1~2초). 계산식에서 null을 내려면 `import "internal/debug"`의 `debug.null(type: "float")`(Flux에는 null 값 문법이 없다). `insertNulls`는 고정 ms라 묶은 구간 길이를 몰라 쓰지 않는다.
- 관제는 5초마다 새로고침하고 새로고침은 진행 중인 쿼리를 취소한다 — 7일 범위도 패널마다 5초 안이어야 화면에 나온다(패널의 쿼리 A·B는 한 요청에서 차례로 돌아 시간이 더해진다). 경보 요약(`alert_summary`)은 경보 tag마다 series라 읽는 필드 수에 비례해 느려지니, 대표 값·UE 수가 필요 없는 곳은 `fields=("severity", "reason")`처럼 줄인다. 바꾼 쿼리는 배포 전에 `python grafana/query_timing.py --url http://<탄력적 IP>:3000 --source p4 --range 7d --parallel`로 잰다(읽기만, 저장소의 JSON을 보냄).

### 9.2 성능 (`performance.json`, uid `portran-performance`), 새로고침 1분, 기본 최근 24시간
`docs/dashboard-design.md` 3절. **CU 자원**만 남았다(줄 제목 'Overhead', 11/16)(수집 오버헤드, M11 — Beszel식 2열): 노드(코어·메모리·마지막 수신), 고른 범위 요약(평균·최대 CPU %, 최대 메모리 %, 분석 엔진 평균 코어·최대 RSS), CPU 사용률, CPU 내역(분석 엔진 + 그 밖, 쌓기), 메모리 사용량, 메모리 내역, F1·N2 SCTP 트래픽(바이트/초)·패킷(패킷/초 — 링크 값은 SCTP 시그널링만, 범례 'F1 들어옴 (DU → CU)'), CPU 사용률 · RRC 연결 시도(CPU % + RRC 연결 시도 막대, 오른쪽 범례 표에 평균·최대). 시간 그래프는 긴 시간 범위에서 3초 배수 구간의 평균(연결 시도는 합, 11/18). 변수: `source`, `cell`(CPU 사용률 · RRC 연결 시도의 RRC 연결 시도만). 단계 비교(1~4단계 vs 1단계만)와 '파이프라인 완성 뒤' 자리는 없앴고(11/13), 탐지 결과 줄(공격별 경보 수, 경보 길이, 공격별 경보 결과)은 관제 맨 위로 옮기고(종류별 경보 수는 없앰) 경보·입력 품질 줄(경보가 어떻게 끝났나·근거 손실·gap·상시 KPM2 칸 채움·일부만 측정된 지표)은 없앴다(11/16). 탐지율·오탐·탐지 지연은 파이프라인 완성 뒤 탐지 쪽과 정한다(27_ §9).

### 9.3 Slack 알림 (M12, Grafana Alerting)
알림 규칙·연락처·메시지 템플릿을 provisioning(`grafana/provisioning/alerting/portran.json`)으로 띄운다. 이 파일도 `grafana/build.py`가 만든다(경보 상태 계산·짧은 공격 이름을 대시보드와 같게).
| 규칙 | 언제 | Slack |
|---|---|---|
| 공격 경보 (AWS) | AWS(p4)의 공격 경보(`kind` `attack`)가 열리면(`raise`·`update`) 울리고, `clear`·`end`가 오면 끝 | 발생: 공격 이름·셀·심각도·시작 시각(KST)·경보 상세 링크 / 끝: 해제·강제 종료·끝 소식 없음(6시간 안에 끝이 안 옴) |
| 수집 멈춤 (AWS) | 마지막 레코드(상시 KPM2·오버헤드·경보·근거·hello) 뒤 5분 넘게 아무것도 없을 때. 최근 1시간에 아무것도 없으면(테스트베드를 끈 것) 울리지 않음 | 멈춤만 알리고 다시 들어올 때는 알리지 않음 |

- 10초마다 조회한다. 알림 하나 = 경보 하나(`group_by alert_id`), 같은 알림 다시 보내기 24시간.
- 이상 유형·판정 보류 경보, 재생·샘플·On-Premise 데이터는 알리지 않는다(11/13 사용자 결정). On-Premise는 받기 시작하면 더한다.
- Webhook 주소는 `.env`의 `SLACK_WEBHOOK_URL`(비밀 값, 서버 `.env`에만). 비어 있으면 아무 데도 안 가는 주소로 두어 전송 실패 로그만 남는다. 링크 앞부분은 `GRAFANA_ROOT_URL`(Grafana `root_url`).
- provisioning 파일은 환경변수를 바꿔 넣으므로 템플릿·주석에 `$`를 쓰지 않는다(`.CommonLabels`·`.Values`만). 조회 결과가 없을 때 템플릿이 깨지지 않게 `.Values`는 `{{ with .Values }}` 안에서만 쓴다.

## 10. 평가 (보류)

처음 evaluator(정답 기록 `attack_run`과 `detection`을 맞춰 탐지율·오탐·지연 계산)는 M10에서 지웠다. 정답 기록을 대시보드로 받지 않기로 했고(11/04), 평가 결과(R1 `eval`·R2 `eval_run`)·경보별 지연(R3)은 전체 파이프라인(분석 엔진 → 탐지 엔진 → 대시보드, 실제 공격)이 완성된 뒤 탐지 쪽과 함께 정한다(27_ §9). 정해지면 이 절을 다시 쓴다.

## 11. replay 요구사항

```bash
python -m replay.replay recordings/raw-<시각>-p4.jsonl --env replay            # 지금 시각으로 옮겨 로컬 collector로
python -m replay.replay tests/data/detection/*.jsonl --env sample --speed 0 --gap-sec 30
python -m replay.replay a.jsonl --out https://3.39.170.31/ingest --ca certs/ingest.crt
python -m replay.replay recordings/raw-<시각>-p4.jsonl --from 2026-11-11T15:08 --to 2026-11-11T15:14   # 구간만
```
- 탐지 엔진 레코드를 `/ingest`로 다시 보낸다(전송기처럼 500줄·1 MiB 묶음, 413이면 나눠서, 503이면 다시). `X-Env` 기본 `replay`.
- `--retime now`(기본): 첫 레코드를 지금으로 옮긴다. 이동량은 `kpm2` 칸 길이의 배수(3초 칸 경계 유지). 재생마다 `session`·`alert_id` 끝에 재생 표시(`~r<시각>`)를 붙여 여러 번 재생해도 따로 저장된다. `--retime none`이면 원본 그대로(이미 있는 줄은 중복으로 걸러짐).
- 파일 순서를 지키되 보내는 시각이 거꾸로 가지 않게 한다(경보 `raise` 직후 그 경보의 `pre` 근거). 여러 파일은 `--gap-sec` 간격으로 이어서.
- `--from`/`--to`: 원본 데이터 시각이 `[from, to)`인 것만. 경보는 통째로 고른다 — 구간 안에서 시작한 경보는 구간 밖 근거·`clear`까지, 구간 전에 시작한 경보는 모두 뺀다(앞뒤가 잘린 경보를 만들지 않음). `hello`는 다음 줄 시각을 쓴다.
- 시간대 없이 적은 시각(`--retime`·`--from`·`--to`)은 **한국 시각(KST)** 이다. 컨테이너 시계(UTC)와 상관없이 Grafana 화면 시각을 그대로 쓴다.
- 발표 당일 테스트베드 시연이 실패할 경우의 백업용이다.

## 12. 작업 원칙

1. **마일스톤 단위로 진행한다.** 한 마일스톤이 끝나면 멈추고, `docs/progress.md`를 갱신하고, 한 일·실행 방법·확인 결과를 보고한 뒤 다음으로 넘어간다. 커밋은 사용자 확인을 받고 마일스톤 단위로 한다.
2. **스키마(5절)를 바꿔야 하면 먼저 묻는다.** 다른 팀원들과 합의된 기준이라 임의로 바꾸지 않는다.
3. 숫자(임계값, 확률, 범위, 포트)는 설정 파일이나 `.env`로 뺀다.
4. 핵심 로직(스키마 검증, InfluxDB 변환, `/ingest` 요청 처리·중복 제거, replay 시각 옮기기, 대시보드 생성)은 pytest로 테스트한다. 대시보드 쿼리는 실제 InfluxDB·Grafana에서 실행해 확인한다.
5. 실행 방법이 바뀌면 README.md를 같이 고친다.
6. 모르는 것(예: UE ID 형식, 상태 코드표)은 추측해서 확정하지 말고 TODO로 표시한다.
7. **샘플·재생 데이터로 나온 숫자는 성능 결과가 아니다.** 화면·리포트에 데이터 출처(AWS 실측 / 재생 / 샘플)를 표시한다.
8. **진행 기록은 `docs/progress.md`에 남긴다.** 대화로만 보고하면 세션이 끝날 때 사라지므로, 사용자가 나중에 문서로 확인할 수 있게 한다. 마일스톤마다 아래 항목을 쓴다.
   - **한 일**: 만들거나 바꾼 파일과 그 역할
   - **결정 사항**: 이 문서에 정해져 있지 않아 직접 정한 것. 결정, 이유, 팀원 확인 필요 여부(필요하면 대상 파트)를 함께 적는다
   - **확인 결과**: 실행한 명령과 결과(테스트 통과 수, 연결 확인 등). 확인하지 못한 것은 못 했다고 적는다
   - **환경 메모**: 설치·권한 문제와 해결법 중 팀원도 겪을 만한 것은 README의 "문제 해결"에도 옮긴다
   - **남은 일·TODO**
   
   문서 맨 위의 "열린 항목"(팀 확인 대기, 미정 사항)은 마일스톤과 상관없이 항상 최신으로 유지한다. 해결된 항목은 지우지 말고 해결 내용과 함께 해결됨으로 옮긴다.
9. **브랜치 규칙.**
   - `main`: 배포·발표용. 직접 커밋하지 않고 `dev` → `main` PR로만 반영한다.
     - **`main`에 병합되면 CD(`.github/workflows/deploy.yml`)가 곧바로 EC2에 배포한다.** 배포할 준비가 된 것만 `main`에 올린다.
     - `dev` → `main` PR은 **"Create a merge commit"**으로 병합한다. squash·rebase로 합치면 `main`과 `dev`의 이력이 갈라져, 다음 `dev` → `main` PR에서 이미 들어간 변경이 다시 차이로 보이고 충돌하기 쉽다.
   - `dev`: 개발 통합 브랜치 (GitHub default 브랜치).
   - `feat/dashboard-M<n>`: 마일스톤 작업 브랜치. 항상 최신 `dev`에서 만들고, 끝나면 `dev`로 PR을 연다. 마일스톤이 아닌 작은 수정은 `fix/<내용>`, `docs/<내용>`.
   - push, PR 생성·병합은 사용자 확인을 받고 한다.
10. **역할을 나눠 일한다 — Researcher → Planner → 구현 → Reviewer.** 역할 정의는 `.claude/agents/`, 사람용 설명은 `docs/agent-workflow.md`.

    | 단계 | 누가 | 하는 일 | 다음으로 넘기는 것 |
    |---|---|---|---|
    | 1 조사 | `researcher` 서브에이전트 | 관련 코드·스키마·참고 문서·결정 이력·이전 작업 기록을 읽고 근거 달린 사실만 보고 | 조사 보고 |
    | 2 계획 | `planner` 서브에이전트 | 바꿀 파일·단계·테스트, 번호 붙은 **완료 조건**, 사용자 확인이 필요한 결정 | 계획 → **사용자 승인** |
    | 3 구현 | 메인 에이전트 | 계획대로 고치고 테스트, README·progress 갱신 | 변경(diff) |
    | 4 검증 | `reviewer` 서브에이전트 | 완료 조건과 diff만으로 독립 검증, 테스트 직접 실행 | 판정: 통과 / 수정 필요 |

    - Reviewer에게는 **요구 원문, 계획의 완료 조건, 비교 기준(브랜치·커밋)만** 넘긴다. 구현하며 한 판단·설명·자기 평가("테스트 다 통과함")는 넘기지 않는다(구현자 시각에 끌려가지 않게).
    - "수정 필요"면 고친 뒤 **새 Reviewer**로 다시 검증한다. 지난 판정의 문제 목록(파일:줄, 실패 시나리오)만 더 넘긴다. 같은 문제로 두 번 넘게 막히면 멈추고 사용자에게 묻는다.
    - **검증은 최대 3차까지 한다**(사용자 결정 2026-11-18). 3차에서도 "수정 필요"면 4차를 돌리지 말고 멈춘 뒤, 남은 문제를 사용자에게 보고하고 어떻게 할지 묻는다. 마지막 검증 뒤에 고친 것은 "Reviewer 검증을 받지 않음"이라고 보고와 `docs/progress.md`에 적는다.
    - 사용자 보고와 `docs/progress.md` 확인 결과에 Reviewer 판정(몇 번째에 통과했나, 찾은 문제와 고친 것)을 적는다.
    - 줄여도 되는 것: 오타·문서 몇 줄 같은 작은 수정은 1·2단계를 생략한다. **코드·설정·대시보드 생성기·테스트를 바꾸면 4단계는 생략하지 않는다.**
    - 세 역할은 읽기 전용이다. Edit·Write 도구가 없고, Bash로 파일·git 상태를 바꾸는 명령은 `.claude/hooks/readonly_guard.py`가 막는다.
    - Reviewer가 통과시켜도 커밋·push·PR은 지금처럼 사용자 확인을 받는다(9항).
11. **작업 기록(hook).** `.claude/settings.json`의 hook이 프롬프트·도구 호출(입력·결과·소요 시간)·실패·서브에이전트 시작과 끝·응답 끝을 `logs/agent/<세션 ID>.jsonl`에 남긴다(비밀 값은 가림, git 제외).
    - 원인을 모르는 오류는 추측하기 전에 기록부터 본다: `python3 .claude/hooks/agent_log.py errors [세션]`(실패한 호출과 그 프롬프트·입력·오류), `show [세션]`(타임라인), `list`(세션 목록). 세션은 ID 앞 몇 글자, 생략하면 마지막 세션.
    - hook과 가드를 끄거나 고치지 않는다. 바꿔야 하면 먼저 묻는다.

## 13. 마일스톤

| # | 내용 | 완료 조건 |
|---|---|---|
| M1 | 저장소 뼈대, docker-compose(InfluxDB + Grafana), `.env.example`, 스키마 파일 2종 | `docker compose up`으로 InfluxDB·Grafana 접속 가능, datasource 자동 연결, 스키마 예시 메시지 검증 테스트 통과 |
| M2 | mock 생성기 + `scenarios.yaml` (M10에서 삭제) | 파일 출력으로 10분치 생성, 전 메시지 스키마 통과, seed 재현성 테스트 통과 |
| M3 | collector | mock → UDP → collector → InfluxDB 저장 확인, raw 녹화·거부 로그 동작 |
| M4 | 실시간 관제 대시보드 | mock 데이터로 9.1의 모든 패널 표시, annotation 동작 |
| M5 | evaluator + 성능 검증 대시보드 (M10에서 삭제) | 경계 사례 테스트 통과, `eval_result` 저장, 9.2 패널 표시 |
| M6 | replay | 녹화 파일 재생 시 실시간 대시보드에 표시 |
| M7 | AWS 배포 · CI/CD. AWS에는 대시보드 스택(InfluxDB + Grafana + collector)만 올리고, 테스트베드 실시간 경로(eBPF → 탐지 엔진)는 로컬에 둔다 | CI: PR마다 Python 3.10·3.14로 서비스 테스트까지 전체 통과. AWS: EC2에서 대시보드 접속, mock·replay 데이터 표시. CD: `main` 병합 시 자동 배포 후 헬스 체크 통과 |
| M8 | 탐지 엔진 연동 1 — 스키마 v0.3(27_ 레코드 6종), collector `POST /ingest`·`X-Env`·중복 제거·InfluxDB 저장 | 탐지 쪽 샘플 32개 전 줄 스키마 통과, `/ingest`로 넣어 InfluxDB 저장(타입 충돌·덮어쓰기 없음), 재전송 중복 제거·503 재시도 테스트 통과 |
| M9 | 탐지 엔진 연동 2 — AWS 앞단 TLS(자체 서명 인증서, IP SAN), 443·보안 그룹, 탐지 쪽 전송기와 연동 시험 | 탐지 쪽 전송기가 EC2 `https://<IP>/ingest`로 보낸 레코드가 InfluxDB에 저장됨 |
| M10 | 대시보드 재구성 — 관제(상시 KPM2·경보 목록·경보 상세: 근거 KPM2 그래프·KPM1 타임라인)·성능 대시보드를 탐지 엔진 레코드로. replay를 새 형식으로 바꾸고 mock·evaluator·처음 메시지(`metric`·`detection`·`attack_run`)·옛 대시보드를 지운다. 평가는 27_ §9에 따라 탐지 쪽과 정한 뒤 | 27_ §7 '화면과 레코드'의 화면이 샘플·replay 데이터로 표시됨 |
| M11 | 수집 오버헤드 — 탐지 쪽 `overhead` 형식(11/13)으로 스키마 v0.5, collector 저장(`overhead`·`overhead_link`), replay, 성능 대시보드 CU 자원 줄 | 새 형식이 스키마·`/ingest`·InfluxDB(실제 InfluxDB 통합 테스트)를 통과하고, CU 자원 줄이 실제 Grafana에서 표시됨 |
| M12 | Slack 알림 — AWS(p4) 공격 경보 발생·끝, 수집 멈춤을 Grafana Alerting으로(provisioning `grafana/provisioning/alerting/portran.json`, `grafana/build.py`가 만든다) | 알림 규칙이 실제 Grafana에서 돌고, 시험용 수신기로 발생·해제·강제 종료·수집 멈춤 메시지가 옴 |
