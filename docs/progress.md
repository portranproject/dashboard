# 진행 기록

마일스톤별로 한 일, 직접 정한 것, 확인 결과를 남긴다. 작성 규칙은 `CLAUDE.md` 12절 8항.

| 마일스톤 | 상태 | 완료일 |
|---|---|---|
| M1 저장소 뼈대 · docker-compose · 스키마 | 완료 | 2026-10-19 |
| M2 mock 생성기 | 완료 (PR 대기) | 2026-10-19 |
| M3 collector | 대기 | |
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
| Q7 | 지표가 어느 노드에서 나오는지와 단위. mock은 eKPM 전부 `cu`, `RRU.PrbUsedDl`·`DRB.UEThpDl`은 `du`, `RRC.ConnMean`은 `cu`. 단위는 `req/s`, `ratio`, `%`, `kbps`, `count` | eBPF, FlexRIC(KPM) | M2 D24 |

### 미정 (확정 전까지 TODO로 둠)

| # | 내용 | 현재 처리 |
|---|---|---|
| T1 | 실제 eKPM / KPM 지표 이름 | 형식만 검사 (`^[A-Za-z][A-Za-z0-9_.\-]*$`) |
| T2 | UE ID 형식 (예시는 `0x4601`) | 비어 있지 않은 문자열만 검사 |
| T3 | `ts_first_evidence <= ts_detected`, `ts_start <= ts_end` 검사 위치 | JSON Schema로 표현 불가. M3 collector에서 할지 결정 |
| T4 | 탐지 룰의 `rule_id` 체계, 임계값, severity | mock은 `scenarios.yaml`의 가안 값 (`R-RRC-001`, `R-KPM-RRC-001` 등) |
| T5 | 지표별 평상시 값·공격 시 변화량 | mock은 그럴듯한 가안 값. 테스트베드에서 실측하면 `scenarios.yaml`을 맞춘다 |

### 해결됨

(없음)

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

- [ ] M2 커밋 → `feat/dashboard-M2` push → `dev`로 PR (사용자 확인 대기)
- [ ] 팀 확인 대기 Q5–Q7 공유 (Q1–Q4와 함께)
- [ ] M3 collector: `value` float 변환(D27), `ts_first_evidence <= ts_detected` 검사 위치 결정(T3)
