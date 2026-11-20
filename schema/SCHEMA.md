# PortRAN 메시지 스키마 (v0.5)

collector가 받는 메시지 형식이다. **기계 검증의 단일 기준은 [`messages.schema.json`](messages.schema.json)**이고, 이 문서는 그 내용을 사람이 읽기 쉽게 풀어 쓴 것이다. 둘이 다르면 JSON Schema가 맞다.

| 갈래 | `type` | 보내는 곳 | 기준 |
|---|---|---|---|
| **탐지 엔진 레코드** | `alert` · `evidence` · `gap` · `kpm2` · `hello` · `f1_evt` | 탐지 엔진 전송기 (`POST /ingest`) | 탐지 엔진 담당 명세 [`27_탐지엔진_1-4단계-대시보드-지표_명세서.md`](../reference/detection/27_탐지엔진_1-4단계-대시보드-지표_명세서.md) (2026-11-05 확정, 이하 **27_**). 뜻·룰별 값은 27_이 기준이고, 이 문서는 collector가 무엇을 검사하고 어떻게 저장하는지를 적는다 |
| **수집 오버헤드** | `overhead` | 분석 엔진(계측기)이 3초마다 — 전송기가 `kpm2`·`f1_evt`처럼 줄 그대로 `POST /ingest` | 탐지 쪽이 11/13에 보낸 형식(27_ 밖, R5). 6절 |

처음 스키마의 `metric`·`detection`·`attack_run`(mock 생성기 전용)은 M10에서 mock·evaluator와 함께 지웠다(v0.4).

> 스키마를 바꾸고 싶으면 먼저 팀에 공유하고 합의한 뒤 두 파일을 함께 고친다. 탐지 엔진 레코드는 27_이 바뀌면 따라 고친다.

## 1. 공통 규칙

모든 레코드(탐지 엔진 레코드 6종과 `overhead`)에 같은 규칙을 쓴다. v0.4까지 `overhead`만 따로 쓰던 규칙(ns 시각, 모르는 필드 거부, UDP)은 v0.5에서 없앴다.

| 항목 | 규칙 |
|---|---|
| 전송 단위 | JSON 한 줄 = 레코드 하나 (JSON Lines, UTF-8) |
| 전송 방식 | `POST /ingest` (2절). 시험용으로 UDP·파일도 받는다(이때 환경은 collector `--env`) |
| 시각 | **Unix epoch 밀리초 정수** — 분석 엔진이 붙인 데이터 시각(27_ §2.3). 2001-09-09 ~ 2286년 범위만 받는다(초·마이크로초·나노초로 잘못 보낸 값을 잡으려고) |
| 모르는 필드 | **받는다.** 녹화에는 그대로 남고 InfluxDB 저장과 화면에서는 무시한다. 탐지 쪽은 필드를 더할 때 형식 판을 올리지 않는다(27_ §2.4) |
| 형식 판 | `alert`의 `fmt`, `kpm2`·`hello`·`f1_evt`·`overhead`의 `ver`가 `1`이 아니면 거부(대시보드 2차 답변서 D8, 27_ §9) |
| `null` | "그 값을 셌어야 하는데 모름". 키가 없음 = 해당 없음. InfluxDB에는 그 필드를 빼고 쓴다(그래프에서 0이 아니라 '데이터 없음') |
| 다시 보낸 줄 | 환경 + 레코드별 키가 같으면 한 번만 저장(2.3) |

공통 검사:
- 정수 필드에 실수 표기(`1.0`)·문자열은 거부한다. JSON Schema 표준은 `1.0`을 정수로 보지만 우리 검증기 `common/schema.py`는 정밀도 손실을 막기 위해 실수 표기를 거부한다.
- 숫자 필드에 `NaN`, `Infinity`는 거부한다.
- 검증되지 않은 줄은 버리지 않고 `recordings/rejected.jsonl`에 사유와 함께 남긴다.

## 2. `/ingest`로 받기 — 탐지 엔진 전송기

27_ §3의 약속(11/02 합의, 대시보드 2차 답변서 D1~D3) 그대로다. TLS는 서버 앞단이 맡고, collector는 서버 안에서 평문 HTTP로 받는다(`--in http://127.0.0.1:8088`).

### 2.1 요청

| 항목 | 값 |
|---|---|
| 주소 | `POST /ingest` |
| 본문 | 파일의 줄을 바이트 그대로 `\n`으로 이은 것. 빈 줄은 건너뛴다 |
| 크기 | 요청 하나 최대 1 MiB(`COLLECTOR_HTTP_MAX_BYTES`). `Content-Length` 필수 |
| `X-Env` | 환경(`p4`·`lab`·`replay-kpm-only` 등). 없으면 `unknown`. 영숫자로 시작하고 영숫자·`.`·`_`·`-`만 쓴 64자 이하 |
| 인증 | 토큰 없음 — HTTPS + 보안 그룹 IP 제한(11/02 합의) |

### 2.2 응답 — 원본 녹화와 InfluxDB 저장이 끝난 뒤에 답한다

| 코드 | 언제 | 본문 | 전송기 |
|---|---|---|---|
| `200` | 줄마다 검증해 통과한 줄을 저장한 뒤. 틀린 줄이 있어도 나머지는 저장한다 | `{"accepted":n,"rejected":m,"duplicates":d}` | 다음 묶음 |
| `400` | 본문 전체를 읽을 수 없음(UTF-8 아님, `Content-Length`보다 짧음), `X-Env` 형식 오류 | `{"error":…}` | 다시 보내지 않음 |
| `411` | `Content-Length` 없음 | | 설정 문제로 보고 멈춤 |
| `413` | 요청이 상한을 넘음 | | 반으로 나눠 다시 |
| `503` | InfluxDB 일시 장애, 처리가 `COLLECTOR_HTTP_TIMEOUT_MS`를 넘음, collector 종료 중 | | 간격을 늘려 다시 |
| `404` | `/ingest`가 아닌 경로 | | 멈춤 |

- `503`이면 그 요청의 줄은 녹화·중복 키에 하나도 반영하지 않는다. 같은 묶음이 다시 와도 처음 온 것처럼 저장한다.
- `GET /healthz` → `200 {"status":"ok"}` (앞단·서버 상태 확인용).

### 2.3 다시 보낸 줄 거르기 (27_ §3 '중복 제거 키', 모든 키 앞에 `X-Env`)

| 레코드 | 키 |
|---|---|
| `alert` | (`alert_id`, `event`, `t`) |
| `evidence` | (`alert_id`, `phase`, `seq`, `ue`) — 1단계는 `ue` 없음 |
| `gap` | (`alert_id`, `t_from`) |
| `kpm2` | (`session`, `cell_id`, `agg_ms`, `t_start_ms`) |
| `hello` · `f1_evt` · `overhead` | (`session`, `seq`) — 세 종류가 같은 번호열을 쓴다 |

collector는 최근 키 `COLLECTOR_DEDUP_MAX_KEYS`개를 메모리에 기억한다. 재시작하면 비지만, 같은 줄은 InfluxDB에서 같은 series·같은 시각에 덮어써지므로(5절) 저장 결과는 같다. 녹화 파일에는 재시작 뒤 다시 온 줄이 한 번 더 남을 수 있다.

### 2.4 직접 보내 보기

```bash
python -m collector.collector --dry-run --in http://127.0.0.1:8088     # 터미널 1
curl -s -X POST http://127.0.0.1:8088/ingest -H 'Content-Type: application/x-ndjson' -H 'X-Env: lab' \
     --data-binary @tests/data/detection/T10_긴공격_evidence.jsonl          # 터미널 2
# → {"accepted": 667, "rejected": 0, "duplicates": 0}. 한 번 더 보내면 모두 duplicates
```

## 3. 탐지 엔진 레코드

필드의 뜻은 27_의 해당 절을 본다. 아래 "검사"는 collector가 거부하는 조건이다. 표에 없는 필드는 받는다.

### 3.1 `alert` — 경보 (27_ §5)

경보 하나 = (룰, 셀) 하나. 생애는 `raise` → (`update`) → `clear`/`end`. 1단계 `raise` 예:

```json
{"type":"alert","fmt":1,"alert_id":"S1-L3-01-V-1-65","event":"raise","rule":"L3-01-V","stage":1,"unit":"cell","kind":"attack","cell":1,"t":1792209006400,"severity":"medium","mode":"normal","cond":["C1","C2","C2a"],"candidates":["L3-11"],"values":{"a_w":13,"f_w":12,"ratio":0.9230769230769231,"base":1.0,"sigma":0.0},"params":{"z":3.0,"theta":0.5,"f_abs_frac":0.1,"f_abs":10},"refs":{"a":[46,55],"f":[56,65]}}
```

| 검사 | 내용 |
|---|---|
| 필수 | `type` · `fmt`(=1) · `alert_id` · `event` · `rule` · `stage` · `unit` · `kind` · `cell` · `t` · `severity` · `mode` |
| 열거 | `event` `raise`·`update`·`clear`·`end` · `unit` `cell`·`ue` · `kind` `attack`·`anomaly` · `stage` 1~4 |
| 그대로 받는 값 | `rule`·`severity`·`mode`는 비어 있지 않은 문자열이면 받는다(새 룰·심각도가 와도 저장하고 화면이 처리) |
| 선택 필드 타입 | `cond`·`candidates`·`conditions` 문자열 배열 · `values`·`params`·`refs` 객체(안은 검사 안 함) · `ues` 객체 배열 · `ues_total`·`duration_ms`·`evidence_sent`·`evidence_dropped` 0 이상 정수 · `branch`·`reason` 문자열 |
| `ues[]` 한 칸 | `cell`·`du_ue_id`·`uid` 정수 필수. `cu_ue_id`·`crnti` 정수 또는 `null`, `s_tmsi` 문자열 또는 `null`, `seq_range` 정수 2개 또는 `null`, `evidence` 불리언 |

- `alert`에는 `session`이 없다. collector가 같은 `alert_id`의 첫 `evidence`의 `raw.session`을 그 경보의 세션으로 저장한다(27_ §7, 5절).
- `update`의 `values`는 그 시점의 전체 값(덮어씀), `ues`는 새로 걸린 UE만(누적) — 화면에서 처리한다(27_ §7).

### 3.2 `evidence` — 경보 근거 (27_ §6)

2~4단계 근거(공격 증거 KPM1) 예 — `raw`는 분석 엔진의 원본 `ue_evt` 그대로:

```json
{"type":"evidence","alert_id":"S1-L3-24-1-21","phase":"pre","seq":12,"ue":[1,3,1],"raw":{"type":"ue_evt","t_ms":1792209001000,"cell_id":1,"du_ue_id":3,"cu_ue_id":3,"crnti":10003,"dir":"UL","proto":"RRC","msg":"RRCSetupRequest","f":{"est_cause":"mo-Signalling","ue_identity":{"type":"randomValue"}},"ver":1,"session":"S1","seq":12}}
```

| 검사 | 내용 |
|---|---|
| 필수 | `type` · `alert_id` · `phase`(`pre`·`active`·`post`) · `seq`(0 이상 정수) · `raw`(객체, `type` 문자열 필수) |
| 선택 | `ue` 정수 3개 `[cell, du_ue_id, uid]` — 2~4단계만 |
| `raw` | `type`(문자열)을 확인한다. **`ue_evt`(KPM1)면 타임라인에 쓰는 필드 7개를 검사**한다(3.7절). 100 ms `kpm2` 등 다른 원본은 해석하지 않고 그대로 저장한다(27_ §8) |

1단계 근거(공격 증거 KPM2)는 `raw`가 100 ms 원본 `kpm2`이고 `ue`가 없다.

### 3.3 `gap` — 경보 중 그 셀의 `kpm2`가 끊긴 구간 (27_ §6.4)

```json
{"type":"gap","alert_id":"S1-L3-01-V-1-65","cell":1,"t_from":1792209012000,"t_to":1792209012100,"seq_from":121,"seq_to":122}
```

필수: `type` · `alert_id` · `cell` · `t_from` · `t_to`. 선택: `seq_from`·`seq_to`(정수 또는 `null`). `t_from > t_to`면 경고 로그만 남기고 저장한다.

### 3.4 `kpm2` — 상시 KPM2, 셀마다 3초로 묶은 줄 (27_ §4.1)

```json
{"type":"kpm2","ver":1,"agg_ms":3000,"session":"20261105T010000Z","cell_id":1,"t_start_ms":1793840400000,"t_end_ms":1793840403000,"n":30,"seq_from":103,"seq_to":190,"cc":{"RRC.ConnEstabAtt":{"total":21,"mo-Signalling":21},"RRC.ConnEstabSucc":{"total":21,"mo-Signalling":21},"RRC.ConnEstabFailCause":{"NetworkReject":0,"NoReply":0,"Other":0},"RRC.RelWithoutSuspendConfig":0,"UECNTX.ConnEstabAtt":{"total":21,"mo-Signalling":21},"UECNTX.ConnEstabSucc":{"total":21,"mo-Signalling":21},"RRC.ReEstabAtt":null,"RRC.ReEstabSuccWithUeContext":null,"RRC.ResumeAtt":null,"RRC.ResumeSucc":null},"si":{"RRC.ConnMean":4.433,"RRC.ConnMax":6,"RRC.InactiveConnMean":null,"RRC.InactiveConnMax":null},"ext":{"UeCtxMax":7,"DuCannotServe":0,"CrntiAlloc":21},"partial":["cc.RRC.ConnEstabFailCause"]}
```

| 검사 | 내용 |
|---|---|
| 필수 | `type` · `ver`(=1) · `agg_ms`(1 이상 정수) · `session` · `cell_id` · `t_start_ms` · `t_end_ms` · `n` |
| `cc`·`si`·`ext` | 객체. 값은 숫자, `null`, 또는 하위 키(원인별 등)마다 숫자·`null`을 담은 객체 |
| 선택 | `seq_from`·`seq_to` 정수 또는 `null`, `partial` 문자열 배열 |

- `/ingest`로 오는 `kpm2`는 **모두 묶은 줄**이라 `agg_ms`가 없으면 거부한다. 100 ms 원본은 `evidence.raw` 안에만 온다.
- `agg_ms`는 운영 중 바뀔 수 있어(1,000의 배수) 줄마다 읽는다. `n`이 `agg_ms / hello.period_ms`보다 작으면 칸 일부가 빠진 것이다.

### 3.5 `hello` — 분석 엔진 접속 = 새 세션 시작 (27_ §4.3)

```json
{"type":"hello","ver":1,"session":"20261024T013000Z","seq":1,"producer":"ebpf-analyzer 0.1","node_id":"cu-p4","cells":[{"cell_id":1,"max_conn":null}],"period_ms":100,"noreply_timeout_ms":1000,"si_sample_ms":100,"clock":"realtime","ue_evt":true}
```

필수: `type` · `ver`(=1) · `session` · `seq`. **시각 필드가 없다** — collector가 받은 시각으로 저장한다.

### 3.6 `f1_evt` — DU·CU 재시작 (27_ §4.3)

```json
{"type":"f1_evt","ver":1,"session":"20261026T090000Z","seq":3001,"t_ms":1793005300000,"msg":"F1SetupRequest","cells":[1]}
```

필수: `type` · `ver`(=1) · `session` · `seq` · `t_ms` · `msg`. 선택: `cells`(정수 배열 또는 `null` = 모든 셀), `du_ue_ids`(정수 배열).

### 3.7 KPM1 `ue_evt` — `evidence.raw` 안 (27_ §4.2)

분석 엔진이 관측한 RRC·NAS·F1AP 메시지 **하나 = 한 줄**이다(집계 없음). 단독으로는 오지 않고 2~4단계 경보의 `evidence.raw`에 담겨 온다(상시로는 보내지 않음, 27_ §9 D4). 탐지 엔진이 이 줄들로 2~4단계 공격을 판정하고, 판정 결과는 `alert`, 근거는 걸린 UE의 이 줄들이다.

예 — 4단계 `AN-02`(식별 요청 증가) 경보에 걸린 UE `[1,3,3]`이 받은 식별 요청(샘플 `SAN02_AN-02_해제_CLEAR` 13번째 줄의 `raw`):

```text
{"type":"ue_evt","t_ms":1792209035095,"cell_id":1,"du_ue_id":3,"cu_ue_id":3,"crnti":10003,"dir":"DL","proto":"NAS","msg":"IdentityRequest","via":"F1","sht":0,"ver":1,"session":"20261105T102600Z","seq":378}
```

| 필드 | 타입 | 검사 | 뜻 |
|---|---|---|---|
| `type` | `"ue_evt"` | 필수 | |
| `t_ms` | 정수(ms) | **필수** | 메시지를 관측한 데이터 시각. 같은 ms 안의 순서는 `seq` 순 |
| `cell_id` | 0 이상 정수 | **필수** | 서빙 셀 — `kpm2`의 `cell_id`와 같은 번호 |
| `du_ue_id` | 정수 또는 `null` | **필수** | gNB-DU UE F1AP ID — 연결을 잇는 기본 키. `null`은 NGAP에서만 보고 잇지 못한 NAS 줄 |
| `dir` | `"UL"` · `"DL"` | **필수** | 단말 → 망 / 망 → 단말 |
| `proto` | `"RRC"` · `"NAS"` · `"F1AP"` | **필수** | |
| `msg` | 문자열 | **필수** | 메시지 이름(아래 표 철자). 목록 밖 이름도 받는다. 암호화돼 종류를 모르는 NAS는 `"ProtectedNAS"` |
| `cu_ue_id` · `crnti` | 정수 또는 `null` | 안 함 | gNB-CU UE F1AP ID(CU가 첫 DL을 보낸 뒤부터) · C-RNTI(10진) |
| `via` · `sht` | 문자열 · 정수 | 안 함 | NAS만 — 본 경로 `"F1"`(RRC 안)·`"NGAP"`, 보안 헤더 유형 0~4(0 = 평문) |
| `f` | 객체 | 안 함 | 메시지에서 꺼낸 값(아래 표). 꺼내지 못한 값은 키가 없거나 `null` |
| `ver` · `session` · `seq` | 정수 · 문자열 · 정수 | 안 함 | 형식 판 · 분석 엔진 세션 · 세션 안 일련번호(모든 종류의 줄이 한 번호열을 함께 씀) |

- **"필수" 7개만 검사한다.** 근거 타임라인에 쓰는 값이다. 나머지와 모르는 필드는 그대로 받는다 — `ue_evt` 형식이 아직 분석 엔진 팀 답을 기다리는 초안이라서다(27_ §8). 필수 값이 틀리면 그 근거 줄만 거부돼 `rejected.jsonl`에 남는다(경보 레코드는 그대로 저장).
- 화면(27_ §6.3): UE(`evidence.ue`)마다 한 줄 타임라인 — 가로축 `t_ms`, 이름 `msg`, 방향 `dir`(↑ UL / ↓ DL), 색 `proto`. `f` 등 나머지는 해석하지 않고 펼쳐 보인다.
- UE 묶기(27_ §4.2): 연결 하나 = (`session`, `cell_id`, `du_ue_id`)로 처음 본 줄부터 `UEContextReleaseComplete`까지. 같은 단말의 여러 연결은 S-TMSI로 묶는다.

**메시지와 `f`** (27_ §4.2 그대로. † = 탐지 쪽 샘플 32개에 아직 나오지 않은 메시지)

| `proto` | `dir` | `msg` | `f` |
|---|---|---|---|
| RRC | UL | `RRCSetupRequest` | `est_cause`(설정 원인), `ue_identity` `{"type":"ng-5G-S-TMSI-Part1"\|"randomValue","value":"0x…"}` |
| RRC | DL | `RRCSetup` | — |
| RRC | DL | `RRCReject` † | `wait_time`(있으면) |
| RRC | UL | `RRCSetupComplete` | `s_tmsi`(단말이 5G-S-TMSI를 준 경우 48비트) |
| RRC | DL | `SecurityModeCommand` | `cipher` `"nea0"`~`"nea3"`, `integrity` `"nia0"`~`"nia3"` |
| RRC | UL | `SecurityModeComplete` · `SecurityModeFailure` † | — |
| RRC | DL | `UECapabilityEnquiry` | — |
| RRC | UL | `UECapabilityInformation` | — (능력 내용은 보내지 않음) |
| RRC | DL | `RRCRelease` | `suspend`(불리언) |
| NAS | UL | `RegistrationRequest` | `reg_type` `"initial"`·`"mobility"`·`"periodic"`·`"emergency"`, `id_type` `"SUCI"`·`"5G-GUTI"`·`"IMEI"`·`"IMEISV"`, `s_tmsi`(5G-GUTI일 때) |
| NAS | DL | `IdentityRequest` | — |
| NAS | UL | `IdentityResponse` | — (식별자 종류·값은 보내지 않음) |
| NAS | DL | `AuthenticationRequest` · `AuthenticationReject` † | — |
| NAS | UL | `AuthenticationResponse` | — |
| NAS | UL | `AuthenticationFailure` | `cause`(5GMM 원인값 — 21 = 동기 실패) |
| NAS | DL | `SecurityModeCommand` | `cipher` `"5G-EA0"`~`"5G-EA3"`, `integrity` `"5G-IA0"`~`"5G-IA3"` |
| NAS | UL | `SecurityModeComplete` | — |
| NAS | UL | `SecurityModeReject` | `cause` |
| NAS | DL | `RegistrationAccept` | `s_tmsi`(새로 준 5G-GUTI의 5G-S-TMSI) |
| NAS | UL | `RegistrationComplete` | — |
| NAS | DL | `RegistrationReject` · `ServiceReject` † | `cause` |
| NAS | UL | `ServiceRequest` | `s_tmsi` |
| NAS | DL | `ServiceAccept` | — |
| NAS | UL·DL | `DeregistrationRequest` † | `switch_off`(불리언) |
| F1AP | DL | `UEContextReleaseCommand` | `cause`(`"radioNetwork:…"` 형식) |
| F1AP | UL | `UEContextReleaseRequest` † | `cause` |
| F1AP | UL | `UEContextReleaseComplete` | — (**연결 끝**) |

### 3.8 받지 않는 것

- **단독 `ue_evt`**와 **100 ms 원본 `kpm2`**는 상시로 오지 않는다(전송기 `send_ue_evt` 기본 `false`, 27_ §4.2·§9 D4). 단독 줄로 `/ingest`에 오면 거부해 `rejected.jsonl`에 남긴다. 둘 다 경보 근거로 `evidence.raw` 안에 담겨 온다(3.2·3.7절).

## 4. TeleRAN Table I·II와의 대응

TeleRAN 논문([`reference/TeleRAN.pdf`](../reference/TeleRAN.pdf) 4쪽)의 Table II는 KPM2, Table I은 KPM1(팀 용어 eKPM)이다(27_ §2.1). v0.2에서 고정했던 지표 이름 24개(`metric.name`)는 이 대응으로 바뀐다.

### 4.1 KPM2 = Table II (3GPP TS 28.552 셀 카운터) → `kpm2`의 `cc`·`si` 키

탐지 엔진은 측정 이름을 바꾸지 않는다. 그래서 키 이름이 Table II와 같다.

| Table II 이름 | 종류 | `kpm2` 키 | 값 (27_ §4.1) | TS 28.552 |
|---|---|---|---|---|
| `RRC.ConnEstabAtt` | CC | `cc.RRC.ConnEstabAtt` | `{total, <설정 원인>…}` | 5.1.1.15.1 |
| `RRC.ConnEstabSucc` | CC | `cc.RRC.ConnEstabSucc` | `{total, <설정 원인>…}` | 5.1.1.15.2 |
| `RRC.ConnEstabFailCause` | CC | `cc.RRC.ConnEstabFailCause` | `{NetworkReject, NoReply, Other}` | 5.1.1.15.3 |
| `RRC.RelWithoutSuspendConfig` | CC | `cc.RRC.RelWithoutSuspendConfig` | 수 | 5.1.1.15.4 |
| `UECNTX.ConnEstabAtt` | CC | `cc.UECNTX.ConnEstabAtt` | `{total, <원인>…}` | 5.1.1.16.1 |
| `UECNTX.ConnEstabSucc` | CC | `cc.UECNTX.ConnEstabSucc` | `{total, <원인>…}` | 5.1.1.16.2 |
| `RRC.ReEstabAtt` | CC | `cc.RRC.ReEstabAtt` | 수 (지금은 `null` 예상) | 5.1.1.17.1 |
| `RRC.ReEstabSuccWithUeContext` | CC | `cc.RRC.ReEstabSuccWithUeContext` | 수 (지금은 `null` 예상) | 5.1.1.17.2 |
| `RRC.ResumeAtt` | CC | `cc.RRC.ResumeAtt` | 수 (지금은 `null` 예상) | 5.1.1.18.1 |
| `RRC.ResumeSucc` | CC | `cc.RRC.ResumeSucc` | 수 (지금은 `null` 예상) | 5.1.1.18.2 |
| `RRC.ConnMean` | SI | `si.RRC.ConnMean` | 평균(실수) | 5.1.1.4.1 |
| `RRC.ConnMax` | SI | `si.RRC.ConnMax` | 최댓값 | 5.1.1.4.2 |
| `RRC.InactiveConnMean` | SI | `si.RRC.InactiveConnMean` | 평균 | 5.1.1.4.3 |
| `RRC.InactiveConnMax` | SI | `si.RRC.InactiveConnMax` | 최댓값 | 5.1.1.4.4 |

탐지 쪽 확장 3종(Table II 아님): `ext.UeCtxMax`(UE 컨텍스트 수 최댓값, 셀 한도 96), `ext.DuCannotServe`, `ext.CrntiAlloc`.

### 4.2 KPM1 = Table I (UE별 보안 텔레메트리) → `ue_evt` (`evidence.raw` 안, 형식은 3.7절)

| Table I 항목 | `ue_evt`의 어디에 (27_ §4.2) |
|---|---|
| UE C-RNTI | 모든 줄의 `crnti` (10진 정수) |
| UE S-TMSI | `RRCSetupRequest`의 `f.ue_identity`(Part1), `RRCSetupComplete`·`RegistrationRequest`·`ServiceRequest`·`RegistrationAccept`의 `f.s_tmsi` |
| UE Cipher Algorithm · UE Integrity Algorithm | RRC·NAS `SecurityModeCommand`의 `f.cipher`·`f.integrity` |
| RRC Message ID · NAS Message ID | `proto` + `msg` (메시지 이름 문자열) |
| UE RRC State · UE NAS State · UE RRC Security State · UE NAS Security State | 분석 엔진이 보내지 않는다. 탐지 엔진이 메시지 순서로 만들어 일부 룰의 `ues[].values`에 `rrc_sec`·`nas_sec`으로 싣는다 |

v0.2의 숫자 코드표(상태·알고리즘·메시지 ID)는 쓰지 않는다. `ue_evt`는 메시지 이름과 알고리즘 이름을 문자열로 보낸다.

## 5. InfluxDB 저장 형태 (참고)

collector가 아래처럼 변환한다. 보내는 쪽은 신경 쓰지 않아도 된다.

| measurement | time | tags | fields |
|---|---|---|---|
| `alert` | `t` | env, alert_id, rule, stage, kind, event, cell | severity, mode, unit, fmt, branch, reason, ues_total, duration_ms, evidence_sent, evidence_dropped, session, rep_key·rep_value(대표 값), `cond`·`candidates`·`conditions`·`values`·`params`·`refs`·`ues`는 `<이름>_json`(JSON 문자열) |
| `evidence` | 원본 시각(`raw.t_ms` 또는 `raw.t_start_ms`) + `seq` | env, alert_id, phase, raw_type, cell, session | seq, du_ue_id, uid, raw_json, (KPM1) msg·dir·proto, (KPM2) `cc.*`·`si.*`·`ext.*` 실수 |
| `gap` | `t_from` | env, alert_id, cell | t_to, seq_from, seq_to, session |
| `kpm2` | `t_start_ms` | env, session, cell, agg_ms | t_end_ms, n, seq_from, seq_to, partial_json, `cc.<이름>[.<하위 키>]`·`si.<이름>`·`ext.<이름>` 실수 |
| `hello` | 받은 시각 | env, session | seq, producer, node_id, clock, period_ms, noreply_timeout_ms, si_sample_ms, ue_evt, cells_json |
| `f1_evt` | `t_ms` + `seq` | env, session | seq, msg, cells_json, du_ue_ids_json |
| `alert_ue` | `ues[].t_hit` | env, alert_id, ue(`<cell>-<du_ue_id>-<uid>`) | cell, du_ue_id, uid, cu_ue_id, crnti, s_tmsi, cond, uncertain, conditions, peers(쉼표·`;`로 이은 문자열), seq_from, seq_to, evidence, values_json, event |
| `overhead` | `t_start_ms` | env, session, node(`node_id`, 있을 때) | t_end_ms, seq, process_scope, cpu_count, node_busy_cores·process_cores(실수), mem_total_bytes·mem_used_bytes·process_rss_bytes |
| `overhead_link` | `t_start_ms` | env, session, node, iface(`interface_name`), role | t_end_ms, seq, ingress_sctp_packets, ingress_wire_bytes, egress_sctp_packets, egress_wire_bytes |
| `ingest_delay` | 받은 시각 + 요청 안 순번(ns) | env, type(`kpm2`·`overhead`·`alert`·`f1_evt`), event(`alert`만) | delay_ms(실수) |

- **시각**: ms를 ns로 바꿔 쓴다. 같은 ms에 여러 줄이 올 수 있어(27_ §4.2) `evidence`·`f1_evt`는 ms 안의 ns 자리에 `seq`를 넣어 가른다(`t_ms × 10⁶ + seq mod 10⁶`). 표시 시각은 1 ms 안에서만 달라진다.
- **`alert_id`를 tag로 둔다**(field로는 두지 않는다 — 같은 이름의 tag·field가 있으면 pivot 때 열이 겹친다). 같은 원본 줄이 두 경보의 근거로 함께 올 수 있어(예: `L3-24`·`L3-14` 판정 보류 경보) `alert_id`가 series를 가르지 않으면 서로 덮어쓴다. 경보는 공격마다 하나라 series 수는 경보 수에 비례한다(경보 하나에 `evidence` series 3개 정도).
- **세션**: `alert`·`gap`의 `session` 필드는 그 경보의 첫 `evidence`에서 알게 된다. 경보를 먼저 쓴 뒤 세션을 알면 같은 점에 `session` 필드만 더해 쓴다.
- **숫자 타입**: `kpm2`·근거 `kpm2`의 지표는 모두 실수로 쓴다(정수·실수가 섞이면 InfluxDB가 쓰기를 거부함, 27_ §7.1). `values`·`params`·`ues`처럼 룰마다 다른 묶음은 JSON 문자열로 통째 저장하고 화면에서 펼친다.
- **대표 값** `rep_value`: 화면에 값 하나만 보일 때 쓰는 룰별 값(27_ §5.3 '대표 값(제안)'). 판정 보류 경보는 `held_w`. `rep_key`가 어떤 값인지 알려 준다.
- **`overhead_link`**: `overhead`의 `link[]` 한 칸(NIC 하나) = 점 하나(M11, `alert_ue`와 같은 이유). 값은 구간 증가분이라 초당 값은 화면에서 구간 길이(`t_end_ms` − 시각)로 나눈다.
- **`ingest_delay`**: 메시지가 아니라 collector가 재는 값(D211) — `/ingest`로 받은 줄마다 받은 시각 − 데이터 시각(`kpm2`·`overhead`는 `t_end_ms`, `alert`는 `t`, `f1_evt`는 `t_ms`). 메시지 형식은 바뀌지 않는다.
- **`alert_ue`**: `alert`의 `ues[]` 한 칸 = 점 하나(M10). 경보 상세의 '걸린 UE' 표를 행으로 그리려고 따로 둔다(`ues_json` 배열은 Flux·Grafana에서 행으로 펴기 어렵다). `update`에는 새로 걸린 UE만 오므로 모으면 그 경보의 전체 UE다.

## 6. `overhead` — 수집 오버헤드 (11/13 탐지 쪽 형식, M11)

분석 엔진(계측기)이 `kpm2`·`ue_evt`·`f1_evt`와 **같은 소켓, 같은 번호열**(`session`·`seq`)로 구간마다 한 줄 낸다. 구간은 `--overhead-ms`(기본 3,000 ms) — 상시 `kpm2`와 같은 3초다. 전송기가 줄 그대로 `/ingest`로 보낸다.

```json
{"type":"overhead","ver":1,"session":"20261113T043024Z","seq":37,"node_id":"cu","process_scope":"self","t_start_ms":1794544261000,"t_end_ms":1794544264000,"cpu":{"count":4,"node_busy_cores":0.03,"process_cores":0},"memory":{"total_bytes":8153268224,"used_bytes":4623908864,"process_rss_bytes":323219456},"link":[{"interface_name":"ens5","role":"f1","ingress":{"sctp_packet_count":0,"wire_byte_count":0},"egress":{"sctp_packet_count":0,"wire_byte_count":0}}]}
```

| 필드 | 뜻 |
|---|---|
| `ver` | 줄 형식 판. `1`이 아니면 거부 |
| `session` · `seq` | 계측기 기동 시각(UTC, 재시작하면 바뀜)과 그 세션 안의 줄 번호 — `kpm2`·`ue_evt`·`f1_evt`와 한 번호열 |
| `node_id` | 어느 박스의 부하인가(`cu`로 통일 — 11/13). 계측기에 `--node`를 안 주면 키가 없다(`hello`와 같은 규칙) |
| `process_scope` | `process_*` 값이 덮는 범위. `self` = 계측기 프로세스 하나. 탐지 판정·전송은 다른 프로세스라 그 몫은 `node_*`에만 섞여 있다 |
| `t_start_ms` · `t_end_ms` | 이 줄이 덮는 구간(벽시계 epoch ms) |
| `cpu.count` | 노드 코어 수(아래 두 값의 분모, 1 이상) |
| `cpu.node_busy_cores` | 구간 동안 노드가 바쁘게 돈 코어 수의 평균(실수) |
| `cpu.process_cores` | 같은 구간에 계측기가 쓴 코어 수의 평균. `0`은 유효한 측정값(한가했음) |
| `memory.total_bytes` · `used_bytes` | 노드 전체·사용 중(MemTotal − MemAvailable), 구간 끝 순간값 |
| `memory.process_rss_bytes` | 계측기 프로세스의 resident |
| `link[]` | 선언한 NIC마다 한 칸: `interface_name`(필수), `role`(`f1`·`n2`·`f1+n2`), `ingress`(들어옴, F1이면 DU → CU)·`egress`(나감)의 `sctp_packet_count`·`wire_byte_count`(구간 증가분 — 누적·초당 값 아님). **SCTP 패킷만 센다**(F1AP·NGAP 시그널링, F1-U 사용자 데이터 GTP-U는 빠짐 — 11/13). 바이트는 이더넷 헤더 포함·FCS 제외, GSO로 묶인 패킷은 세그먼트 수만큼 |

- 숫자를 못 읽었으면 `null`(첫 구간의 `link` 증가분도 `null`). `null`·빈 객체·키 없음은 모두 "값 없음"으로 받아 InfluxDB에서 그 필드를 뺀다.
- 점유율(%)은 보내는 쪽이 나누지 않는다(분모를 잃으면 0.5가 몇 코어의 절반인지 모름). 화면에서 `node_busy_cores` / `count`로 계산한다.
- 검사: 위 형식과 타입(정수·0 이상, `count` ≥ 1), 모르는 필드는 받는다. `t_start_ms` ≥ `t_end_ms`면 저장하고 경고만 남긴다.

## 7. 직접 검증해 보기

collector를 InfluxDB 없이 띄워 놓고 내 프로그램이 보내게 하면, 거부된 줄과 사유가 `recordings/rejected.jsonl`에 쌓인다.

```bash
python -m collector.collector --dry-run --in http://127.0.0.1:8088            # 탐지 엔진 전송기 (2.4절)
python -m collector.collector --dry-run                                       # UDP 127.0.0.1:9999로 받기(시험용)
python -m collector.collector --dry-run --in file://out.jsonl --once --env lab   # 파일 검사
```

또는 파일을 한 줄씩 검사:

```bash
python -c "import json,sys; from common.schema import validation_errors as v; \
[print(i, v(json.loads(l)) or 'OK') for i,l in enumerate(open(sys.argv[1]),1)]" my_messages.jsonl
```

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| 0.1 | 2026-10-19 | 최초 작성 (CLAUDE.md 5절 기준) |
| 0.1 | 2026-10-19 | 문서만: 시각 순서는 collector가 경고로 처리, `--dry-run` 검증 방법 추가 (스키마 변경 없음) |
| 0.1 | 2026-10-19 | 문서만: 6절 지표를 TeleRAN 논문 Table I·II 기준으로 바꾸고 코드표 추가 (스키마 변경 없음) |
| 0.2 | 2026-11-04 | (커밋 전에 0.3에 합침) 지표 이름을 TeleRAN Table I·II의 24개로 고정 |
| 0.3 | 2026-11-09 | **탐지 엔진 레코드 6종 추가**(`alert`·`evidence`·`gap`·`kpm2`·`hello`·`f1_evt`, 27_ 명세 그대로 — ms 시각, 모르는 필드 받음, `fmt`·`ver` 1). `POST /ingest`·`X-Env`·중복 키(2절). Table I·II 대응을 `kpm2` 키와 `ue_evt` 필드로 바꿈(4절). `evidence.raw`가 KPM1 `ue_evt`면 타임라인 필드 7개(`t_ms`·`cell_id`·`du_ue_id`·`dir`·`proto`·`msg`·`type`)를 검사(3.7절, `$defs.ue_evt`). `metric`·`detection`·`attack_run`은 mock 전용·교체 예정으로 6절에 모음. 스키마 `$defs.evidence`(탐지 근거 항목)는 `$defs.detection_evidence`로 이름만 바꿈 |
| 0.4 | 2026-11-11 | `metric`·`detection`·`attack_run`(mock 전용)을 mock 생성기·evaluator·옛 대시보드와 함께 **삭제**(M10). `overhead`만 처음 형식으로 남김(6절). InfluxDB `alert_ue`(걸린 UE 한 칸 = 점 하나) 추가(5절) |
| 0.5 | 2026-11-13 | **`overhead`를 탐지 쪽 형식으로 바꿈**(M11, 6절): 분석 엔진이 3초마다 `/ingest`로, ms 구간 `t_start_ms`·`t_end_ms`, `session`·`seq`(중복 키), `ver` 1, 노드·계측기 CPU(코어 수)·메모리(바이트)·NIC별 링크 증가분, 모르는 필드 받음. 옛 형식(ns `ts`·`node`·`ebpf_on`·`cpu_pct`·`mem_mb`, 모르는 필드 거부)과 `$defs.epoch_ns`·`$defs.node` 삭제. InfluxDB `overhead`를 새 필드로, `overhead_link` 추가(5절) |
