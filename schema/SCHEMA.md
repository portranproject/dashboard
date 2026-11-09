# PortRAN 메시지 스키마 (v0.3)

collector가 받는 메시지 형식이다. **기계 검증의 단일 기준은 [`messages.schema.json`](messages.schema.json)**이고, 이 문서는 그 내용을 사람이 읽기 쉽게 풀어 쓴 것이다. 둘이 다르면 JSON Schema가 맞다.

메시지는 두 갈래다.

| 갈래 | `type` | 보내는 곳 | 기준 |
|---|---|---|---|
| **탐지 엔진 레코드** | `alert` · `evidence` · `gap` · `kpm2` · `hello` · `f1_evt` | 탐지 엔진 전송기 (`POST /ingest`) | 탐지 엔진 담당 명세 [`27_탐지엔진_1-4단계-대시보드-지표_명세서.md`](../reference/detection/27_탐지엔진_1-4단계-대시보드-지표_명세서.md) (2026-11-05 확정, 이하 **27_**). 뜻·룰별 값은 27_이 기준이고, 이 문서는 collector가 무엇을 검사하고 어떻게 저장하는지를 적는다 |
| **옛 메시지** | `metric` · `detection` · `attack_run` | mock 생성기만 | **교체 예정.** 대시보드를 탐지 엔진 레코드로 재구성할 때 지운다(6절) |
| | `overhead` | 미정 | 측정 주체·형식을 탐지 쪽과 협의 중(R5)이라 옛 형식 그대로 둔다 |

> 스키마를 바꾸고 싶으면 먼저 팀에 공유하고 합의한 뒤 두 파일을 함께 고친다. 탐지 엔진 레코드는 27_이 바뀌면 따라 고친다.

## 1. 공통 규칙

| 항목 | 탐지 엔진 레코드 | 옛 메시지 |
|---|---|---|
| 전송 단위 | JSON 한 줄 = 레코드 하나 (JSON Lines, UTF-8) | 같음 |
| 전송 방식 | `POST /ingest` (2절). 시험용으로 UDP·파일도 받는다(이때 환경은 collector `--env`) | UDP(기본 `127.0.0.1:9999`, 데이터그램 하나에 한 줄) 또는 파일 |
| 시각 | **Unix epoch 밀리초 정수** — 분석 엔진이 붙인 데이터 시각(27_ §2.3). 2001-09-09 ~ 2286년 범위만 받는다(초·마이크로초·나노초로 잘못 보낸 값을 잡으려고) | **Unix epoch 나노초 정수** (2001-09-09 이후) |
| 모르는 필드 | **받는다.** 녹화에는 그대로 남고 InfluxDB 저장과 화면에서는 무시한다. 탐지 쪽은 필드를 더할 때 형식 판을 올리지 않는다(27_ §2.4) | **거부한다.** 오타(`ts_detect` 등)를 바로 잡기 위해서다 |
| 형식 판 | `alert`의 `fmt`, `kpm2`·`hello`·`f1_evt`의 `ver`가 `1`이 아니면 거부(대시보드 2차 답변서 D8, 27_ §9) | — |
| `null` | "그 값을 셌어야 하는데 모름". 키가 없음 = 해당 없음. InfluxDB에는 그 필드를 빼고 쓴다(그래프에서 0이 아니라 '데이터 없음') | 허용하지 않음 |
| 다시 보낸 줄 | 환경 + 레코드별 키가 같으면 한 번만 저장(2.3) | 거르지 않음 |

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
| `hello` · `f1_evt` | (`session`, `seq`) |

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
{"type":"alert","fmt":1,"alert_id":"S1-L3-01-V-1-65","event":"raise","rule":"L3-01-V","stage":1,"unit":"cell","kind":"attack","cell":1,"t":1792209006400,"severity":"medium","mode":"normal","cond":["C1","C2","C2a"],"candidates":["L3-11"],"values":{"a_w":13,"f_w":12,"ratio":0.9230769230769231,"base":1.0},"params":{"k":3.0,"theta":0.5,"f_abs":10},"refs":{"a":[46,55],"f":[56,65]}}
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

v0.2의 숫자 코드표(상태·알고리즘·메시지 ID)는 쓰지 않는다. `ue_evt`는 메시지 이름과 알고리즘 이름을 문자열로 보낸다. 옛 코드표는 mock 전용으로 6.5절에 남는다.

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
| `metric` · `detection` · `attack_run` · `overhead` | 6절 | | |

- **시각**: ms를 ns로 바꿔 쓴다. 같은 ms에 여러 줄이 올 수 있어(27_ §4.2) `evidence`·`f1_evt`는 ms 안의 ns 자리에 `seq`를 넣어 가른다(`t_ms × 10⁶ + seq mod 10⁶`). 표시 시각은 1 ms 안에서만 달라진다.
- **`alert_id`를 tag로 둔다**(field로는 두지 않는다 — 같은 이름의 tag·field가 있으면 pivot 때 열이 겹친다). 같은 원본 줄이 두 경보의 근거로 함께 올 수 있어(예: `L3-24`·`L3-14` 판정 보류 경보) `alert_id`가 series를 가르지 않으면 서로 덮어쓴다. 경보는 공격마다 하나라 series 수는 경보 수에 비례한다(경보 하나에 `evidence` series 3개 정도).
- **세션**: `alert`·`gap`의 `session` 필드는 그 경보의 첫 `evidence`에서 알게 된다. 경보를 먼저 쓴 뒤 세션을 알면 같은 점에 `session` 필드만 더해 쓴다.
- **숫자 타입**: `kpm2`·근거 `kpm2`의 지표는 모두 실수로 쓴다(정수·실수가 섞이면 InfluxDB가 쓰기를 거부함, 27_ §7.1). `values`·`params`·`ues`처럼 룰마다 다른 묶음은 JSON 문자열로 통째 저장하고 화면에서 펼친다.
- **대표 값** `rep_value`: 화면에 값 하나만 보일 때 쓰는 룰별 값(27_ §5.3 '대표 값(제안)'). 판정 보류 경보는 `held_w`. `rep_key`가 어떤 값인지 알려 준다.

## 6. 옛 메시지 — mock 전용 (교체 예정)

`metric`·`detection`·`attack_run`은 mock 생성기와 지금 대시보드·evaluator·replay가 쓴다. 실제 파트는 보내지 않는다(탐지 엔진은 3절 레코드를 보내고, 정답 기록은 받지 않기로 함 — 평가는 전체 파이프라인 완성 뒤 탐지 쪽과 함께 정한다, 27_ §9). 대시보드를 재구성할 때 이 절을 지운다. `overhead`는 R5 협의 전까지 남긴다.

### 6.1 `metric`

```json
{"type":"metric","ts":1763280000123456789,"src":"ebpf","node":"cu",
 "kind":"ekpm","name":"rrc_msg_id","value":0,"unit":"code",
 "labels":{"cell":"1","ue":"0x4601"}}
```

필수: `type` · `ts`(ns) · `src`(`ebpf`·`kpm`) · `node`(`cu`·`du`·`core`) · `kind`(`ekpm`·`kpm`) · `name`(영문자로 시작, 영숫자·`_`·`.`·`-`) · `value`(숫자) · `unit`(문자열). 선택: `labels`(`cell`·`ue` 문자열만). mock은 6.5절의 이름만 낸다.

### 6.2 `detection`

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
   {"source":"ebpf","metric":"count(rrc_msg_id=RRCSetupRequest)","op":">","value":5,"threshold":2,"window_ms":1000},
   {"source":"kpm","metric":"RRC.ConnEstabAtt","op":">","value":25,"threshold":10,"window_ms":5000}
 ]}
```

| 필드 | 내용 |
|---|---|
| 필수 | `event_id` · `ts_detected`·`ts_first_evidence`(ns) · `attack_type`(6.3절 열거) · `severity`(`low`·`medium`·`high`·`critical`) · `ruleset`(`full`·`kpm_only`) · `rule_id` · `rule_version` · `target.node` · `evidence`(1개 이상) |
| `evidence[]` | `source`(`ebpf`·`kpm`) · `metric` · `op`(`>` `>=` `<` `<=` `==` `!=`) · `value` · `threshold` · `window_ms`(0 이상 정수) 모두 필수 |
| 선택 | `target.cell`(문자열), `target.ue`(문자열 배열) |

탐지 지연 = `ts_detected - ts_first_evidence`. `ts_first_evidence > ts_detected`면 collector가 경고만 하고 저장한다.

### 6.3 `attack_run`

```json
{"type":"attack_run","run_id":"run-007","scenario":"RRC_SIGNALING_STORM",
 "ts_start":1763280000000000000,"ts_end":1763280060000000000,
 "params":{"rate":200,"fake_ue_count":50}}
```

필수: `run_id` · `scenario` · `ts_start`·`ts_end`(ns, 어긋나면 경고만) · `params`(객체, 없으면 `{}`). `scenario`·`attack_type` 값: `RRC_SIGNALING_STORM` · `ABNORMAL_UE_ATTACH` · `F1AP_MSG_TAMPER`(목록 밖은 거부).

### 6.4 `overhead` (R5 협의 전까지 유지)

```json
{"type":"overhead","ts":1763280000000000000,"node":"cu","ebpf_on":true,"cpu_pct":23.4,"mem_mb":512}
```

필수: `ts`(ns) · `node` · `ebpf_on`(불리언, 문자열 `"true"`는 거부) · `cpu_pct`·`mem_mb`(0 이상 숫자, 멀티코어 합산이면 100을 넘을 수 있음).

### 6.5 mock 지표 이름과 코드표

mock은 Table I을 eKPM 10개(`ue_c_rnti` · `ue_s_tmsi` · `ue_cipher_alg` · `ue_integrity_alg` · `ue_rrc_state` · `ue_nas_state` · `ue_rrc_sec_state` · `ue_nas_sec_state` · `rrc_msg_id` · `nas_msg_id`, `src: "ebpf"`, `unit` `code`·`id`)로, Table II를 14개 이름 그대로(`src: "kpm"`, `unit: "count"`, 1초마다) 낸다. 상태·알고리즘·메시지 ID의 숫자 코드표는 [`mock/scenarios.yaml`](../mock/scenarios.yaml)의 `codes`에 있다(mock 전용 가안).

### 6.6 InfluxDB 저장 형태

| measurement | time | tags | fields |
|---|---|---|---|
| `metric` | `ts` | src, node, kind, name, cell, ue | value(float), unit |
| `detection` | `ts_detected` | attack_type, severity, ruleset, rule_id, node | event_id, rule_version, ts_first_evidence, latency_ms, cell, ue_list(JSON 문자열), evidence_json(JSON 문자열) |
| `attack_run` | `ts_start` | scenario | run_id, ts_end, params_json |
| `overhead` | `ts` | node, ebpf_on | cpu_pct, mem_mb |

## 7. 직접 검증해 보기

collector를 InfluxDB 없이 띄워 놓고 내 프로그램이 보내게 하면, 거부된 줄과 사유가 `recordings/rejected.jsonl`에 쌓인다.

```bash
python -m collector.collector --dry-run --in http://127.0.0.1:8088            # 탐지 엔진 전송기 (2.4절)
python -m collector.collector --dry-run                                       # UDP 127.0.0.1:9999로 받기
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
