# 진행 기록

마일스톤별로 한 일, 직접 정한 것, 확인 결과를 남긴다. 작성 규칙은 `CLAUDE.md` 12절 8항.

| 마일스톤 | 상태 | 완료일 |
|---|---|---|
| M1 저장소 뼈대 · docker-compose · 스키마 | 완료 | 2026-10-19 |
| M2 mock 생성기 | 완료 (PR #1 병합, 지표는 M3 브랜치에서 논문 기준으로 보완) | 2026-10-19 |
| M3 collector | 완료 (PR 대기) | 2026-10-19 |
| M4 실시간 관제 대시보드 | 대기 | |
| M5 evaluator + 성능 검증 대시보드 | 대기 | |
| M6 replay | 대기 | |

---

## 열린 항목

### 팀 확인 대기

CLAUDE.md에 없던 부분을 정했거나, 다른 파트의 동작을 가정한 것들이다. 팀원이 반대하면 고친다.

| # | 내용 | 확인 대상 | 관련 |
|---|---|---|---|
| Q1 | 스키마에 없는 필드는 **거부**한다 (필드를 추가하려면 스키마부터 수정) | 전 파트 | M1 결정 D1 |
| Q2 | metric `labels`는 `cell`, `ue`만 허용 | eBPF | D2 |
| Q3 | 시각은 2001년 이후 ns 정수만 허용, `1.0` 같은 실수 표기 거부 | 전 파트 (특히 탐지 엔진 C++) | D3, D4 |
| Q4 | `attack_type`을 3종 열거형으로 고정 (목록 밖 값은 거부) | 탐지 엔진, 공격 도구 | D5 |
| Q5 | `attack_run`을 공격 **시작 시점**에 보낼지 **종료 시점**에 보낼지. mock은 시작 시점(예정 종료 시각 포함)으로 냄 | 공격 도구 | SCHEMA.md 4절, M2 D15 |
| Q6 | 탐지 엔진이 공격이 계속되는 동안 탐지 이벤트를 **반복해서** 내는지, 한 번만 내는지. mock은 full 룰셋이 10초마다 반복 | 탐지 엔진 | M2 D18 |
| Q7 | 지표가 어느 노드에서 나오는지. mock은 eKPM·KPM 모두 `cu` (TeleRAN은 CU에서 F1AP·RRC·NAS를 봄). 표준 KPM을 FlexRIC(E2SM-KPM)로 받을지 eBPF 에이전트가 만들지도 확인 | eBPF, FlexRIC(KPM) | M2 보완 D51 |
| Q9 | eKPM `labels.ue`에 무엇을 넣을지. mock은 그 RRC 연결의 C-RNTI 16진수(`"0x4601"`). 연결이 바뀌면 같은 단말도 라벨이 바뀜 | eBPF | M2 보완 D45 |
| Q10 | Table I 값의 숫자 코드표(RRC/NAS 상태, 보안 상태, 알고리즘, 메시지 ID). NAS 메시지 ID만 TS 24.501 값이고 나머지는 가안. 탐지 엔진도 같은 코드를 써야 함 | eBPF, 탐지 엔진 | M2 보완 D42, SCHEMA.md 6.3 |
| Q11 | `ue` 태그 개수(cardinality). 폭주 공격 땐 가짜 UE 수만큼 라벨이 생긴다. mock은 C-RNTI를 재사용해서 최대 512개. 실제 에이전트가 다른 키를 쓰면 InfluxDB 시리즈가 크게 늘 수 있음 | eBPF | M2 보완 D45 |
| Q8 | 노드 간 시계 동기화(NTP/PTP). eBPF 에이전트·탐지 엔진·공격 도구가 다른 호스트면 시각이 어긋나 탐지 지연·매칭이 틀어진다. collector는 `ts_first_evidence > ts_detected`를 경고로만 남김 | 전 파트 (테스트베드 담당) | M3 D29 |

### 미정 (확정 전까지 TODO로 둠)

| # | 내용 | 현재 처리 |
|---|---|---|
| T1 | 실제 eKPM / KPM 지표 이름 | TeleRAN 논문 기준으로 정함 (KPM은 3GPP 이름 그대로, eKPM은 Table I 항목을 snake_case로 쓴 가안). 스키마는 형식만 검사 |
| T2 | UE ID 형식 (예시는 `0x4601`) | 비어 있지 않은 문자열만 검사 |
| T4 | 탐지 룰의 `rule_id` 체계, 임계값, severity | mock은 `scenarios.yaml`의 가안 값 (`R-RRC-001`, `R-KPM-RRC-001` 등) |
| T5 | 절차 타이밍, UE 수, 공격 강도 | mock은 그럴듯한 가안 값. 테스트베드에서 실측하면 `scenarios.yaml`을 맞춘다 |

### 해결됨

| # | 내용 | 해결 |
|---|---|---|
| T3 | `ts_first_evidence <= ts_detected`, `ts_start <= ts_end` 검사 위치 | M3: collector가 검사하고 **경고만** 남긴 뒤 저장 (D29). SCHEMA.md에도 반영 |

---

## M1 — 저장소 뼈대 · docker-compose · 스키마 (2026-10-19)

### 한 일

| 파일 | 역할 |
|---|---|
| `docker-compose.yml` | InfluxDB `2.7.12` + Grafana `12.4.13`. InfluxDB 초기 설정(org, bucket, 토큰)을 `.env`에서 받음. InfluxDB healthcheck 후 Grafana 기동 |
| `.env.example` | InfluxDB·Grafana 접속 정보, collector 포트·배치 설정 |
| `grafana/provisioning/datasources/influxdb.yml` | InfluxDB datasource 자동 등록 (Flux, uid `portran-influxdb`) |
| `grafana/provisioning/dashboards/dashboards.yml` | `grafana/dashboards/*.json`을 PortRAN 폴더로 자동 로드 |
| `grafana/provisioning/{plugins,alerting}/` | 빈 폴더. 없으면 Grafana가 error 로그를 남김 |
| `schema/messages.schema.json` | 메시지 4종 JSON Schema (기계 검증 기준) |
| `schema/SCHEMA.md` | 팀원용 스키마 설명, 예시, TODO, 변경 이력 |
| `common/schema.py` | 스키마 검증 함수 `validation_errors()`, `is_valid()`. mock·collector·테스트 공용 |
| `common/config.py` | `.env` 로딩, InfluxDB 접속 설정 |
| `tests/test_schema.py` | 스키마 유효성, 문서 예시 통과, 잘못된 메시지 40종 거부 |
| `tests/test_config.py` | `.env` 파싱 |
| `README.md` | 실행 방법, 문제 해결 |
| `requirements.txt`, `pytest.ini`, `.gitignore`, `.gitattributes` | |
| `mock/`, `collector/`, `evaluator/`, `replay/` | 빈 `__init__.py`만 (이후 마일스톤) |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D1 | 모든 메시지 타입에 `additionalProperties: false` | `ts_detect` 같은 오타를 바로 잡기 위해. 거부된 메시지는 collector가 `rejected.jsonl`에 남기므로 유실되지 않음 | 필요 (Q1) |
| D2 | `labels`는 `cell`, `ue`만 허용 | InfluxDB 매핑(CLAUDE.md 6절)의 tag가 이 둘뿐이라 다른 키는 저장 단계에서 소리 없이 사라짐 | 필요 (Q2) |
| D3 | 시각 하한 `1000000000000000000` (2001-09-09 ns) | 초·밀리초·마이크로초로 잘못 보낸 값을 잡기 위해 | 필요 (Q3) |
| D4 | Python 검증기에서 정수 필드의 실수 표기(`1.0`)와 `NaN`/`Infinity` 거부 | JSON Schema 표준은 `1.0`을 정수로 인정 → ns 타임스탬프를 float로 보내면 정밀도가 깨져도 통과됨. NaN은 InfluxDB에 쓸 수 없음. 스키마 파일 자체는 표준 그대로 | 필요 (Q3) |
| D5 | `attack_type`(= `attack_run.scenario`)을 열거형으로 고정 | evaluator 매칭 키라 오타가 나면 평가가 조용히 틀어짐 | 필요 (Q4) |
| D6 | 선택 필드: `labels`, `target.cell`, `target.ue`. 나머지는 필수 (`params`는 빈 객체 `{}` 허용, `unit`은 빈 문자열 허용) | CLAUDE.md가 `labels`만 선택이라고 명시. F1AP 공격처럼 UE가 특정되지 않는 경우를 위해 target 하위는 선택 | 불필요 |
| D7 | `evidence`는 1개 이상, `op`는 `> >= < <= == !=` | 근거 없는 탐지는 대시보드 "근거" 패널에 보여줄 게 없음 | 불필요 |
| D8 | Grafana 쿼리는 Flux | InfluxDB 2.x 기본 언어. InfluxQL은 DBRP 매핑 설정이 추가로 필요 | 불필요 |
| D9 | 이미지 `influxdb:2.7.12`, `grafana/grafana:12.4.13` | Docker Hub에서 확인한 2.7 / 12.4 계열 최신 패치. Grafana 13도 있으나 12.4가 더 오래 검증됨. `grafana/grafana`가 OSS 이미지 | 불필요 |
| D10 | 대시보드 UI 수정 저장 불가 (`allowUiUpdates: false`) | 기준은 커밋된 JSON. UI에서 고친 내용은 JSON으로 내보내 커밋 | 불필요 |
| D11 | InfluxDB retention 무제한 (기본값) | 발표 전까지 평가 데이터를 보존하기 위해 | 불필요 |
| D12 | `common/schema.py` 추가 (CLAUDE.md 4절에 없던 파일) | 검증 코드를 한 곳에 두어 mock·collector·테스트가 같은 규칙을 쓰도록 | 불필요 |
| D13 | 테스트가 SCHEMA.md·CLAUDE.md의 ```` ```json ```` 예시를 직접 읽어 검증 | 문서 예시와 스키마가 어긋나면 테스트가 실패하도록 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 컨테이너 기동 | `docker compose up -d` → `docker compose ps` | 둘 다 Up, influxdb `(healthy)` |
| InfluxDB | `curl localhost:8086/health` | `status: pass`, `v2.7.12` |
| InfluxDB 초기 설정 | 토큰으로 `/api/v2/buckets` 조회 | `portran` bucket 생성됨 |
| Grafana | `curl localhost:3000/api/health` | `database: ok`, `12.4.13` |
| datasource 자동 등록 | `/api/datasources` | uid `portran-influxdb`, Flux, org·bucket `portran` |
| datasource 연결 | `/api/datasources/uid/portran-influxdb/health` | `datasource is working. 3 buckets found` |
| provisioning 로그 | `docker compose logs grafana` | error 없음 (`.gitkeep` 건너뜀 warn 1줄만) |
| 호스트 → InfluxDB | `common.config.influx_settings()`로 `InfluxDBClient.ping()` | `True`, bucket 조회 성공 |
| 테스트 | `pytest` | **46 passed** |

미확인: 브라우저에서 Grafana·InfluxDB UI 로그인은 직접 해보지 않음 (API로만 확인).

### 환경 메모

- **Docker 소켓 권한 오류** (`permission denied ... /var/run/docker.sock`): Docker Desktop WSL integration을 켠 뒤 이미 열린 터미널에는 `docker` 그룹이 적용되지 않음. 이번 세션은 `sg docker -c "..."`로 우회. 터미널 재시작 또는 `wsl --shutdown` 필요 → README "문제 해결"에 기록함
- **venv의 pip가 깨짐**: `/mnt/c`에서 처음 만든 venv의 pip 파일이 일부 누락됨. 삭제 후 재생성하니 정상 → README "문제 해결"에 기록함
- **sudo는 Claude Code의 `!` 명령으로 실행 불가**: 비밀번호 입력 터미널이 없음. 별도 WSL 터미널에서 실행해야 함
- 설치된 Python 패키지: influxdb-client 1.50.0, jsonschema 4.26.0, pytest 9.1.1, PyYAML 6.0.3

### 남은 일

- [x] 첫 커밋 `8209215` → `origin/main` push (2026-10-19)
  - 브랜치 규칙(CLAUDE.md 12절 9항)을 정하기 전이라 M1만 `main`에 바로 올라갔다. 이후 `main`에서 `dev`를 만들었고(GitHub default = `dev`), M2부터는 `feat/dashboard-M<n>` → `dev` PR로 진행한다.
- [x] WSL 재시작 (`wsl --shutdown`) 후 `sg` 없이 `docker` 사용 확인 (2026-10-19). 컨테이너는 `restart: unless-stopped`로 자동 재기동됨
- [ ] 팀 확인 대기 Q1–Q5 공유 (M2에서 Q6·Q7 추가)
- [ ] GitHub에서 `main` 브랜치 보호 규칙 설정 (직접 push 금지, PR 필수) — 저장소 관리자가 설정

---

## M2 — mock 생성기 (2026-10-19, 브랜치 `feat/dashboard-M2`)

### 한 일

| 파일 | 역할 |
|---|---|
| `mock/generator.py` | mock 생성기 CLI. 공격 일정 → 지표·오버헤드(1초 주기) + attack_run + 탐지 이벤트를 시각 순으로 합쳐 검증 후 전송 |
| `mock/scenarios.yaml` | 생성기의 모든 숫자: 지표 기본값·노이즈, 공격 일정, 공격별 지표 변화량, 룰셋별 탐지율·지연·근거, 오탐률, 오버헤드 |
| `common/transport.py` | `udp://`, `file://` 주소 해석, JSON 한 줄 인코딩, 송신(Sink). 수신 쪽은 M3에서 추가 |
| `tests/test_mock_generator.py` | 설정 오류 검출, 10분치 스키마 통과, seed 재현성, 지표 변화, 탐지율·지연, 오탐, 오버헤드 (26건) |
| `tests/test_transport.py` | 인코딩, 주소 해석, 파일·UDP 송신 (14건) |
| `README.md` | "mock 데이터 만들기" 섹션, 디렉터리 표 |
| `CLAUDE.md` | 12절 9항 브랜치 규칙 (M2 시작 전에 추가) |

생성 흐름:
1. 공격 일정: 평상시 30초 → 공격 → 평상시 40~90초 → ... (`mixed`는 유형마다 한 번씩 돈 뒤 순서를 다시 섞음)
2. 지표: 1초마다 기본값 ± 노이즈. 공격 중에는 `effects`대로 평균이 바뀜 (eKPM 크게, KPM 약하게)
3. 탐지: 공격마다 룰셋별 확률로 탐지 → `delay_ms` 후 첫 이벤트. 공격 없는 구간에는 포아송 오탐
4. 오버헤드: 5초마다 cu·du, 60초마다 eBPF on/off 교대

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D14 | `--scenario normal`(공격 없음) 추가 | 오탐 기준선 데이터용. CLAUDE.md에는 `mixed`와 공격 유형만 있음 | 불필요 |
| D15 | `attack_run`은 공격 시작 시각에 낸다 (예정 `ts_end` 포함) | 실시간 대시보드에서 공격 구간이 바로 보이도록. 공격 도구가 어떻게 할지는 미정 | 필요 (Q5) |
| D16 | mock의 `attack_run.params`에 `"generator": "mock"`, `"seed"` 추가 | 데이터 출처 표시(CLAUDE.md 12절 7항). evaluator 리포트가 이걸로 mock 여부를 알 수 있음. `params`는 자유 형식이라 스키마 변경 없음 | 불필요 |
| D17 | 탐지 근거(evidence) 값은 `scenarios.yaml`의 범위에서 뽑는다. 지표 시계열과 직접 연동하지 않음 | 연동하면 mock 안에 탐지 엔진을 만드는 셈. 범위는 공격 중 지표 값과 비슷하게 잡아 화면상 어긋나지 않게 함 | 불필요 |
| D18 | full 룰셋은 공격이 계속되는 동안 10초마다 탐지 이벤트를 다시 냄. kpm_only는 한 번 | 실제 엔진의 반복 알림을 흉내 내고, evaluator의 "run 하나에 여러 detection" 사례가 mock 데이터에도 나오도록 | 필요 (Q6) |
| D19 | 노이즈는 AR(1)(계수 0.6). 공격 시작·종료 때 평균은 즉시 바뀜 | 매초 독립 노이즈보다 그래프가 자연스러움. 공격 시작은 즉시 튀어야 함 | 불필요 |
| D20 | 오탐: 시간당 full 1건, kpm_only 4건 (포아송). 공격 종료 후 10초는 오탐 없음. 근거 값은 임계값을 2~15% 넘긴 값 | "낮은 확률 오탐"(7절). 종료 직후 오탐은 evaluator grace 구간에서 TP로 잡혀 의도와 달라짐 | 불필요 |
| D21 | 오버헤드는 60초마다 eBPF on/off 교대. eKPM 지표 생성과는 독립 | on/off를 섞어 내라는 요구(7절). off일 때 eKPM을 끊으면 핵심 비교 그래프에 구멍이 남 | 불필요 |
| D22 | `--start`(첫 시각 지정), `--speed 0`(기다리지 않음) 추가. `--speed`가 1보다 크면 시각이 실제보다 앞서 나감 | 파일로 10분치를 바로 만들고(M2 완료 조건), 재현성 테스트에 고정 시각이 필요. 앞서 나가는 문제는 README에 적음 | 불필요 |
| D23 | 파일 출력은 덮어쓰기 | 같은 seed로 다시 만들면 같은 파일이 되도록 | 불필요 |
| D24 | 지표 노드·단위 배정 (Q7 내용) | 가안. 실제 수집 위치를 모름 | 필요 (Q7) |
| D25 | 난수열을 용도별(일정, 지표, 오버헤드, 오탐)·공격별(탐지)로 분리 | 지표를 하나 추가하거나 탐지율을 바꿔도 공격 일정·다른 공격의 결과가 바뀌지 않게 | 불필요 |
| D26 | 생성기가 보내기 전에 모든 메시지를 스키마로 검증하고, 실패하면 중단 | mock이 잘못된 메시지를 만드는 건 버그이므로 조용히 넘기지 않음. 10분치 검증 비용 약 1초 | 불필요 |
| D27 | 지표 값은 항상 실수(float)로 냄 | InfluxDB는 같은 필드에 정수·실수가 섞이면 쓰기를 거부함. **M3 collector도 `value`를 float로 변환해야 함** (실제 파트는 정수로 보낼 수 있음) | 불필요 |
| D28 | ID 형식: `run-s<seed>-001`, `det-s<seed>-000001` (탐지 시각 순) | seed가 다른 mock 실행끼리 ID가 겹치지 않게 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 10분치 파일 생성 | `--duration 600 --seed 42 --speed 0 --out file://...` | 6,268건(metric 6,000 / overhead 240 / attack_run 6 / detection 22), 약 1.5초. 전부 스키마 통과 |
| 핵심 데이터 모양 | 위 파일에서 공격 유형별 지표 평균 | 예: RRC 폭주 때 `rrc_setup_req_rate` 0.6 → 199, `RRU.PrbUsedDl` 34.7 → 37.6(+8%). 유형마다 eKPM 하나 이상 크게, KPM은 전부 ±11% 이내 |
| 탐지 지연 | 같은 파일 | full 첫 탐지 0.3~0.5초, kpm_only 4~14초, 오탐 1건 |
| 오버헤드 | 같은 파일 | cu CPU 17.9% → 20.4%, du 35.1% → 37.5% (off → on) |
| UDP·배속 | `--duration 60 --speed 10 --out udp://...`를 소켓으로 수신 | 624건 수신, 약 6.8초(10배속 기대 6초 + 실행 시간) |
| CLAUDE.md 예시 | `--scenario RRC_SIGNALING_STORM --duration 120` (seed 1~3) | 각각 공격 1회 |
| 테스트 | `pytest` | **86 passed** (스키마 45, mock 26, transport 14, config 1) |
| 통계 테스트 안정성 | 탐지율·오탐 테스트를 seed 5개로 바꿔 실행 | 모두 통과 (허용 범위가 아슬아슬하지 않음) |

미확인: collector가 아직 없어서 InfluxDB·Grafana까지 가는 것은 확인 못 함 (M3에서).

### 환경 메모

- 특이 사항 없음.

### 남은 일

- [x] M2 커밋 `7fa57aa` → `feat/dashboard-M2` push → PR #1로 `dev`에 병합
- [ ] 팀 확인 대기 Q5–Q7 공유 (Q1–Q4와 함께)
- [x] M3 collector: `value` float 변환(D27), 시각 순서 검사 위치 결정(T3) → M3에서 처리

---

## M3 — collector (2026-10-19, 브랜치 `feat/dashboard-M3`)

### 한 일

| 파일 | 역할 |
|---|---|
| `collector/collector.py` | collector CLI. 입력마다 스레드가 줄을 읽어 큐에 넣고, 메인 루프가 검증 → raw 녹화 → 배치 쓰기 → 1초 로그. Ctrl+C·SIGTERM 시 남은 것 처리 후 flush |
| `collector/influx_writer.py` | 메시지 → InfluxDB Point 변환(CLAUDE.md 6절), 동기 쓰기, 오류를 재시도 가능/불가로 구분 |
| `common/transport.py` | 수신 추가: `UdpSource`, `FileTailSource`(tail -f, 파일 생성 대기, 잘림·교체 감지), `open_source()` |
| `common/config.py` | `.env`에 없는 키는 `.env.example`로 채움, `env_int()` |
| `.env.example` | `COLLECTOR_MAX_PENDING`, `COLLECTOR_INFLUX_TIMEOUT_MS`, `COLLECTOR_UDP_RCVBUF_BYTES`, `COLLECTOR_FILE_POLL_MS` 추가 |
| `tests/test_collector.py` | 변환 결과(line protocol) 고정, 녹화·거부·경고, 배치 분할, InfluxDB 장애·데이터 오류 처리, 파일 입력 끝까지/중단 시 flush (21건) |
| `tests/test_transport.py` | 파일 따라 읽기(추가·부분 줄·끝부터·나중에 생성·잘림), UDP 수신 (5건 추가) |
| `tests/test_influx_integration.py` | 실제 InfluxDB 임시 bucket에 mock 2분치를 넣고 건수·시각·지연 확인 후 bucket 삭제. InfluxDB가 없으면 건너뜀 |
| `README.md`, `schema/SCHEMA.md` | collector 사용법, 시각 순서 처리 방식, `--dry-run`으로 형식 확인하는 법 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D29 | `ts_first_evidence > ts_detected`, `ts_start > ts_end`는 **거부하지 않고 경고 로그만** 남긴 뒤 저장 | 노드 간 시계 차이로 생길 수 있는데, 거부하면 evaluator에서 FN으로 잡혀 결과가 조용히 틀어짐. 경고는 처음 5건만 자세히, 이후는 건수만 | 필요 (Q8) |
| D30 | `--in`을 여러 번 줄 수 있음 (UDP와 파일 동시 수신) | 실제 파트들이 UDP·파일을 섞어 쓸 수 있음 | 불필요 |
| D31 | 파일 입력은 기본으로 **처음부터** 읽음 (`--from-end`로 끝부터). `--once`면 끝까지 읽고 종료 | collector가 늦게 떠도 데이터를 놓치지 않게. 같은 파일을 다시 넣어도 InfluxDB에는 같은 점이 덮어써질 뿐이라 중복이 생기지 않음 (raw 녹화에는 중복됨) | 불필요 |
| D32 | `--dry-run` 추가 (InfluxDB 없이 검증·녹화만) | 다른 파트가 자기 메시지 형식을 확인하는 용도. SCHEMA.md 8절에 안내 | 불필요 |
| D33 | InfluxDB 장애(연결 실패·5xx·429)면 메시지를 메모리에 최대 `COLLECTOR_MAX_PENDING`(10만)건 들고 flush 주기마다 재시도. 넘으면 오래된 것부터 버림 | 짧은 장애는 손실 없이 넘김. 버린 것도 raw 녹화에는 있어 replay로 복구 가능 | 불필요 |
| D34 | InfluxDB가 데이터 문제(4xx)로 배치를 거부하면 한 건씩 다시 써서, 문제 건만 `rejected.jsonl`에 `InfluxDB 거부: ...` 사유로 남김 | 한 건 때문에 배치 전체를 잃지 않도록 | 불필요 |
| D35 | raw 녹화는 스키마 검증 통과 시점에 함 (InfluxDB 저장 성공 여부와 무관) | InfluxDB가 죽어 있어도 replay 백업이 남도록. 그래서 InfluxDB가 거부한 건도 raw에는 있음 | 불필요 |
| D36 | raw 파일은 collector 실행마다 새로 `raw-<시작시각>.jsonl` (첫 정상 메시지 때 생성). `rejected.jsonl`은 하나에 계속 이어 붙이고 형식은 `{received_at, source, reasons, raw}` | replay는 실행 단위로 고르기 쉽게. 거부 로그는 한 곳에서 보기 쉽게 | 불필요 |
| D37 | UDP 데이터그램에 여러 줄이 붙어 오면 나눠서 처리. UTF-8이 아니거나 `NaN`/`Infinity`가 있으면 거부 | 보내는 쪽 실수에 너그럽게, 단 InfluxDB에 못 쓰는 값은 막음 | 불필요 |
| D38 | `.env`에 없는 키는 `.env.example` 값을 씀. 단 InfluxDB 접속 정보는 `.env`가 있어야 함 | `.env.example`에 설정이 추가될 때마다 팀원 각자 `.env`를 고치지 않아도 되게. 접속 정보까지 예시 값으로 채우면 인증 실패 원인이 헷갈림 | 불필요 |
| D39 | InfluxDB 클라이언트는 동기 쓰기 + 자체 재시도 끔. 배치·재시도는 collector가 직접 | "저장" 건수를 실제 성공 기준으로 세고, Ctrl+C 시 남은 배치를 확실히 쓰기 위해 | 불필요 |
| D40 | 변환 세부: detection의 tag `node`는 `target.node`, `ue_list`는 UE가 없으면 `"[]"`, `cell`은 있을 때만, `latency_ms = (ts_detected - ts_first_evidence) / 1e6`. 숫자 필드 타입 고정(`value`·`cpu_pct`·`mem_mb`·`latency_ms`는 float, `ts_first_evidence`·`ts_end`는 int) | CLAUDE.md 6절에 없는 세부. 타입이 섞이면 InfluxDB가 쓰기를 거부함 | 불필요 |

알려진 제약: InfluxDB는 measurement·tag·시각이 모두 같은 점을 하나로 덮어쓴다. 예를 들어 같은 나노초에 같은 룰(같은 attack_type·severity·ruleset·rule_id·node)로 탐지 이벤트 2개가 오면 하나만 남는다. ns 단위라 실제로는 드물다.

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| **mock → UDP → collector → InfluxDB** | collector 실행 후 `mock.generator --duration 300 --speed 10 --seed 42 --start <5분 전>` (30.7초) | mock 3,135건 전송 → collector 수신 3,135·저장 3,135. InfluxDB 조회: metric 3,000 / overhead 120 / attack_run 3 / detection 12 (전송 건수와 일치) |
| **raw 녹화** | `recordings/raw-20261019-141329.jsonl` | 3,135줄 (정상 메시지 전부) |
| **거부 로그** | 깨진 JSON 1건, 스키마 위반 detection 1건을 UDP로 전송 | `rejected.jsonl`에 2건, 출처(`udp:127.0.0.1:포트`)·사유·원문 기록. raw에는 없음 |
| 1초 로그 | collector 출력 | `수신 104 저장 104 거부 0 \| 누적 ... \| 대기 N` 형식으로 매초 출력 |
| **Ctrl+C flush** | 전송 직후 SIGINT | 대기 중이던 72건까지 쓰고 `종료 — 누적 수신 3,137 저장 3,135 거부 2 \| 못 쓴 것 0`, exit 0 |
| InfluxDB 꺼짐 | `INFLUX_URL=http://localhost:1` | "InfluxDB에 접속할 수 없습니다 ... (docker compose up -d 했는지 확인)", exit 1 |
| 옵션 오류 | `--once`를 UDP와 같이 | "--once는 파일 입력에만 쓸 수 있습니다" |
| 파일 `--once --dry-run` | mock 60초 파일 | 624건 전부 통과 후 자동 종료 |
| 통합 테스트 | 임시 bucket에 mock 2분치 | 타입별 건수 일치, 탐지 시각 ns 일치, `latency_ms` 계산값 일치, bucket 삭제 |
| 테스트 | `pytest` | **114 passed** (스키마 45, mock 26, collector 21, transport 19, config 2, 통합 1) |

미확인: InfluxDB가 **실행 도중** 죽었다가 살아나는 상황은 실제로 해보지 않음 (가짜 writer로 테스트만 함).

### 환경 메모

- UDP 수신 버퍼를 4MB로 요청하면 Linux가 두 배인 8MB를 잡는다(이 WSL에서는 `net.core.rmem_max` 상한에 안 걸림). 다른 환경에서는 상한에 막혀 작아질 수 있어, collector가 시작할 때 실제 크기를 로그로 보여 준다.
- 기본 bucket `portran`에 확인용 mock 데이터(seed 42, 5분치, 2026-10-19 14:08~14:13 KST)가 들어 있다. M4 대시보드 작업에 그대로 쓴다.

### 남은 일

- [ ] M3 커밋 → `feat/dashboard-M3` push → `dev`로 PR (아래 M2 보완과 함께)
- [ ] 팀 확인 대기 Q8(시계 동기화) 공유
- [ ] M4 실시간 관제 대시보드

---

## M2 보완 — mock 지표를 TeleRAN 논문 기준으로 (2026-10-19, 브랜치 `feat/dashboard-M3`)

M3 커밋 전에 사용자 요청으로 mock 지표 체계를 바꿨다. 기준 논문: Wen et al., *Towards Bridging the Telemetry Gap for Security Applications in 6G OpenRANs via eBPF* (TeleRAN). **Table I → eKPM, Table II → 표준 KPM.**

Table I 항목은 숫자 지표가 아니라 UE별 식별자·상태값이라, 세 가지를 사용자에게 물어 정했다.
- Table I 표현: **숫자 코드로 기존 `metric` 메시지에** (스키마 변경 없음)
- 표준 KPM 변화: **공격별로 현실대로** (폭주 때는 KPM도 오름). CLAUDE.md 7절 2항 문구도 고침
- 공격 유형: **3종 유지**, 지표에 나타나는 방식만 다시 설계

### 한 일

| 파일 | 내용 |
|---|---|
| `mock/scenarios.yaml` | 새로 씀: 코드표(`codes`), eKPM 10개, KPM 14개, 절차 9개(정상 6 + 공격 3), 정상 UE 행동, 공격별 주입(inject)·변조(override), 탐지 근거 |
| `mock/generator.py` | 지표 생성부를 "기본값 ± 노이즈"에서 **UE 절차 시뮬레이터**로 교체 (`Simulator`). 공격 일정·탐지·CLI는 유지. 탐지 `target.ue`에 공격에 연루된 UE를 넣음 |
| `tests/test_mock_generator.py` | 새 구조에 맞게 다시 씀 (40건): 논문 표와 일치, 코드표 사용, KPM↔eKPM 개수 일치, 공격별 특성(폭주·비정상 접속·변조), 탐지 대상, C-RNTI 부족 오류 |
| `CLAUDE.md` 7절 | 동작 1·2항과 지표 목록을 논문 기준으로 |
| `schema/SCHEMA.md` 6절 | 지표 이름·논문 항목 대응, `labels.ue` 의미, KPM 설명, 코드표, 탐지 근거 표기 (스키마 파일은 변경 없음) |
| `README.md` | mock 설명과 공격별로 보이는 것 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D41 | 이전 가안 지표 8개(`rrc_setup_req_rate`, `RRU.PrbUsedDl` 등)를 버리고 논문 Table I(10개)·Table II(14개)로 교체 | 사용자 결정 | 불필요 |
| D42 | Table I 값은 숫자 코드로 `metric`에 넣음. 코드표는 `scenarios.yaml`의 `codes`(원본)와 SCHEMA.md 6.3. `nas_msg_id`는 TS 24.501 표 9.7.1 값, 나머지는 가안 | 사용자 결정(스키마 변경 없음). 대시보드는 값 매핑으로 이름을 보여 주면 됨 | 필요 (Q10) |
| D43 | eKPM은 이벤트 단위(값이 바뀔 때, 메시지마다), KPM은 1초 구간 집계를 **구간 끝 시각**으로 냄 | 구간 시작 시각으로 내면 KPM이 eKPM보다 1초 먼저 튀어 보임. M2 D19(AR(1) 노이즈)를 대체 | 불필요 |
| D44 | mock을 UE 절차 시뮬레이터로: 정상 UE 3대가 등록 → 연결 ↔ 해제/일시 중지 → 재개 ... 를 반복하고, 절차는 yaml에 단계 목록으로 선언. eKPM과 KPM을 같은 절차에서 뽑음 | 두 지표가 서로 맞아야 대시보드 비교가 설득력 있음 (예: KPM `RRC.ConnEstabAtt` 합 = eKPM `RRCSetupRequest` 수) | 불필요 |
| D45 | `labels.ue` = 그 RRC 연결의 C-RNTI 16진수. C-RNTI는 512개 풀에서 돌려 씀 → `ue` 태그는 최대 512개 | 스키마 예시(`0x4601`)와 같은 형식. 폭주 때도 InfluxDB 시리즈 수가 묶임 | 필요 (Q9, Q11) |
| D46 | 공격 효과: 폭주 = 가짜 `RRCSetupRequest` 초당 50건, 1초 뒤 타임아웃 실패 / 비정상 접속 = 공격자가 2.5~3.5초마다 새 S-TMSI로 등록 → 인증 실패 → 거절 / 변조 = 연결 중인 UE에 변조된 SMC(NEA0/NIA0 + 위조 C-RNTI) 초당 0.3건 + 재수립 0.05건, 공격 중 모든 SMC를 NEA0/NIA0으로 | "공격별로 현실대로"를 구체화. 논문이 언급한 시그널링 폭주(위조 RRC 연결 요청)·알고리즘 다운그레이드를 반영 | 불필요 |
| D47 | kpm_only 탐지율을 공격별로: 폭주 0.5, 비정상 접속 0.3, 변조 0.15. 폭주 full 지연은 400~800ms | KPM에 보이는 정도에 맞춤. 변조는 CLAUDE.md 예시(30~50%)보다 낮지만 KPM에 거의 안 보이므로. 폭주는 초당 50건이면 0.4초쯤 임계값(20건)을 넘음 (CLAUDE.md의 200~800ms 안) | 불필요 |
| D48 | eKPM 기반 탐지 근거의 `metric`은 `count(rrc_msg_id=RRCSetupRequest)`처럼 집계식으로 적음 | eKPM은 메시지 단위라 룰은 윈도우 집계로 쓰게 됨 | 필요 (T4) |
| D49 | 탐지 `target`: `node`·`cell`은 설정값, `ue`는 탐지 시각까지 그 공격에 연루된 UE 라벨(최대 5개). 오탐은 `ue` 없음 | 대시보드 이벤트 표의 "대상" 열이 의미 있게 | 불필요 |
| D50 | mock의 `attack_run.params` = 실제로 주입한 내용(`inject`, `override`) + `generator`, `seed` | M2 D16 보완. 예전에는 설명용 값(`rate` 등)을 따로 적었는데, 실제 동작과 어긋날 수 있어서 | 불필요 |
| D51 | eKPM·KPM 모두 `node: cu` | TeleRAN은 CU에서 F1AP·RRC·NAS를 봄. M2 D24를 대체 | 필요 (Q7) |
| D52 | 변조로 낮아진 보안 알고리즘은 다음 SMC 전까지 유지됨 (일시 중지 후 재개 때 NEA0을 다시 보고) | 실제 보안 컨텍스트 동작과 같게. 공격이 끝난 뒤에도 피해 UE가 남아 보임 | 불필요 |

알려진 한계: 변조 공격이 시작될 때 연결 중인 정상 UE가 없으면 첫 변조가 늦어진다. 그러면 full 탐지 시각(공격 시작 후 0.2~0.6초)이 실제 변조보다 앞설 수 있다. 탐지 이벤트는 정해진 확률·지연으로 만들고 지표와 직접 연동하지 않기 때문이다(M2 D17).

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 10분치 생성 | `--duration 600 --seed 42 --speed 0 --out file://...` | 23,126건 (eKPM 14,458 / KPM 8,400 / overhead 240 / attack_run 6 / detection 22), 약 4.2초, 전부 스키마 통과 |
| KPM ↔ eKPM 정합성 | 같은 파일 | KPM `RRC.ConnEstabAtt` 합 2,720 = eKPM `RRCSetupRequest` 2,720 |
| 공격별 모양 (초당) | 같은 파일, 공격 구간 vs 평상시 | 폭주: KPM 연결 시도 49, 실패 47 / eKPM `RRCSetupRequest` 50. 비정상 접속: KPM 연결 시도 0.37 / eKPM 인증 실패·등록 거절 0.34. 변조: KPM 연결·해제 카운터 거의 그대로, 재수립 0.1 / eKPM NEA0 전환 0.08, C-RNTI 불일치 0.28 |
| `ue` 라벨 수 | 같은 파일 | 512 (C-RNTI 풀 크기에서 멈춤) |
| 공격 특성 테스트 안정성 | seed 1~5로 30분씩 생성해 세 테스트 실행 | 모두 통과 |
| **mock → UDP → collector → InfluxDB** | collector 실행 후 `--duration 300 --speed 10 --seed 42 --start <5분 전>` | 10,936건 전송, raw 녹화 10,936줄(UDP 손실 없음). InfluxDB: eKPM 6,601 / KPM 4,200 / detection 12 / attack_run 3 / overhead 120 (전송 건수와 일치) |
| 테스트 | `pytest` | **128 passed** (스키마 45, mock 40, collector 21, transport 19, config 2, 통합 1) |

### 환경 메모

- 논문 PDF를 읽으려고 `pypdf`를 임시 폴더(scratchpad)에만 설치했다. 프로젝트 의존성에는 넣지 않았다.
- 기본 bucket `portran`에 확인용 mock 데이터가 두 벌 있다: **이전 형식**(2026-10-19 14:08~14:13 KST, `rrc_setup_req_rate` 등)과 **새 형식**(14:34~14:39 KST, seed 42). M4 대시보드는 새 형식을 쓴다. 이전 형식 데이터는 지워도 됨(사용자 확인 후).

### 남은 일

- [ ] M3 + M2 보완 커밋 → `feat/dashboard-M3` push → `dev`로 PR
- [ ] 팀 확인 대기 Q7, Q9~Q11 공유 (특히 Q10 코드표는 eBPF·탐지 엔진 담당과 맞춰야 함)
- [ ] bucket의 이전 형식 mock 데이터 정리 여부 결정
