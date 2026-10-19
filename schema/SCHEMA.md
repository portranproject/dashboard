# PortRAN 메시지 스키마 (v0.1 가안)

eBPF 에이전트, 탐지 엔진, 공격 도구, mock 생성기가 collector로 보내는 메시지 형식이다.
**기계 검증의 단일 기준은 [`messages.schema.json`](messages.schema.json)**이고, 이 문서는 그 내용을 사람이 읽기 쉽게 풀어 쓴 것이다.
둘이 다르면 JSON Schema가 맞다.

> 스키마를 바꾸고 싶으면 먼저 팀에 공유하고 합의한 뒤 두 파일을 함께 고친다.

## 1. 공통 규칙

| 항목 | 규칙 |
|---|---|
| 전송 단위 | JSON 한 줄 = 메시지 하나 (JSON Lines, UTF-8, 줄 끝 `\n`) |
| 전송 방식 | UDP (기본 `127.0.0.1:9999`, 데이터그램 하나에 한 줄) 또는 파일에 한 줄씩 추가 |
| 시각 | **Unix epoch 나노초 정수**. 예: `1763280000123456789` |
| 종류 구분 | `type` = `metric` \| `detection` \| `attack_run` \| `overhead` |
| 모르는 필드 | **거부된다.** 오타(`ts_detect` 등)를 바로 잡기 위해서다. 필드를 추가하려면 스키마부터 고친다 |

시각 관련 주의:
- 초(`1763280000`)·밀리초·마이크로초 값을 넣으면 거부된다(2001-09-09 이후의 ns 값만 허용).
- 실수(`1763280000123456789.0`)나 문자열(`"1763280000123456789"`)도 거부된다.
  (JSON Schema 표준은 `1.0`을 정수로 보지만, 우리 검증기 `common/schema.py`는 정밀도 손실을 막기 위해 실수 표기를 거부한다. `window_ms`도 마찬가지)
- 숫자 필드에 `NaN`, `Infinity`는 거부된다.
- ns 정수는 2^53보다 커서 JavaScript, `jq` 등에서는 정밀도가 깨진다. C++은 `int64_t`/`uint64_t`, Python은 기본 `int`로 다루면 안전하다.

검증되지 않은 메시지는 collector가 버리지 않고 `recordings/rejected.jsonl`에 사유와 함께 남긴다.

## 2. metric — eKPM / 표준 KPM 지표

```json
{"type":"metric","ts":1763280000123456789,"src":"ebpf","node":"cu",
 "kind":"ekpm","name":"rrc_setup_req_rate","value":120.0,"unit":"req/s",
 "labels":{"cell":"1","ue":"0x4601"}}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"metric"` | O | |
| `ts` | 정수(ns) | O | 측정 시각 |
| `src` | `ebpf` \| `kpm` | O | 수집 경로 |
| `node` | `cu` \| `du` \| `core` | O | 측정 대상 노드 |
| `kind` | `ekpm` \| `kpm` | O | 보안 지표(eKPM)인지 표준 KPM인지 |
| `name` | 문자열 | O | 지표 이름. 영문자로 시작, 영숫자·`_`·`.`·`-`만. **가안**(4절) |
| `value` | 숫자 | O | |
| `unit` | 문자열 | O | 예: `req/s`, `ratio`, `%`, `Mbps`. 단위가 없으면 `""` |
| `labels` | 객체 | X | `cell`(문자열), `ue`(문자열)만 허용 |

## 3. detection — 탐지 이벤트

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

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"detection"` | O | |
| `event_id` | 문자열 | O | 이벤트 고유 ID |
| `ts_detected` | 정수(ns) | O | 탐지 엔진이 판정한 시각 |
| `ts_first_evidence` | 정수(ns) | O | 판정에 쓰인 근거 중 가장 이른 데이터의 시각 |
| `attack_type` | 열거형 | O | 4절 공격 유형 중 하나 |
| `severity` | `low` \| `medium` \| `high` \| `critical` | O | |
| `ruleset` | `full` \| `kpm_only` | O | `full` = eKPM + KPM 룰, `kpm_only` = 표준 KPM 룰만 |
| `rule_id` | 문자열 | O | 예: `R-RRC-001` |
| `rule_version` | 문자열 | O | 예: `1.0` |
| `target.node` | `cu` \| `du` \| `core` | O | |
| `target.cell` | 문자열 | X | |
| `target.ue` | 문자열 배열 | X | 대상 UE 목록. F1AP처럼 UE가 특정되지 않으면 생략 |
| `evidence` | 배열(1개 이상) | O | 아래 표 |

`evidence` 항목 (모두 필수):

| 필드 | 타입 | 설명 |
|---|---|---|
| `source` | `ebpf` \| `kpm` | |
| `metric` | 문자열 | 지표 이름 |
| `op` | `>` `>=` `<` `<=` `==` `!=` | |
| `value` | 숫자 | 관측값 |
| `threshold` | 숫자 | 임계값 |
| `window_ms` | 0 이상 정수 | 집계 윈도우 |

- 탐지 지연 = `ts_detected - ts_first_evidence`
- `ts_first_evidence <= ts_detected`여야 한다. JSON Schema로는 표현할 수 없어서 collector가 따로 검사하고, 어긋나면 **경고 로그만 남기고 저장한다**(노드 간 시계 차이로 데이터를 잃지 않도록).
- `kpm_only` 룰셋의 이벤트는 evidence에 `source: "kpm"`만 들어가는 것이 자연스럽다(강제하지는 않음).

## 4. attack_run — 정답 기록 (공격 도구가 출력)

```json
{"type":"attack_run","run_id":"run-007","scenario":"RRC_SIGNALING_STORM",
 "ts_start":1763280000000000000,"ts_end":1763280060000000000,
 "params":{"rate":200,"fake_ue_count":50}}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"attack_run"` | O | |
| `run_id` | 문자열 | O | 공격 실행 고유 ID |
| `scenario` | 열거형 | O | 공격 유형. detection의 `attack_type`과 같은 값 |
| `ts_start` | 정수(ns) | O | 공격 시작 |
| `ts_end` | 정수(ns) | O | 공격 종료 (`ts_start` 이상. 어긋나면 collector가 경고만 함) |
| `params` | 객체 | O | 공격 파라미터. 내용은 자유, 없으면 `{}` |

> TODO: 공격 도구가 이 메시지를 **시작 시점**(예정 종료 시각)에 낼지 **종료 시점**(실제 종료 시각)에 낼지 공격 도구 담당과 정해야 한다.
> evaluator는 어느 쪽이든 동작하지만, 실시간 대시보드의 구간 표시는 메시지가 도착한 뒤에야 보인다.

### 공격 유형 (가안)

| 값 | 설명 |
|---|---|
| `RRC_SIGNALING_STORM` | 대량 RRC 연결 요청으로 CU 시그널링 자원 고갈 |
| `ABNORMAL_UE_ATTACH` | 비정상 패턴의 단말 접속 시도 반복 |
| `F1AP_MSG_TAMPER` | CU-DU 간 F1AP 메시지 위·변조 |

목록에 없는 값은 거부된다. 유형을 추가하면 스키마의 `$defs.attack_type`을 고친다.

## 5. overhead — 수집 오버헤드

```json
{"type":"overhead","ts":1763280000000000000,"node":"cu","ebpf_on":true,"cpu_pct":23.4,"mem_mb":512}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `type` | `"overhead"` | O | |
| `ts` | 정수(ns) | O | |
| `node` | `cu` \| `du` \| `core` | O | |
| `ebpf_on` | 불리언 | O | eBPF 수집 켜짐 여부. 문자열 `"true"`는 거부 |
| `cpu_pct` | 0 이상 숫자 | O | 멀티코어 합산이면 100을 넘을 수 있다 |
| `mem_mb` | 0 이상 숫자 | O | |

## 6. 지표 이름과 코드 (가안)

TeleRAN 논문(Wen et al., *Towards Bridging the Telemetry Gap for Security Applications in 6G OpenRANs via eBPF*)의 Table I을 eKPM, Table II를 표준 KPM으로 쓴다.
1~5절 예시의 지표 이름(`rrc_setup_req_rate` 등)은 형식을 보여 주기 위한 것이다.

> TODO: 이름·코드·`labels.ue`의 의미는 eBPF 팀과 확정 예정. 스키마는 이름 형식만 검사하므로 바뀌어도 스키마 수정은 필요 없다.

### 6.1 eKPM (Table I) — `src: "ebpf"`, `kind: "ekpm"`, `labels: {cell, ue}`

UE별 값이라 매 초가 아니라 **그 값이 바뀌거나 메시지를 처리할 때** 낸다. 값은 숫자 코드(6.3절) 또는 식별자다.

| 이름 | 논문 항목 | 종류 · 처리 위치 | 값 | 낼 때 |
|---|---|---|---|---|
| `ue_c_rnti` | UE C-RNTI | Metadata · F1AP | C-RNTI (정수) | 할당될 때, F1AP에서 볼 때 |
| `ue_s_tmsi` | UE S-TMSI | Metadata · RRC | S-TMSI (48비트 정수) | 할당·보고될 때 |
| `ue_cipher_alg` | UE Cipher Algorithm | Metadata · RRC | 코드 (NEA0~3) | 바뀔 때 |
| `ue_integrity_alg` | UE Integrity Algorithm | Metadata · RRC | 코드 (NIA0~3) | 바뀔 때 |
| `ue_rrc_state` | UE RRC State | State · RRC | 코드 | 바뀔 때 |
| `ue_nas_state` | UE NAS State | State · NAS | 코드 | 바뀔 때 |
| `ue_rrc_sec_state` | UE RRC Security State | State · RRC | 코드 | 바뀔 때 |
| `ue_nas_sec_state` | UE NAS Security State | State · NAS | 코드 | 바뀔 때 |
| `rrc_msg_id` | RRC Message ID | State · RRC | 코드 | RRC 메시지마다 |
| `nas_msg_id` | NAS Message ID | State · NAS | 코드 (5GMM 메시지 타입) | NAS 메시지마다 |

- `labels.ue`: 지금은 **그 RRC 연결의 C-RNTI를 16진수 문자열**(`"0x4601"`)로 쓴다. 연결이 바뀌면 같은 단말도 라벨이 바뀌고, 단말을 계속 추적하려면 `ue_s_tmsi`를 본다. (TODO: 확정 필요)
- `unit`: 코드는 `"code"`, 식별자는 `"id"`.

### 6.2 표준 KPM (Table II, 3GPP TS 28.552) — `src: "kpm"`, `kind: "kpm"`, `labels: {cell}`

1초(보고 주기)마다 **그 구간의 값**을 구간 끝 시각으로 낸다. 단위는 `"count"`.

| 이름 | 종류 | 값 |
|---|---|---|
| `RRC.ConnEstabAtt` / `RRC.ConnEstabSucc` | CC | 구간 동안 RRC 연결 수립 시도 / 성공 수 |
| `RRC.ConnEstabFailCause` | CC | 구간 동안 연결 수립 실패 수 (TODO: 표준은 원인별 세부 카운터, 지금은 합계) |
| `RRC.RelWithoutSuspendConfig` | CC | suspend 없이 해제한 수 |
| `UECNTX.ConnEstabAtt` / `UECNTX.ConnEstabSucc` | CC | UE 컨텍스트 수립 시도 / 성공 수 |
| `RRC.ReEstabAtt` / `RRC.ReEstabSuccWithUeContext` | CC | 재수립 시도 / 성공 수 |
| `RRC.ResumeAtt` / `RRC.ResumeSucc` | CC | 재개 시도 / 성공 수 |
| `RRC.ConnMean` / `RRC.ConnMax` | SI | RRC_CONNECTED UE 수의 구간 평균 / 최대 |
| `RRC.InactiveConnMean` / `RRC.InactiveConnMax` | SI | RRC_INACTIVE UE 수의 구간 평균 / 최대 |

CC = 누적 카운터(구간 증가량), SI = 상태 통계.

### 6.3 코드표 (TODO: eBPF 팀과 같은 코드를 써야 함)

| 지표 | 코드 |
|---|---|
| `ue_rrc_state` | 0 RRC_IDLE, 1 RRC_SETUP_REQUESTED, 2 RRC_CONNECTED, 3 RRC_INACTIVE |
| `ue_nas_state` | 0 DEREGISTERED, 1 REGISTERED_INITIATED, 2 REGISTERED, 3 DEREGISTERED_INITIATED |
| `ue_rrc_sec_state`, `ue_nas_sec_state` | 0 NOT_ACTIVATED, 1 SMC_SENT, 2 ACTIVATED |
| `ue_cipher_alg` | 0 NEA0(암호화 없음), 1 NEA1, 2 NEA2, 3 NEA3 |
| `ue_integrity_alg` | 0 NIA0(무결성 보호 없음), 1 NIA1, 2 NIA2, 3 NIA3 |
| `rrc_msg_id` | 0 RRCSetupRequest, 1 RRCSetup, 2 RRCSetupComplete, 3 SecurityModeCommand, 4 SecurityModeComplete, 5 RRCReconfiguration, 6 RRCReconfigurationComplete, 7 RRCRelease, 8 RRCResumeRequest, 9 RRCResume, 10 RRCResumeComplete, 11 RRCReestablishmentRequest, 12 RRCReestablishment, 13 RRCReestablishmentComplete |
| `nas_msg_id` | TS 24.501 표 9.7.1의 5GMM 메시지 타입 값: 65 RegistrationRequest, 66 RegistrationAccept, 67 RegistrationComplete, 68 RegistrationReject, 76 ServiceRequest, 78 ServiceAccept, 86 AuthenticationRequest, 87 AuthenticationResponse, 89 AuthenticationFailure, 93 SecurityModeCommand, 94 SecurityModeComplete |

기계가 읽는 원본은 [`mock/scenarios.yaml`](../mock/scenarios.yaml)의 `codes`다.

### 6.4 탐지 근거(evidence)의 `metric`

eKPM은 메시지 단위라 룰은 보통 윈도우 안의 집계로 쓴다. 이때 `evidence[].metric`에는 `count(rrc_msg_id=RRCSetupRequest)`, `count(ue_rrc_state=RRC_SETUP_REQUESTED)`처럼 무엇을 셌는지 적는다(가안, 탐지 엔진 담당과 확정).

## 7. InfluxDB 저장 형태 (참고)

collector가 아래처럼 변환한다. 메시지를 보내는 쪽은 신경 쓰지 않아도 된다.

| measurement | time | tags | fields |
|---|---|---|---|
| `metric` | `ts` | src, node, kind, name, cell, ue | value(float), unit |
| `detection` | `ts_detected` | attack_type, severity, ruleset, rule_id, node | event_id, rule_version, ts_first_evidence, latency_ms, cell, ue_list(JSON 문자열), evidence_json(JSON 문자열) |
| `attack_run` | `ts_start` | scenario | run_id, ts_end, params_json |
| `overhead` | `ts` | node, ebpf_on | cpu_pct, mem_mb |

## 8. 직접 검증해 보기

collector를 InfluxDB 없이 띄워 놓고 내 프로그램이 보내게 하면, 거부된 메시지와 사유가 `recordings/rejected.jsonl`에 쌓인다.

```bash
python -m collector.collector --dry-run                       # UDP 127.0.0.1:9999로 받기
python -m collector.collector --dry-run --in file://out.jsonl --once   # 파일 검사
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
