# PortRAN Observability — 수집기 · 대시보드 · 검증 파이프라인

이 문서는 Claude Code가 이 저장소에서 작업할 때 따르는 기준이다. 작업 전에 끝까지 읽는다.

**답변은 항상 한국어로 한다.** 대화 답변, 질문 창(질문·선택지·설명 모두), 진행 보고, 문서가 모두 해당한다. 코드 식별자·명령·파일 경로·필드 이름은 원문 그대로 쓴다.

## 0. 작업 시작 전 필수: 참고 논문 읽기

**세션을 시작하면(첫 컨텍스트에서) 코드를 보거나 고치기 전에 `reference/`의 두 논문을 먼저 끝까지 읽는다.** 이 저장소의 지표 정의, 공격 유형, 탐지 규칙, 평가 방식의 근거가 이 논문들이다.

| 파일 | 논문 | 이 저장소에서 쓰는 곳 |
|---|---|---|
| `reference/TeleRAN.pdf` | TeleRAN: eBPF 기반 OpenRAN 텔레메트리 (FutureG 2026) | Table I → KPM1(eKPM), Table II → KPM2(표준 KPM). `schema/SCHEMA.md` 4절(탐지 엔진 레코드와의 대응)·6.5절(mock 지표), 대시보드 |
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

## 2. 이 저장소의 범위 (내 담당)

처음에는 다른 팀원 담당(공격 도구, eBPF 에이전트, 탐지 엔진)이 없어서 **mock 생성기로 먼저 개발했다.** 탐지 엔진 출력 형식이 확정됐으므로(2026-11-05, 5절) 실제 경로로 바꾸는 중이다(M8~M10).

```
[실제]  분석 엔진(eBPF) ─> 탐지 엔진 ─> 전송기 ─HTTPS POST /ingest─┐
                                                                   ├─> collector ─> InfluxDB ─> Grafana
[mock]  mock 생성기 ─────────── UDP/파일(JSON Lines) ──────────────┘      │
                                                                         └─> raw 녹화(.jsonl) ─> replay
                                                  evaluator ─> eval_result (InfluxDB) + 리포트  (mock 전용, M10에서 재검토)
```

eBPF 에이전트(분석 엔진)는 대시보드로 직접 보내지 않는다. 탐지 엔진이 받은 줄 가운데 상시 KPM2(`kpm2` 3초 묶음)·`hello`·`f1_evt`를 경보(`alert`·`evidence`·`gap`)와 같은 전송기로 보낸다. 공격 정답 기록은 받지 않는다(5.1절).

포함하는 것:
1. 메시지 스키마 정의 (팀 공용 기준 문서)
2. mock 생성기
3. collector (수신 → 검증 → InfluxDB 저장 → raw 녹화)
4. Grafana 대시보드 2개 (실시간 관제, 성능 검증)
5. evaluator (탐지율·오탐·지연 계산)
6. replay (녹화 데이터 재생, 발표 시연 백업용)
7. AWS 배포 · CI/CD (M7). AWS에는 대시보드 스택만 올린다. 절차는 `docs/deploy.md`

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
- 접속 정보(토큰, org, bucket, 포트)는 `.env`로 관리하고 `.env.example`만 커밋한다.

## 4. 디렉터리 구조

```
.
├── CLAUDE.md
├── README.md                     # 실행 방법 (처음 보는 팀원 기준)
├── reference/                    # 참고 논문 (0절). 작업 전에 읽는다
│   ├── README.md                 # 논문 요약, 이 저장소와의 대응 관계
│   ├── TeleRAN.pdf
│   ├── 5GSpector.pdf
│   └── detection/                # 탐지 엔진 담당 명세 27_(레코드 형식 기준, 5절)와 샘플 분석표
├── docs/
│   ├── progress.md               # 마일스톤별 진행 기록 (12절 8항)
│   └── deploy.md                 # AWS(EC2) 배포 절차 (M7)
├── .github/
│   └── workflows/
│       ├── ci.yml                # CI: PR마다 전체 테스트 (M7)
│       └── deploy.yml            # CD: main push 시 EC2 배포 (M7)
├── deploy/                       # CD용 서버 스크립트(server-deploy.sh)와 AWS 설정 JSON(aws/) (M7)
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
│   ├── schema.py                 # 스키마 검증 (mock·collector·테스트 공용)
│   └── transport.py              # UDP / 파일 송수신 공통 코드
├── mock/
│   ├── generator.py
│   └── scenarios.yaml            # 시나리오·지표 범위 설정
├── collector/
│   ├── collector.py
│   ├── ingest.py                 # POST /ingest HTTP 수신, 중복 키 (M8)
│   └── influx_writer.py
├── evaluator/
│   └── evaluate.py
├── replay/
│   └── replay.py
├── grafana/
│   ├── provisioning/datasources/influxdb.yml
│   ├── provisioning/dashboards/dashboards.yml
│   └── dashboards/{realtime.json, evaluation.json}
├── recordings/                   # raw 녹화 (.gitignore)
└── tests/
    └── data/detection/           # 탐지 쪽 경보 경로 샘플 32개 (11/05, 지금 탐지 엔진 코드 출력)
```

## 5. 메시지 스키마

스키마의 단일 기준은 `schema/messages.schema.json`이다. mock, collector, 테스트 모두 이 파일로 검증한다. 사람이 읽는 설명은 `schema/SCHEMA.md`(v0.3).

메시지는 두 갈래다.

| 갈래 | `type` | 보내는 곳 | 기준 |
|---|---|---|---|
| **탐지 엔진 레코드** | `alert` · `evidence` · `gap` · `kpm2` · `hello` · `f1_evt` | 탐지 엔진 전송기 → HTTPS `POST /ingest` | 탐지 엔진 담당 명세 `reference/detection/27_탐지엔진_1-4단계-대시보드-지표_명세서.md`(2026-11-05 확정, 이하 27_). **형식은 27_ 그대로 받는다** |
| **옛 메시지** | `metric` · `detection` · `attack_run` | mock 생성기만 | **교체 예정** — 대시보드 재구성(M10) 때 지운다 |
| | `overhead` | 미정 | 측정 주체·형식을 탐지 쪽과 협의 중(R5). 그때까지 옛 형식 |

공통 규칙:
- 전송 단위: **JSON 한 줄 = 메시지 하나** (JSON Lines, UTF-8)
- 탐지 엔진 레코드: 시각은 **Unix epoch 밀리초 정수**(분석 엔진이 붙인 데이터 시각). 모르는 필드는 받고(녹화에 남기고 화면에서 무시), `alert.fmt`·`kpm2`·`hello`·`f1_evt`의 `ver`가 1이 아니면 거부한다. `null`은 "모름"이다.
- 옛 메시지: 시각은 **Unix epoch 나노초 정수**, 모르는 필드는 거부. UDP(기본 `127.0.0.1:9999`) 또는 파일로 받는다.

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
{"type":"alert","fmt":1,"alert_id":"S1-L3-01-V-1-65","event":"raise","rule":"L3-01-V","stage":1,"unit":"cell","kind":"attack","cell":1,"t":1792209006400,"severity":"medium","mode":"normal","cond":["C1","C2","C2a"],"candidates":["L3-11"],"values":{"a_w":13,"f_w":12,"ratio":0.9230769230769231,"base":1.0},"params":{"k":3.0,"theta":0.5,"f_abs":10},"refs":{"a":[46,55],"f":[56,65]}}
```

- **KPM2 = TeleRAN Table II**(셀 카운터): `kpm2`의 `cc`·`si` 키가 Table II 14개 이름 그대로다(+ 탐지 쪽 확장 `ext` 3개). **KPM1 = Table I**(UE별, 팀 용어 eKPM): `ue_evt` 한 줄 = UE 메시지 하나. **상시로는 오지 않고** 경보 근거(`evidence.raw`)로만 온다. 탐지 엔진이 이것으로 2~4단계를 판정하고, 대시보드는 판정 결과(`alert`)와 근거(`evidence`)를 보여 준다. `ue_evt` 형식은 `schema/SCHEMA.md` 3.7절(타임라인 필드 7개만 검사), Table I·II 대응표는 4절.
- 받는 방법(`/ingest`·`X-Env`·응답 코드·중복 키)은 8절과 `schema/SCHEMA.md` 2절.
- `alert`에는 `session`이 없다. 같은 `alert_id`의 첫 `evidence`의 `raw.session`이 그 경보의 세션이다(27_ §7).
- 평가 결과(R1 `eval`·R2 `eval_run`)·경보별 지연(R3)·오버헤드(R5)는 전체 파이프라인(분석 엔진 → 탐지 엔진 → 대시보드, 실제 공격)이 완성된 뒤 탐지 쪽과 함께 정한다(27_ §9).

### 5.2 옛 메시지 (mock 전용, 교체 예정)

`metric`(eKPM·표준 KPM 지표 한 개), `detection`(탐지 이벤트, 룰셋 `full`·`kpm_only`), `attack_run`(정답 기록), `overhead`(수집 오버헤드). 필드·예시는 `schema/SCHEMA.md` 6절. 지금 mock·대시보드·evaluator·replay가 이 형식을 쓴다.

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

- `env` = `X-Env`(UDP·파일 입력은 collector `--env`). 환경마다 데이터가 갈린다(단계 비교는 `p4`·`lab` vs `replay-kpm-only`, 27_ §7).
- **같은 series·같은 시각이면 InfluxDB가 덮어쓴다.** 그래서 다른 레코드끼리 겹치지 않게 정했다: 같은 ms의 여러 줄은 ns 자리의 `seq`로, 두 경보에 함께 실린 같은 원본 줄은 `alert_id` tag로 가른다. 같은 줄을 다시 쓰면 같은 점에 덮어써져 결과가 그대로다.
- `alert_id`는 값마다 고유하지만 tag로 둔다(아래 원칙의 예외). 경보는 공격마다 하나라 series 수가 경보 수에 비례하는 정도이고, 위의 덮어쓰기를 막는 데 필요하다.
- `kpm2` 지표는 모두 실수로 쓰고 `null`은 뺀다(그래프에서 '데이터 없음'). 룰마다 다른 묶음(`values`·`params`·`ues`)은 JSON 문자열로 통째 저장한다(27_ §7.1).
- 대표 값 `rep_value`는 27_ §5.3의 룰별 '대표 값', 판정 보류 경보는 `held_w`.

옛 메시지:

| measurement | time | tags | fields |
|---|---|---|---|
| `metric` | `ts` | src, node, kind, name, cell, ue | value(float), unit |
| `detection` | `ts_detected` | attack_type, severity, ruleset, rule_id, node | event_id, rule_version, ts_first_evidence, latency_ms, cell, ue_list(JSON 문자열), evidence_json(JSON 문자열) |
| `attack_run` | `ts_start` | scenario | run_id, ts_end, params_json |
| `overhead` | `ts` | node, ebpf_on | cpu_pct, mem_mb |
| `eval_result` | 평가 실행 시각 | scenario, ruleset, data_source | detection_rate, precision, fp_count, fp_per_hour, latency_p50_ms, latency_p95_ms, runs, (M5에서 추가) tp, fn, detections, onset_p50_ms, onset_p95_ms, eval_id, window_from, window_to, grace_sec |

- `event_id`, `run_id`처럼 값마다 고유한 것은 tag로 두지 않는다(cardinality 폭증 방지).
- 테스트베드는 UE 수가 적으므로 `ue`는 metric에서 tag로 둔다.

## 7. mock 생성기 요구사항

CLI 예시:
```bash
python -m mock.generator --scenario mixed --duration 600 --seed 42 --out udp://127.0.0.1:9999
python -m mock.generator --scenario RRC_SIGNALING_STORM --duration 120 --out file://recordings/mock.jsonl
python -m mock.generator --speed 10   # 10배속 (빠른 데이터 축적용)
```

동작:
1. **평상시**: 정상 UE들이 등록·연결·해제·일시 중지·재개·재수립 같은 RRC/NAS 절차를 무작위 간격으로 반복한다. 같은 절차에서 eKPM(메시지 처리마다, UE별)과 표준 KPM(1초 주기, 셀 단위 집계)을 함께 뽑아 두 지표가 서로 맞도록 한다.
2. **공격 구간**: `attack_run`을 내보내고, 공격 절차(가짜 UE, 공격자 UE, 메시지 변조)를 일으킨다. 표준 KPM은 **공격별로 현실대로** 변한다. 프로젝트 핵심 주장을 화면으로 보여주는 데이터다.
   - `RRC_SIGNALING_STORM` (= 5G-Spector의 BTS Resource Depletion): 위조 연결이 인증 요청까지 진행한 뒤 응답 없이 몇 초 머물다 해제된다. KPM(연결 시도·성공, 연결 UE 수)도 크게 오르지만, 어떤 UE가 가짜인지(transient UE)는 eKPM만 안다.
   - `ABNORMAL_UE_ATTACH`: KPM은 연결 시도가 조금 늘 뿐이고, eKPM에 반복되는 인증 실패·등록 거절과 바뀌는 S-TMSI가 보인다.
   - `F1AP_MSG_TAMPER`: KPM은 거의 그대로이고, eKPM에서 보안 알고리즘이 NEA0/NIA0으로 떨어지고 C-RNTI가 어긋난다.
3. **탐지 이벤트**:
   - `ruleset=full`: 공격 시작 후 200~800ms 지연, 높은 탐지율(예: 95%)
   - `ruleset=kpm_only`: 더 긴 지연, 낮은 탐지율(예: 30~50%)
   - 두 룰셋 모두 공격이 없는 구간에서도 낮은 확률로 오탐을 낸다.
4. **overhead**: `ebpf_on=true/false` 두 경우를 섞어서 내보낸다(on일 때 CPU가 약간 높게).
5. `--seed`가 같으면 결과가 같아야 한다(재현 가능).
6. 지표 이름·기본값·공격 시 변화량·탐지율 같은 숫자는 전부 `scenarios.yaml`에 두고 코드에 하드코딩하지 않는다.
7. 내보내는 모든 메시지는 JSON Schema 검증을 통과해야 한다.

지표:
- mock은 옛 메시지(5.2절)를 낸다. 지표는 TeleRAN Table I → eKPM 10개, Table II → 표준 KPM 14개(`schema/SCHEMA.md` 6.5절, `scenarios.yaml`의 `ekpm`·`kpm`)만 쓴다.
- 상태·알고리즘·메시지 ID의 숫자 코드표(mock 전용 가안)는 `scenarios.yaml`의 `codes`에 있다.
- 탐지 엔진 레코드로 바꾸는 것은 M10(대시보드 재구성) 때 한다. 그 전까지 탐지 엔진 레코드로 화면을 볼 때는 탐지 쪽 샘플(`tests/data/detection/`)을 쓴다.

## 8. collector 요구사항

- UDP, 파일(tail -f 방식), HTTP `POST /ingest` 입력을 지원한다. HTTP는 탐지 엔진 전송기용이고 TLS는 앞단이 맡는다(collector는 서버 안에서 평문으로 받음).
- 메시지마다 JSON Schema로 검증하고, 실패한 메시지는 버리지 말고 `recordings/rejected.jsonl`에 사유와 함께 남긴다.
- 정상 메시지는 원본 그대로 녹화한다(replay용). 옛 메시지는 `recordings/raw-<날짜시각>.jsonl`, 탐지 엔진 레코드는 환경별로 `recordings/raw-<날짜시각>-<환경>.jsonl`.
- `/ingest` 약속(27_ §3, 대시보드 2차 답변서 D1~D3, `schema/SCHEMA.md` 2절):
  - 헤더 `X-Env`를 환경으로 저장한다(없으면 `unknown`). 토큰은 쓰지 않는다(HTTPS + 보안 그룹 IP 제한).
  - **원본 녹화와 InfluxDB 저장이 끝난 뒤에** 답한다. `200 {"accepted","rejected","duplicates"}`(틀린 줄은 거부 로그로 보내고 나머지는 저장), 본문을 못 읽으면 `400`, 상한(1 MiB)을 넘으면 `413`, InfluxDB 일시 장애면 `503`(그 요청은 아무것도 반영하지 않음 — 전송기가 다시 보냄).
  - 다시 보낸 줄은 환경 + 레코드별 중복 키로 걸러 한 번만 저장한다.
- InfluxDB에는 배치로 쓴다(예: 500건 또는 1초마다).
- 종료(Ctrl+C) 시 남은 배치를 flush한다.
- 1초마다 수신·저장·거부 건수를 로그로 출력한다.

## 9. Grafana 대시보드

datasource와 대시보드 모두 provisioning으로 띄운다. `docker compose up` 한 번으로 대시보드까지 떠야 한다. 대시보드 JSON은 `grafana/dashboards/`에 커밋한다.

### 9.1 실시간 관제 (`realtime.json`), 새로고침 5초
| 행 | 패널 |
|---|---|
| 요약 | 최근 5분 탐지 건수, 최고 severity, 소스별 마지막 수신 시각(수집 상태), 접속 UE 수 |
| 핵심 비교 | 같은 시간축에 **표준 KPM 패널과 eKPM 패널을 위아래로** 배치. `detection`은 세로선 annotation, `attack_run`은 구간(region) annotation으로 표시 |
| 이벤트 | 탐지 이벤트 테이블(시각, attack_type, severity, 대상, rule_id, ruleset) + attack_type별 건수 |
| 근거 | 변수 `event_id`로 선택한 이벤트의 evidence를 표로(지표 / 값 / 연산자 / 임계값 / 윈도우). `evidence_json`은 Grafana의 Extract fields 변환으로 펼친다 |

변수: `ruleset`(기본 full), `node`, `attack_type`

### 9.2 성능 검증 (`evaluation.json`)
- 시나리오 × 룰셋별 탐지율, precision, 오탐 수 표 (`full` vs `kpm_only` 나란히)
- 탐지율 막대그래프 (full vs kpm_only)
- 탐지 지연 분포(히스토그램)와 p50/p95
- eBPF on/off별 CPU·메모리 비교

## 10. evaluator 요구사항

```bash
python -m evaluator.evaluate --from 2026-11-20T10:00:00 --to 2026-11-20T12:00:00 --grace-sec 5
```

매칭 규칙:
- detection이 어떤 attack_run과 **attack_type이 같고**, `ts_detected`가 `[ts_start, ts_end + grace]` 안에 있으면 그 run에 매칭된다.
- run에 매칭된 detection이 1개 이상이면 **TP**, 없으면 **FN**. (run 하나에 여러 detection이 나와도 TP 1건)
- 어떤 run에도 매칭되지 않은 detection은 **FP**.
- 시나리오 × 룰셋별로 계산한다:
  - 탐지율 = TP / (TP + FN)
  - precision = 매칭된 detection 수 / 전체 detection 수
  - fp_per_hour = FP 수 / 공격이 없던 시간(시간 단위)
  - 지연: run별 첫 매칭 detection의 `ts_detected - ts_first_evidence`, 그리고 `ts_detected - ts_start`의 p50/p95

출력:
- InfluxDB `eval_result` measurement에 저장
- `reports/eval-<날짜시각>.md`와 `.csv`로 저장

## 11. replay 요구사항

```bash
python -m replay.replay recordings/raw-xxxx.jsonl --speed 1 --out udp://127.0.0.1:9999 --retime now
```
- `--retime now`: 원본 시간 간격은 유지하고, 시각만 현재 기준으로 옮겨서 보낸다(실시간 대시보드에서 바로 보이도록).
- 발표 당일 테스트베드 시연이 실패할 경우의 백업용이다.

## 12. 작업 원칙

1. **마일스톤 단위로 진행한다.** 한 마일스톤이 끝나면 멈추고, `docs/progress.md`를 갱신하고, 한 일·실행 방법·확인 결과를 보고한 뒤 다음으로 넘어간다. 커밋은 사용자 확인을 받고 마일스톤 단위로 한다.
2. **스키마(5절)를 바꿔야 하면 먼저 묻는다.** 다른 팀원들과 합의된 기준이라 임의로 바꾸지 않는다.
3. 숫자(임계값, 확률, 범위, 포트)는 설정 파일이나 `.env`로 뺀다.
4. 핵심 로직(스키마 검증, InfluxDB 변환, evaluator 매칭·계산)은 pytest로 테스트한다. 특히 evaluator는 TP/FN/FP 경계 사례(grace 경계, 다른 attack_type, run 하나에 여러 detection)를 테스트로 고정한다.
5. 실행 방법이 바뀌면 README.md를 같이 고친다.
6. 모르는 것(예: UE ID 형식, 상태 코드표)은 추측해서 확정하지 말고 TODO로 표시한다.
7. **mock 데이터로 나온 숫자는 성능 결과가 아니다.** 리포트에 데이터 출처(mock / 실제 / replay)를 표시한다.
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

## 13. 마일스톤

| # | 내용 | 완료 조건 |
|---|---|---|
| M1 | 저장소 뼈대, docker-compose(InfluxDB + Grafana), `.env.example`, 스키마 파일 2종 | `docker compose up`으로 InfluxDB·Grafana 접속 가능, datasource 자동 연결, 스키마 예시 메시지 검증 테스트 통과 |
| M2 | mock 생성기 + `scenarios.yaml` | 파일 출력으로 10분치 생성, 전 메시지 스키마 통과, seed 재현성 테스트 통과 |
| M3 | collector | mock → UDP → collector → InfluxDB 저장 확인, raw 녹화·거부 로그 동작 |
| M4 | 실시간 관제 대시보드 | mock 데이터로 9.1의 모든 패널 표시, annotation 동작 |
| M5 | evaluator + 성능 검증 대시보드 | 경계 사례 테스트 통과, `eval_result` 저장, 9.2 패널 표시 |
| M6 | replay | 녹화 파일 재생 시 실시간 대시보드에 표시 |
| M7 | AWS 배포 · CI/CD. AWS에는 대시보드 스택(InfluxDB + Grafana + collector)만 올리고, 테스트베드 실시간 경로(eBPF → 탐지 엔진)는 로컬에 둔다 | CI: PR마다 Python 3.10·3.14로 서비스 테스트까지 전체 통과. AWS: EC2에서 대시보드 접속, mock·replay 데이터 표시. CD: `main` 병합 시 자동 배포 후 헬스 체크 통과 |
| M8 | 탐지 엔진 연동 1 — 스키마 v0.3(27_ 레코드 6종), collector `POST /ingest`·`X-Env`·중복 제거·InfluxDB 저장 | 탐지 쪽 샘플 32개 전 줄 스키마 통과, `/ingest`로 넣어 InfluxDB 저장(타입 충돌·덮어쓰기 없음), 재전송 중복 제거·503 재시도 테스트 통과 |
| M9 | 탐지 엔진 연동 2 — AWS 앞단 TLS(자체 서명 인증서, IP SAN), 443·보안 그룹, 탐지 쪽 전송기와 연동 시험 | 탐지 쪽 전송기가 EC2 `https://<IP>/ingest`로 보낸 레코드가 InfluxDB에 저장됨 |
| M10 | 대시보드 재구성 — 실시간 관제·경보 목록·경보 상세(근거 KPM2 그래프·KPM1 타임라인)를 탐지 엔진 레코드로. mock·replay를 새 형식으로 바꾸고 옛 메시지(`metric`·`detection`·`attack_run`)를 지운다. 평가는 27_ §9에 따라 탐지 쪽과 정한 뒤 | 27_ §7 '화면과 레코드'의 화면이 샘플·replay 데이터로 표시됨 |
