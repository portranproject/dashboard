# PortRAN Observability — 수집기 · 대시보드 · 검증 파이프라인

이 문서는 Claude Code가 이 저장소에서 작업할 때 따르는 기준이다. 작업 전에 끝까지 읽는다.

## 1. 프로젝트 배경

- 팀 프로젝트: **O-RAN 기반 5G 기지국 위협 탐지 솔루션** (5인, 최종 발표 2026-12-04)
- 전체 파이프라인: eBPF로 기지국 SW(OCUDU CU/DU) 무수정 텔레메트리 수집 → 보안 지표 eKPM으로 가공 → 룰 기반 탐지 엔진(C++) → 대시보드
- 테스트베드: OAI nrUE ↔ USRP B210 ↔ OCUDU(CU/DU 분리) ↔ Open5GS, FlexRIC(E2SM-KPM)
- 프로젝트 핵심 주장: **표준 KPM만으로는 못 잡는 위협을 eKPM + 룰로 탐지한다.** 대시보드와 검증은 이 주장을 숫자와 화면으로 보여주는 역할이다.

## 2. 이 저장소의 범위 (내 담당)

다른 팀원 담당(공격 도구, eBPF 에이전트, 탐지 엔진)은 아직 완성되지 않았다. 그래서 **mock 생성기로 먼저 개발하고, 나중에 실제 파트로 교체**한다.

```
[지금]  mock 생성기 ──────────────────────┐
                                          ├─ UDP/파일(JSON Lines) ─> collector ─> InfluxDB ─> Grafana
[나중]  eBPF 에이전트 / 탐지 엔진 / 공격 도구 ┘                         │
                                                                     └─> raw 녹화(.jsonl) ─> replay
                                                  evaluator ─> eval_result (InfluxDB) + 리포트
```

포함하는 것:
1. 메시지 스키마 정의 (팀 공용 기준 문서)
2. mock 생성기
3. collector (수신 → 검증 → InfluxDB 저장 → raw 녹화)
4. Grafana 대시보드 2개 (실시간 관제, 성능 검증)
5. evaluator (탐지율·오탐·지연 계산)
6. replay (녹화 데이터 재생, 발표 시연 백업용)

포함하지 않는 것: 탐지 로직, eBPF 코드, 공격 코드, 기지국 제어(대응)

## 3. 기술 스택

| 구분 | 선택 |
|---|---|
| 언어 | Python 3.10+ |
| 의존성 | `influxdb-client`(InfluxDB 2.x용), `pyyaml`, `jsonschema`, `pytest` |
| DB | InfluxDB 2.7 (Docker), 타임스탬프 precision = ns |
| 시각화 | Grafana OSS (Docker), datasource와 대시보드는 **provisioning 파일로 코드화** |
| 실행 | `docker compose` (InfluxDB + Grafana), Python 프로그램은 호스트에서 실행 |

- Docker 이미지는 `latest` 대신 고정 버전 태그를 쓴다.
- 접속 정보(토큰, org, bucket, 포트)는 `.env`로 관리하고 `.env.example`만 커밋한다.

## 4. 디렉터리 구조

```
.
├── CLAUDE.md
├── README.md                     # 실행 방법 (처음 보는 팀원 기준)
├── docs/
│   └── progress.md               # 마일스톤별 진행 기록 (12절 8항)
├── docker-compose.yml
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
```

## 5. 메시지 스키마

공통 규칙:
- 전송 단위: **JSON 한 줄 = 메시지 하나** (JSON Lines, UTF-8)
- 전송 방식: UDP(기본 `127.0.0.1:9999`) 또는 파일. collector는 둘 다 지원한다.
- 모든 시각은 **Unix epoch 나노초 정수**
- `type` 필드로 메시지 종류를 구분한다: `metric` | `detection` | `attack_run` | `overhead`
- 스키마의 단일 기준은 `schema/messages.schema.json`이다. mock, collector, 테스트 모두 이 파일로 검증한다.

### 5.1 metric (eKPM / 표준 KPM)
```json
{"type":"metric","ts":1763280000123456789,"src":"ebpf","node":"cu",
 "kind":"ekpm","name":"rrc_setup_req_rate","value":120.0,"unit":"req/s",
 "labels":{"cell":"1","ue":"0x4601"}}
```
- `src`: `ebpf` | `kpm` / `node`: `cu` | `du` | `core` / `kind`: `ekpm` | `kpm`
- `labels`는 선택. 지표 이름은 아직 **가안**이며 eBPF 팀과 확정 예정이다(7절).

### 5.2 detection (탐지 이벤트)
```json
{"type":"detection",
 "event_id":"det-000123",
 "ts_detected":1763280000523456789,
 "ts_first_evidence":1763280000123456789,
 "attack_type":"RRC_SIGNALING_STORM",
 "severity":"high",
 "ruleset":"full",
 "rule_id":"R-RRC-001","rule_version":"1.0",
 "target":{"node":"cu","cell":"1","ue":["0x4601","0x4602"]},
 "evidence":[
   {"source":"ebpf","metric":"rrc_setup_req_rate","op":">","value":120,"threshold":50,"window_ms":1000},
   {"source":"kpm","metric":"RRU.PrbUsedDl","op":">","value":85,"threshold":80,"window_ms":1000}
 ]}
```
- `severity`: `low` | `medium` | `high` | `critical`
- `ruleset`: `full`(eKPM + KPM 룰) | `kpm_only`(표준 KPM 룰만). 같은 공격을 두 룰셋으로 돌려 비교하기 위한 필드다.
- 탐지 지연 = `ts_detected - ts_first_evidence`

### 5.3 attack_run (정답 기록, 공격 도구가 출력)
```json
{"type":"attack_run","run_id":"run-007","scenario":"RRC_SIGNALING_STORM",
 "ts_start":1763280000000000000,"ts_end":1763280060000000000,
 "params":{"rate":200,"fake_ue_count":50}}
```
- `scenario` 값은 detection의 `attack_type`과 같은 이름 체계를 쓴다.

### 5.4 overhead (수집 오버헤드)
```json
{"type":"overhead","ts":1763280000000000000,"node":"cu","ebpf_on":true,"cpu_pct":23.4,"mem_mb":512}
```

### 5.5 공격 유형 (가안)
| attack_type | 설명 |
|---|---|
| `RRC_SIGNALING_STORM` | 대량 RRC 연결 요청으로 CU 시그널링 자원 고갈 |
| `ABNORMAL_UE_ATTACH` | 비정상 패턴의 단말 접속 시도 반복 |
| `F1AP_MSG_TAMPER` | CU-DU 간 F1AP 메시지 위·변조 |

## 6. InfluxDB 매핑

| measurement | time | tags | fields |
|---|---|---|---|
| `metric` | `ts` | src, node, kind, name, cell, ue | value(float), unit |
| `detection` | `ts_detected` | attack_type, severity, ruleset, rule_id, node | event_id, rule_version, ts_first_evidence, latency_ms, cell, ue_list(JSON 문자열), evidence_json(JSON 문자열) |
| `attack_run` | `ts_start` | scenario | run_id, ts_end, params_json |
| `overhead` | `ts` | node, ebpf_on | cpu_pct, mem_mb |
| `eval_result` | 평가 실행 시각 | scenario, ruleset | detection_rate, precision, fp_count, fp_per_hour, latency_p50_ms, latency_p95_ms, runs |

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
   - `RRC_SIGNALING_STORM`: KPM(연결 시도·실패)도 크게 오르지만, 어떤 UE가 가짜인지는 eKPM(C-RNTI별 상태)만 안다.
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

지표 (TeleRAN 논문 기준, `scenarios.yaml`에 정의, 이름·코드는 가안이라 eBPF 팀과 확정 예정):
- eKPM = 논문 Table I (UE별 보안 텔레메트리, `labels.ue`별, 값은 숫자 코드 또는 식별자): `ue_c_rnti`, `ue_s_tmsi`, `ue_cipher_alg`, `ue_integrity_alg`, `ue_rrc_state`, `ue_nas_state`, `ue_rrc_sec_state`, `ue_nas_sec_state`, `rrc_msg_id`, `nas_msg_id`
- 표준 KPM = 논문 Table II (3GPP TS 28.552, 셀 단위): `RRC.ConnEstabAtt`, `RRC.ConnEstabSucc`, `RRC.ConnEstabFailCause`, `RRC.RelWithoutSuspendConfig`, `UECNTX.ConnEstabAtt`, `UECNTX.ConnEstabSucc`, `RRC.ReEstabAtt`, `RRC.ReEstabSuccWithUeContext`, `RRC.ResumeAtt`, `RRC.ResumeSucc`, `RRC.ConnMean`, `RRC.ConnMax`, `RRC.InactiveConnMean`, `RRC.InactiveConnMax`
- 상태·알고리즘·메시지 ID의 숫자 코드표는 `scenarios.yaml`의 `codes`와 `schema/SCHEMA.md` 6절에 있다.

## 8. collector 요구사항

- UDP와 파일(tail -f 방식) 입력을 둘 다 지원한다.
- 메시지마다 JSON Schema로 검증하고, 실패한 메시지는 버리지 말고 `recordings/rejected.jsonl`에 사유와 함께 남긴다.
- 정상 메시지는 원본 그대로 `recordings/raw-<날짜시각>.jsonl`에 녹화한다(replay용).
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
6. 모르는 것(예: 실제 지표 이름, UE ID 형식)은 추측해서 확정하지 말고 TODO로 표시한다.
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
