# 진행 기록

마일스톤별로 한 일, 직접 정한 것, 확인 결과를 남긴다. 작성 규칙은 `CLAUDE.md` 12절 8항.

| 마일스톤 | 상태 | 완료일 |
|---|---|---|
| M1 저장소 뼈대 · docker-compose · 스키마 | 완료 | 2026-10-19 |
| M2 mock 생성기 | 완료 (PR #1 병합, 지표는 M3 브랜치에서 논문 기준으로 보완) | 2026-10-19 |
| M3 collector | 완료 (PR #2 병합) | 2026-10-19 |
| M4 실시간 관제 대시보드 | 완료 (PR #5 병합) | 2026-10-19 |
| M5 evaluator + 성능 검증 대시보드 | 완료 (PR #6 병합) | 2026-10-19 |
| M6 replay | 완료 (PR #7 병합) | 2026-10-19 |
| M7 AWS 배포 · CI/CD | 완료 (PR #11~#17, 첫 자동 배포 성공) | 2026-10-28 |
| M8 탐지 엔진 연동 1 — 스키마 v0.3 · collector `/ingest` | 완료 (PR #21 병합) | 2026-11-09 |
| M9 탐지 엔진 연동 2 — AWS 앞단 TLS · 연동 시험 | 완료 (PR #22·#24, 배포 #23·#25, 탐지 쪽 전송기 연동 시험 통과) | 2026-11-09 |
| M10 대시보드 재구성 · 옛 메시지 삭제 | 진행 중 (브랜치 `feat/dashboard-M10` — replay·관제 대시보드·정리 끝, 성능 대시보드 남음) | |

---

## 열린 항목

### 팀 확인 대기

CLAUDE.md에 없던 부분을 정했거나, 다른 파트의 동작을 가정한 것들이다. 팀원이 반대하면 고친다.

| # | 내용 | 확인 대상 | 관련 |
|---|---|---|---|
| Q3 | 탐지 엔진 레코드는 27_대로 **ms 정수**(2001~2286년 범위), `overhead`는 2001년 이후 ns 정수. 둘 다 `1.0` 같은 실수 표기 거부 | 탐지 엔진 (ms는 27_ 그대로라 사실상 확인됨), overhead는 R5 협의 때 | D3, D4, M8 D118 |
| Q8 | 노드 간 시계 동기화(NTP/PTP). 분석 엔진이 붙인 데이터 시각과 대시보드의 '지금'을 비교하는 화면(수집 상태, 상태 불명)이 시계에 기댄다. 27_ D6: 실험 노트북·p4 CU 박스는 NTP를 켜 둠 | 전 파트 (테스트베드 담당) | M3 D29 |
| Q16 | AWS에는 대시보드 스택(InfluxDB·Grafana·collector)만 올리고, 탐지 엔진은 테스트베드(p4 CU 박스·실험 노트북)에 둔다. 탐지 엔진 전송기가 HTTPS `/ingest`로 AWS에 보낸다(11/02 합의, 27_ §3) | 탐지 엔진 (합의됨, M9에서 연동 시험) | M7 D85 |
| Q17 | 조직 `portranproject`의 **Deploy keys 정책을 Enabled로 바꿈**(2026-10-26, EC2가 비공개 저장소를 clone하려고). 조직의 모든 저장소에서 배포 키를 만들 수 있게 된다. GitHub는 새 조직에서 기본으로 막고 GitHub App 같은 대안을 권한다. 대안: 서버가 GitHub에 접속하지 않고 S3로 코드를 받는 방식(CD에서 검토). 다시 Disabled로 돌리면 서버의 `git pull`이 멈춤 | 전 파트 (조직 소유자) | M7 D95 |
| Q21 | 대시보드 **데이터 출처 선택**은 AWS(`p4`) / On-Premise(`lab`)로 하되 **우선 AWS만 받는다**(사용자 결정 11/09). On-Premise를 더할 때 필요한 것: ① 연구실 공인 IP·고정 여부(On-Premise → AWS `/ingest`) ② 단계 비교 재생 `X-Env`에 출처 붙이기(`p4-kpm-only`·`lab-kpm-only`). 그 전까지는 묻지 않음 | 탐지 엔진 (On-Premise를 더할 때) | `docs/dashboard-design.md` 1절 |

### 미정 (확정 전까지 TODO로 둠)

| # | 내용 | 현재 처리 |
|---|---|---|
| T6 | 분석 엔진 실측 녹화에서 확인할 것(27_ §8): `session` 실제 형식, `ue_evt` 필드(분석 엔진 팀 답 대기), Table II 나머지(재수립·재개 4종은 `null` 예상), 실제 양(셀·UE 수) | `evidence.raw`는 해석하지 않고 그대로 저장. `session`은 비어 있지 않은 문자열만 검사 |

### 해결됨

| # | 내용 | 해결 |
|---|---|---|
| Q1·Q2·Q4·T5 | 처음 메시지(`metric`·`detection`·`attack_run`)의 모르는 필드 거부·`labels` 제한·`attack_type` 열거형, mock 절차 타이밍 | M10에서 mock·evaluator와 함께 처음 메시지를 지워 해당 없음(D144·D145). 모르는 필드 거부는 `overhead`에만 남음 |
| Q22 | `L3-20`(Blind DoS) 피해자 연결(`ues[].peers`)의 근거가 오지 않음 | 사용자 결정(11/09): 피해자 쪽은 `peers` ID만 '걸린 UE' 표에 보이고 탐지 쪽에 요청하지 않음(D146) |
| Q20 | 탐지 쪽에 알릴 것: ① 상시 레코드 중복 키와 모든 키 앞 `X-Env`(27_ §3 '우리 요청', 답 대기) 반영 ② 단독 `ue_evt`·100 ms 원본 `kpm2` 거부 ③ `Content-Length` 없으면 `411` | 2026-11-09 사용자 정리: ① 탐지 쪽에 전달함 ② 탐지 쪽은 `send_ue_evt`를 끈 채 보내지 않기로 해 알릴 필요 없음 ③ 전송기(파이썬)가 늘 길이를 보내 문제없음 (M8 D116·D121) |
| Q19 | 탐지 쪽 상시 경로 샘플 2개(`T10_긴공격_ingest.jsonl`, `SAN08_AN-08_지속공격_CLEAR_ingest.jsonl`)를 받지 못해 `kpm2` 3초 묶음을 27_ 예시 1줄로만 시험함 | 11/09 연동 시험에서 탐지 쪽이 두 파일을 실제 전송기로 `X-Env: sample`로 보내 서버에 저장·녹화됨(`kpm2` 132, `hello` 2, 거부 0 — M9). 로컬 `tests/data/detection/`에는 아직 없음(필요하면 서버 녹화 `recordings/raw-20261109-072830-sample.jsonl`에서 꺼냄) |
| T3 | `ts_first_evidence <= ts_detected`, `ts_start <= ts_end` 검사 위치 | M3: collector가 검사하고 **경고만** 남긴 뒤 저장 (D29). SCHEMA.md에도 반영 |
| Q12 | mock의 신호 폭주를 5G-Spector의 BTS Resource Depletion 방식으로 바꿀지 | 사용자 결정으로 바꿈 (D53~D55, 브랜치 `fix/mock-bts-depletion`) |
| T1 | 실제 eKPM / KPM 지표 이름 | 11/04에 TeleRAN Table I·II의 24개로 고정했다가(D110·D111, 커밋 전), 탐지 쪽 27_ 확정(11/05)으로 바뀜: KPM2 = `kpm2`의 `cc`·`si` 키(Table II 이름 그대로), KPM1 = `ue_evt`(메시지 이름 문자열). SCHEMA.md 4절 (M8) |
| T2 | UE ID 형식 | 27_ §2.3·§5.6: UE 키는 (`cell`, `du_ue_id`, `uid`), S-TMSI `"0x"`+16진 12자리, C-RNTI 10진 정수 (M8) |
| T4 | 탐지 룰 체계·임계값·severity | 27_ §5.3: 룰 13개(`L3-xx`·`AN-xx`), 단계 1~4, severity `medium`·`high`, 임계값은 `alert.params`로 옴 (M8) |
| Q5·Q6·Q14 | `attack_run` 발행 시점, 탐지 반복 여부, UDP 유실 대책 | 정답 기록을 대시보드로 받지 않기로 함(11/04 사용자 결정). 탐지는 `alert` 생애(`raise`·`update`·`clear`·`end`)로 옴. 평가는 전체 파이프라인 뒤 탐지 쪽과 정함(27_ §9) (M8) |
| Q7·Q9·Q10·Q11 | 지표가 나오는 노드, eKPM `labels.ue`, Table I 숫자 코드표, `ue` 태그 수 | 27_로 해결: KPM2는 분석 엔진(eBPF)이 셀마다 100 ms로 세고 전송기가 3초로 묶음. KPM1은 `ue_evt`로 메시지 이름·알고리즘 이름을 문자열로 보냄(코드표 불필요). UE 값은 tag가 아니라 필드(`du_ue_id`·`uid`)로 저장 (M8) |
| Q13·Q15 | UDP 통일, 다른 호스트에서 UDP로 보낼 때의 네트워크 | 탐지 엔진은 HTTPS `POST /ingest`로 보냄(11/02 합의). UDP는 mock·시험용으로만 남음 (M8) |
| Q18 | 지표 이름 24개 고정의 팀 공유 | T1과 같은 이유로 공유할 필요가 없어짐 (M8) |

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

- [x] M3 + M2 보완 커밋 `86fd553` → `feat/dashboard-M3` push → PR #2로 `dev`에 병합
- [ ] 팀 확인 대기 Q7, Q9~Q11 공유 (특히 Q10 코드표는 eBPF·탐지 엔진 담당과 맞춰야 함)
- [x] bucket의 이전 형식 mock 데이터 정리: 사용자 확인 후 14:08:29~14:13:29 구간 3,135건 삭제, 같은 데이터의 로컬 녹화 `recordings/raw-20261019-141329.jsonl`도 삭제 (2026-10-19)

---

## 참고 논문 추가 (2026-10-19, 브랜치 `docs/reference-papers`)

- `reference/`에 두 논문(`TeleRAN.pdf`, `5GSpector.pdf`)을 넣고, 요약과 이 저장소와의 대응 관계를 `reference/README.md`에 정리했다.
- CLAUDE.md 0절: 세션을 시작하면 코드를 보기 전에 두 논문을 먼저 읽는다는 규칙을 추가했다. 4절 디렉터리 구조에도 반영했다.
- `.gitattributes`에 `*.pdf binary`를 추가했다 (줄바꿈 변환·diff 대상에서 제외).
- 5G-Spector를 읽고 보니 mock의 신호 폭주 모양이 논문의 BTS Resource Depletion과 다르다 → Q12 (아래에서 해결).
- 환경 메모: Claude Code의 Read 도구로 PDF를 읽으려면 `poppler-utils`가 필요한데 아직 설치되지 않았다. 이번에는 임시 폴더에 설치한 `pypdf`로 텍스트를 뽑아 읽었다(표·그림은 깨질 수 있음). → 2026-10-20 README 준비물에 추가함.

---

## Q12 해결 — mock 신호 폭주를 5G-Spector 방식으로 (2026-10-19, 브랜치 `fix/mock-bts-depletion`)

`docs/reference-papers` 위에서 만든 브랜치다 (그 PR을 먼저 병합).

### 한 일

| 파일 | 내용 |
|---|---|
| `mock/scenarios.yaml` | `fake_setup`(RRCSetup 뒤 1초 타임아웃 실패)을 `bts_fake_connection`으로 교체. 폭주 주입·탐지 근거 변경 |
| `tests/test_mock_generator.py` | 폭주 테스트를 논문 방식으로 다시 씀 (KPM 시도·성공·연결 UE 수 증가, 실패 0, eKPM에서 transient UE 확인). 공격 직후 제외 구간 3초 → 10초 |
| `CLAUDE.md` 7절, `README.md`, `reference/README.md` | 폭주 설명을 BTS Resource Depletion 기준으로 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D53 | 위조 연결 = `RRCSetupRequest` → `RRCSetup` → `RRCSetupComplete`+`RegistrationRequest`(임의 S-TMSI) → `AuthenticationRequest` → (응답 없음) → 4~7초 뒤 `RRCRelease` | 5G-Spector VI절: 공격자는 인증 요청을 받으면 새 연결을 시작하고, 위조 연결은 코어 인증 타이머(LTE T3460, 5G T3560) 만료로 몇 초 뒤 해제. 4~7초는 가안(TODO: 실측) | 불필요 |
| D54 | 위조 연결을 0.15~0.3초 간격으로 하나씩 (초당 약 4~5개, 동시에 20~30개) | 공격자 SDR 하나가 연결을 이어서 만드는 방식. 예전 초당 50개는 단말 하나로는 비현실적 | 불필요 |
| D55 | 폭주 탐지 근거: full = `count(rrc_msg_id=RRCSetupRequest) > 2` + `count(nas_msg_id=AuthenticationRequest, 응답 없음) > 1` (1초 창), kpm_only = `RRC.ConnEstabAtt > 10` + `RRC.ConnMean > 8` (5초 창) | 바뀐 공격 모양에 맞춤. 5G-Spector의 transient UE 카운터 방식은 연결이 해제돼야 세어지므로 공격 시작 후 0.2~0.8초 탐지(CLAUDE.md 7절)와 맞지 않아, 빨리 보이는 신호를 근거로 씀 | 필요 (T4) |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 폭주 모양 | 10분 mixed(seed 42), 공격 구간 vs 평상시 KPM 초당 평균 | 연결 시도 0.05 → 4.4, 성공 0.05 → 4.4, 실패 0 → 0, 해제 0.03 → 3.7, 연결 UE 수 2.0 → 24.2 |
| transient UE | 같은 파일, 인증 요청 후 응답 없이 해제된 연결 | 264개, 수명 7초 이하 |
| 공격 특성 테스트 안정성 | seed 1~5로 30분씩 | 모두 통과 |
| 테스트 | `pytest` | **128 passed** |

미확인: collector·InfluxDB 경로는 메시지 형식이 그대로라 다시 돌리지 않았다. bucket에 있는 새 형식 데이터(14:34~14:39)는 예전 폭주 모양이다. M4에서 데이터를 새로 만든다.

---

## M4 — 실시간 관제 대시보드 (2026-10-19, 브랜치 `feat/dashboard-M4`)

### 한 일

| 파일 | 내용 |
|---|---|
| `grafana/dashboards/realtime.json` | 실시간 관제 대시보드 (uid `portran-realtime`, 새로고침 5초, 기본 최근 15분). 행 4개·패널 10개·annotation 2개·변수 4개 |
| `tests/test_dashboards.py` | 정적 검사(datasource uid, `v.defaultBucket`, 배치 겹침, 변수 정의, annotation 대상, 9.1절 구성, eKPM 코드값 ↔ 코드표, KPM 이름 ↔ mock) + Grafana가 떠 있으면 모든 쿼리 실행 (9건) |
| `README.md` | "대시보드 보기" 섹션, 문제 해결(재시작 후 대시보드가 사라지는 경우) |

패널 구성 (CLAUDE.md 9.1절):

| 행 | 패널 |
|---|---|
| 요약 | 최근 5분 탐지 건수 · 최고 severity(최근 5분) · 수집 상태(소스 5개의 마지막 수신 후 경과) · 접속 UE 수(`RRC.ConnMean`) · 데이터 출처 |
| 핵심 비교 | 표준 KPM(위) / eKPM(아래), 같은 시간축. annotation: 탐지 = 빨간 세로선, 공격 구간 = 주황 영역 |
| 이벤트 | 탐지 이벤트 표(event_id 누르면 근거로 이동) · 공격 유형별 탐지 건수 |
| 근거 | 변수 `event_id`로 고른 이벤트의 evidence 표 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D56 | 쿼리는 Flux, bucket은 `v.defaultBucket` (datasource 설정 = `.env`의 `INFLUX_BUCKET`) | 대시보드 JSON은 환경변수를 못 읽으므로 bucket 이름을 박아 넣지 않음. 테스트로 강제 | 불필요 |
| D57 | 요약 행에 **데이터 출처** 패널 추가 (attack_run의 `params`에 `"generator":"mock"`이 있으면 "mock (성능 결과 아님)") | CLAUDE.md 9.1절에는 없지만 12절 7항(mock 숫자는 성능 결과가 아님) 취지. 발표 화면에서 오해를 막기 위해 | 불필요 |
| D58 | 수집 상태 = 소스별 마지막 수신 후 경과(초). 임계값은 소스마다: KPM 5/15초, 오버헤드 15/60초, eBPF 120/600초. 탐지·공격 기록은 사건이 있을 때만 오므로 색 고정 | 9.1절 "소스별 마지막 수신 시각". eBPF(eKPM)도 UE 절차가 있을 때만 와서 길게 잡음 | 필요 (실제 에이전트의 보고 주기를 알면 조정) |
| D59 | 접속 UE 수 = 표준 KPM `RRC.ConnMean`의 마지막 값 | Table II에 있는 값. 신호 폭주(자원 고갈) 때 크게 오르는 게 보임 | 불필요 |
| D60 | 표준 KPM 패널은 14개 중 6개(`ConnEstabAtt/Succ/FailCause`, `RelWithoutSuspendConfig`, `ReEstabAtt`, `ConnMean`)만. 카운터는 1초 값의 평균 = 초당 건수, `ConnMean`은 오른쪽 축. 데이터가 없는 구간은 선을 끊음 | 14개를 다 그리면 읽을 수 없음. `ConnMean`(최대 30)이 카운터(0~6)를 납작하게 만들어 축 분리. 끊지 않으면 수집 중단이 대각선으로 가려짐 | 불필요 |
| D61 | eKPM 패널은 UE별 값을 4가지 신호의 초당 건수로 집계: `RRCSetupRequest`, `AuthenticationRequest`, 인증 실패·등록 거절, NEA0/NIA0로 바뀜. 코드값은 쿼리에 직접 쓰고 테스트로 코드표와 대조 | eKPM은 메시지 단위라 시계열로 보려면 집계가 필요. C-RNTI 불일치는 Flux로 16진수 라벨을 숫자로 바꿀 수 없어 그리지 않음 | 불필요 |
| D62 | annotation: 탐지는 `ruleset`·`node`·`attack_type` 변수 적용, 공격 구간은 `attack_type`만 적용하고 시간 범위 1시간 전부터 찾음(범위 시작 전에 시작한 공격도 보이게). 둘 다 핵심 비교 두 패널에만 표시 | 9.1절. 다른 패널에 세로선이 깔리면 읽기 어려움 | 불필요 |
| D63 | 근거 표: Flux(`experimental/dynamic`)로 `evidence_json` 배열을 항목마다 한 행(JSON 문자열)으로 나누고, Grafana **Extract fields**로 열(출처·지표·값·연산자·임계값·윈도우)을 펼침 | 9.1절은 Extract fields를 쓰라고 함. Extract fields는 한 셀의 JSON 객체를 열로 펼치므로 배열은 먼저 행으로 나눔. 배열을 그대로 Extract fields에 넣는 방식은 시험하지 않음 | 불필요 |
| D64 | 변수 `event_id` = 시간 범위 안 탐지 이벤트(필터 적용) 최신순 100개, 기본은 가장 최근. 이벤트 표의 event_id에 같은 대시보드로 가는 링크(`var-event_id`)를 붙임 | 근거를 보려고 목록을 뒤지지 않게 | 불필요 |
| D65 | 대시보드 `editable: false`, 시간대는 브라우저 기준 | provisioning의 `allowUiUpdates: false`와 맞춤. 기준은 JSON | 불필요 |
| D66 | 대시보드 JSON은 작업용 스크립트로 조립하고 결과 JSON만 커밋 | 앞으로는 JSON을 직접 고친다(README에 방법). 조립 스크립트까지 두면 기준이 두 개가 됨 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| provisioning | `docker compose up` 상태에서 `/api/dashboards/uid/portran-realtime` | PortRAN 폴더에 등록, provisioned |
| 모든 쿼리 실행 | 패널 10개·annotation 2개·변수 2개의 Flux를 Grafana `/api/ds/query`로 실행 | 오류 없음, 전부 데이터 있음 (예: 탐지 표 32행, 공격 구간 20개, 근거 2행) |
| 화면 (지난 30분) | mock 30분치(seed 7, 공격 17회)를 넣고 Grafana 이미지 렌더러로 대시보드 전체를 PNG로 그림 | 모든 패널 표시. 변조 구간에서 KPM은 평평하고 eKPM의 NEA0/NIA0 전환만 튀는 모습, 신호 폭주 때 KPM 접속 UE 수 2 → 30 |
| annotation | 공격 하나가 있는 3분 구간을 KPM 패널만 확대해 그림 | 공격 구간이 주황 영역(시작·끝 선 포함)으로, 탐지가 빨간 세로선으로 보임 |
| 근거 (Extract fields) | 변수 `event_id=det-s7-000078`(변조) | 출처·지표·값·연산자·임계값·윈도우 열로 2행 (`ue_cipher_alg == 0`, `ue_integrity_alg == 0`) |
| 실시간 | collector + mock 1배속 170초(seed 2, 비정상 접속 1회) 직후 렌더 | 최근 5분 탐지 6, 최고 severity high, 이벤트 변수가 최신(`det-s2-000007`)으로 자동 선택, 근거 표 표시 |
| 데이터 끊김 | 수집이 5분 멈췄던 구간을 그림 | KPM 선이 끊겨 보임 (고치기 전에는 대각선으로 이어졌음) |
| 테스트 | `pytest` | **137 passed** (대시보드 9건 추가). 일부러 오타를 낸 Flux를 쿼리 실행 검사가 잡는 것도 확인 |

미확인: 실제 브라우저에서의 상호작용(event_id 링크 클릭, 변수 바꾸기, 5초 자동 새로고침)은 하지 않았다. 렌더링은 헤드리스 브라우저 이미지로만 확인했다.

### 환경 메모

- **재시작 후 대시보드가 사라짐**: WSL 재시작 뒤 Docker Desktop이 자동으로 다시 띄운 Grafana 컨테이너에서 `/etc/grafana/dashboards`와 `/etc/grafana/provisioning/datasources`가 비어 있었다(Windows 디스크 바인드 마운트가 빈 채로 붙음). `docker compose up -d --force-recreate grafana`로 해결 → README "문제 해결"에 기록.
- **화면 확인 방법**: Grafana 이미지 렌더러(`grafana/grafana-image-renderer:v5.12.5`)를 임시 compose override로 붙여 `/render/d/...` API로 PNG를 받았다. 저장소에는 넣지 않았고 확인 후 내렸다. 설정은 아래와 같다 (`docker compose -f docker-compose.yml -f render.override.yml up -d`, 끝나면 `docker compose up -d --remove-orphans`).
  ```yaml
  services:
    grafana:
      environment:
        GF_RENDERING_SERVER_URL: http://renderer:8081/render
        GF_RENDERING_CALLBACK_URL: http://grafana:3000/
    renderer:
      image: grafana/grafana-image-renderer:v5.12.5
  ```
- bucket `portran`에 있는 mock 데이터: 새 형식 14:34~14:39(seed 42, 이전 폭주 모양), 14:44~15:14(seed 7, 30분), 15:19~15:22(seed 2, 실시간 확인). 모두 오늘(2026-10-19 KST).

### 남은 일

- [x] M4 커밋 `a3c9890` → push → PR #5로 `dev`에 병합
- [ ] 브라우저에서 http://localhost:3000/d/portran-realtime 직접 확인 (event_id 링크, 변수)
- [x] M5 evaluator + 성능 검증 대시보드

---

## M5 — evaluator + 성능 검증 대시보드 (2026-10-19, 브랜치 `feat/dashboard-M5`)

### 한 일

| 파일 | 내용 |
|---|---|
| `evaluator/evaluate.py` | CLI. InfluxDB에서 attack_run·detection을 읽어 매칭(10절) → 시나리오 × 룰셋별 탐지율·precision·오탐·지연 p50/p95 → `eval_result` 저장 + `reports/eval-<날짜시각>.md`·`.csv`. 매칭·계산은 InfluxDB와 분리한 순수 함수 |
| `grafana/dashboards/evaluation.json` | 성능 검증 대시보드 (uid `portran-evaluation`). 변수 `eval_id`로 평가 하나를 고르고, 지연 분포·오버헤드는 그 평가 구간의 원시 데이터로 그림 |
| `tests/test_evaluator.py` | 경계 사례(grace 경계 포함/1ns 초과, ts_start 경계, 다른 attack_type, run 하나에 여러 탐지, 룰셋 분리, 겹치는 run, 구간 시작 전·끝 직전 run), 공격 없던 시간, 백분위수, 리포트, mock 탐지율 정합성, InfluxDB 경유 결과 = 직접 계산 결과 (21건) |
| `tests/test_dashboards.py` | 성능 검증 대시보드 구성(9.2절), 대시보드가 읽는 필드를 evaluator가 쓰는지 (7건 추가) |
| `.env.example` | `EVAL_GRACE_SEC=5`, `EVAL_LOOKBACK_SEC=3600`, `REPORTS_DIR=reports` |
| `.gitignore` | `reports/` |
| `CLAUDE.md` 6절 | `eval_result` 행에 추가한 tag·field 반영 |
| `README.md` | "성능 평가하기", 성능 검증 대시보드 설명 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D67 | 평가 대상: run은 `--from`~`--to` 안에서 **시작한** 것, 탐지는 `ts_detected`가 구간 안인 것 | 10절에 구간 경계 규칙이 없음. 시작 시각 기준이 가장 단순하고 예측 가능 | 불필요 |
| D68 | 매칭에는 구간 시작 전 `EVAL_LOOKBACK_SEC`(1시간) 안에 시작한 run과, 구간 끝 뒤 (run 종료 + grace)까지의 탐지도 씀. 세는 대상은 D67 그대로 | 구간 경계에 걸친 공격 때문에 오탐(앞쪽)·미탐(뒤쪽)이 잘못 세지지 않도록 | 불필요 |
| D69 | 탐지 하나가 여러 run의 [ts_start, ts_end + grace]에 걸치면 모든 run에 매칭 (TP를 각각 줌), precision에서는 한 번만 셈 | 10절 문장 그대로("어떤 run과 … 안에 있으면 그 run에 매칭"). 같은 유형의 공격이 grace 안에 다시 시작할 때만 생김 | 불필요 |
| D70 | 공격 없던 시간 = 평가 구간에서 모든 run의 [ts_start, ts_end] 합집합을 뺀 시간 (grace는 포함하지 않음) | fp_per_hour 분모. 공격 유형과 상관없이 "공격이 없던" 시간 | 불필요 |
| D71 | 계산할 수 없는 값(분모 0: run 없는 탐지율, 탐지 없는 precision, TP 없는 지연)은 `eval_result`에 쓰지 않고 리포트에 "—" | 0으로 쓰면 "탐지율 0%"처럼 틀린 의미가 됨 | 불필요 |
| D72 | 백분위수는 선형 보간(numpy 기본과 같음) | 표본이 적을 때도 값이 나옴 | 불필요 |
| D73 | `eval_result`에 필드 추가: `tp`, `fn`, `detections`, `onset_p50/p95_ms`(공격 시작→탐지), `eval_id`, `window_from/to`, `grace_sec`, tag `data_source` | 10절의 두 번째 지연(`ts_detected - ts_start`)을 저장할 곳이 6절에 없었음. 대시보드가 평가 하나를 골라 그 구간을 보려면 `eval_id`·구간이 필요. CLAUDE.md 6절에 반영 | 불필요 |
| D74 | 데이터 출처: `--source auto`면 평가한 run의 `params.generator == "mock"`으로 mock 판단, 아니면 real. replay는 `--source replay`로 지정 | 12절 7항. replay는 원본이 mock인지 실제인지에 따라 달라 자동 판단하지 않음 | 불필요 |
| D75 | 탐지 시각은 Flux에서 정수 ns로 받음 (`int(v: r._time)`) | influxdb-client의 datetime은 마이크로초까지라 grace 경계 같은 ns 비교가 틀어짐 | 불필요 |
| D76 | 성능 검증 대시보드: 변수 `eval_id`(최신 기본), 지연 히스토그램은 평가 구간의 **모든** 탐지 `latency_ms`, p50/p95 표는 `eval_result`(run별 첫 매칭 탐지). 표에는 9.2절 항목(탐지율·precision·오탐 수)만 두고 오탐/시간은 리포트에 | 히스토그램을 run별 첫 탐지로만 그리려면 저장 구조가 더 필요함. 패널 설명에 차이를 적음. 표 열이 많으면 잘림 | 불필요 |
| D77 | 리포트(`reports/`)는 git에서 제외 | mock으로 자주 만들 결과라 저장소가 지저분해짐. 발표용은 따로 옮겨 커밋 | 불필요 |
| D78 | (M4 수정) 실시간 대시보드의 "접속 UE 수"에 `RRC.ConnMax`(최대, 정수)와 `RRC.ConnMean`(평균)을 **둘 다** 표시 | 사용자 질문: 0.9처럼 소수가 나오는 이유. ConnMean은 1초 평균이라 연결·해제가 섞이면 소수. 요약 숫자로는 정수인 최대가 읽기 쉽고, 평균을 옆에 두면 표준 KPM 값도 그대로 보임. 사용자 결정. M4 D59를 대체 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 평가 | `--from 2026-10-19T14:44:00 --to 2026-10-19T15:15:00` (bucket의 30분 mock, seed 7) | run 17개, 탐지 78건, 데이터 출처 mock 자동 판단. full: 3개 공격 모두 탐지율 100%, 지연 p50 213~266ms / kpm_only: 탐지율 16.7~50%, 지연 p50 4.1~4.3초, 신호 폭주 오탐 1건 |
| 리포트 | 같은 실행 | md(경고 문구, 요약, 시나리오 × 룰셋, run별), csv(행마다 eval_id·출처·구간 포함) |
| `eval_result` 저장 | 같은 실행 | 6건 (시나리오 3 × 룰셋 2) |
| InfluxDB 경유 = 직접 계산 | 통합 테스트: 임시 bucket에 mock 30분 → collector → fetch → evaluate | 메시지로 직접 계산한 결과와 행 단위로 같음 |
| 성능 검증 대시보드 | 모든 쿼리를 Grafana API로 실행 + 이미지 렌더러로 PNG (M4와 같은 임시 방법) | 모든 패널 표시: 데이터 출처 빨간 "mock — 성능 결과 아님", 시나리오 × 룰셋 표(% 색), 탐지율 막대, 지연 히스토그램(full 0.4초 근처, kpm_only 2.5~5초), p50/p95 표, eBPF on/off CPU(cu 18.0 → 20.5%)·메모리 |
| 평가가 없을 때 | `eval_id`에 없는 값 | 오류 없이 "평가 없음" 표시 |
| 테스트 | `pytest` | **165 passed** (evaluator 21, 대시보드 16 포함) |
| 접속 UE 수 (D78) | 쿼리를 Grafana API로 실행 + 패널만 렌더 | 같은 1초에 최대 1 · 평균 0.956처럼 함께 나옴. 패널에 "최대"·"평균" 두 줄과 추이 그래프 |

미확인: 실제 브라우저에서 `eval_id` 변수를 바꾸는 동작은 해 보지 않았다(평가가 하나뿐).

### 환경 메모

- 특이 사항 없음. 화면 확인은 M4와 같은 임시 렌더러를 썼고 끝난 뒤 내렸다.

### 남은 일

- [x] M5 커밋 `291c996` → push → PR #6으로 `dev`에 병합
- [x] 실시간 대시보드의 "접속 UE 수"에 최대·평균을 함께 표시 (D78, 사용자 결정)
- [x] M6 replay

---

## M6 — replay (2026-10-19, 브랜치 `feat/dashboard-M6`)

### 한 일

| 파일 | 내용 |
|---|---|
| `replay/replay.py` | CLI. 녹화 파일을 읽어(잘못된 줄은 건너뜀) 시각 순으로 정렬 → `--retime`으로 모든 시각 필드를 같은 만큼 이동 → `attack_run.params`에 재생 표시 → 배속에 맞춰 UDP·파일로 전송 |
| `common/schema.py` | `TIME_FIELDS`, `message_time()`(메시지 대표 시각), `shift_times()`, `count_key()` — mock·replay 공용 |
| `common/transport.py` | `paced()`: 메시지 시각에 맞춰 배속으로 내보내기 — mock·replay 공용 |
| `mock/generator.py` | `emit_ns`·대기 루프를 위 공용 함수로 교체 (동작 같음) |
| `evaluator/evaluate.py` | 데이터 출처 자동 판단에 replay 추가 (mock 원본이면 mock 유지) |
| `grafana/dashboards/realtime.json` | 데이터 출처 패널: "mock 재생 (성능 결과 아님)", "녹화 재생" 구분 |
| `tests/test_replay.py` | 녹화 읽기(정렬·잘못된 줄), 시각 이동(모든 시각 필드 간격 유지), 재생 표시, CLI(파일·UDP·retime now·오류) (8건) + `paced` 1건, 데이터 출처 판단 보강 |
| `README.md` | "녹화 재생하기 (replay)", collector 준비 전 UDP 손실 주의 |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D79 | 녹화를 메시지 시각 순으로 정렬해 보냄 | 녹화는 도착 순서라 시각이 조금씩 뒤섞일 수 있음 | 불필요 |
| D80 | `--retime`은 `now`(기본) / `none` / ISO 시각. 모든 시각 필드(`ts`, `ts_detected`·`ts_first_evidence`, `ts_start`·`ts_end`)를 같은 만큼 이동 | 11절 "원본 시간 간격 유지". 탐지 지연·공격 길이가 원본과 같아야 함 | 불필요 |
| D81 | 재생한 `attack_run.params`에 `replay: {file, shift_s}`를 넣음. 다른 메시지는 시각만 바뀜 | 12절 7항(데이터 출처 표시). `params`는 자유 형식이라 스키마 변경 없음. 원본 `generator: mock` 표시는 그대로 → mock 재생은 계속 mock으로 판단 | 불필요 |
| D82 | event_id·run_id는 바꾸지 않음 | "원본 그대로" 재생. 같은 녹화를 짧은 간격으로 두 번 재생할 때만 대시보드에 같은 ID가 두 번 보임 (README에 적음) | 불필요 |
| D83 | 읽을 수 없거나 스키마에 맞지 않는 줄은 건너뛰고 수를 알림 (처음 5줄은 사유 로그) | 녹화는 collector가 검증한 것이지만, 손으로 고친 파일 때문에 시연이 멈추지 않도록 | 불필요 |
| D84 | 메시지 시각·배속 전송 코드를 `common/`으로 옮겨 mock과 공유 | 같은 로직이 두 군데 생기는 것을 피함 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| **녹화 재생 → 실시간 대시보드** | collector를 띄워 "녹화" 로그를 확인한 뒤, M4 때 녹화한 파일(seed 2, 168초, 비정상 접속 1회)을 `--speed 1 --retime now`로 재생하고 실시간 대시보드를 렌더 | 재생 2,923건 → collector 수신·저장 2,923 (손실 0). 대시보드에 현재 시각(16:12~16:15)으로 표시: 최근 5분 탐지 6, severity high, 데이터 출처 "mock 재생 (성능 결과 아님)", 공격 구간·탐지 annotation, 이벤트 표·근거 |
| 시각 이동 | 같은 녹화를 파일로 재생해 원본과 비교 | 모든 메시지가 같은 만큼(+3015초) 이동, 탐지 지연(근거→탐지) 유지, `attack_run`에 원본 `generator: mock` + `replay` 표시 |
| evaluator | 재생 구간 평가 | 데이터 출처 mock(원본이 mock), full 탐지 지연 396ms로 원본과 같음 |
| 테스트 | `pytest` | **174 passed** (스키마 45, mock 40, collector 21, evaluator 21, transport 20, 대시보드 16, replay 8, config 2, InfluxDB 통합 1) |

### 환경 메모

- **UDP 손실처럼 보였던 것의 원인**: M4 실시간 확인 때 mock이 보낸 2,939건 중 녹화는 2,923건이었다. 같은 seed로 다시 만들어 비교하니 빠진 16건은 **처음 1초(0초·1초)의 메시지뿐**이었다. 확인 스크립트가 collector를 띄우고 3초만 기다렸는데, collector가 UDP 포트를 열기까지 4.4초가 걸렸다(`/mnt/c`에서 라이브러리 로딩 + InfluxDB 확인). 일정한 UDP 손실은 아니다. README에 "collector 로그에 `녹화 …`가 뜬 뒤 보낸다"를 적었다.

### 남은 일

- [x] M6 커밋 → push (`dev`로 PR은 사용자가 엶)
- [ ] 발표 전: 테스트베드 시연 녹화를 만들어 두고 재생 리허설 (녹화는 git 제외라 따로 백업)

---

## 전체 마일스톤 이후 — 실제 파트 연동 전에 할 일

mock으로 만든 파이프라인(수집 → 저장 → 대시보드 → 평가 → 재생)은 모두 동작한다. 실제 eBPF 에이전트·탐지 엔진·공격 도구를 붙이기 전에 맨 위 "열린 항목"을 팀과 정리해야 한다. 특히:

1. **Q10 코드표 / Q9 `labels.ue` / Q7 노드** — eBPF 팀이 eKPM을 이 형식(SCHEMA.md 6절)으로 낼 수 있는지. 다르면 대시보드 eKPM 패널 쿼리의 코드값을 같이 고친다(테스트가 어긋남을 잡는다).
2. **Q5 attack_run 발행 시점 / Q6 반복 탐지** — 공격 도구·탐지 엔진의 동작에 따라 evaluator 결과(precision 등)가 달라진다.
3. **Q8 시계 동기화** — 노드가 여러 대면 NTP/PTP 필수. 어긋나면 collector 경고 로그로 보인다.
4. 각 파트는 `python -m collector.collector --dry-run`으로 자기 메시지가 스키마를 통과하는지 먼저 확인한다(SCHEMA.md 8절).

---

## 새 PC 환경 구성 확인 (2026-10-20, 브랜치 `docs/readme-poppler`)

새 PC(Ubuntu 26.04 / WSL2, Python 3.14.4)에서 README "처음 실행하기"를 따라 처음부터 구성하면서 확인했다.

### 한 일

- `README.md` 준비물 표에 `poppler-utils`를 추가했다(Claude Code가 `reference/` 논문 PDF를 읽을 때 필요). 이전에는 CLAUDE.md 0절에만 있었다.
- 맨 위 마일스톤 표의 M6 상태를 "PR 대기"에서 "PR #7 병합"으로 고쳤다.

### 확인 결과

- `docker compose ps`: influxdb `(healthy)`, grafana 실행 중. Grafana datasource health `OK` (bucket 3개), PortRAN 폴더에 대시보드 2개
- `pytest`: **174 passed** (Python 3.14.4)
- mock 10분치(seed 42)를 파일로 만들어 `collector --once`로 넣음: 12,836건 저장, 거부 0
- collector UDP 실시간 + mock `--scenario normal --duration 15`: 보낸 294건 = 저장 294건, 거부 0, SIGTERM 종료 시 남은 배치까지 저장
- evaluator 1회: `eval_result` 6건 저장, `reports/eval-*.md/.csv` 생성
- 두 대시보드의 패널 쿼리를 Grafana `/api/ds/query`로 실행: 성능 검증 9/9, 실시간 관제 8/10 패널에 데이터 있음. 빈 2개("최근 5분 탐지 건수", "최고 severity")는 공격이 든 mock 데이터가 5분보다 이전 시각이라 정상
- 브라우저 화면은 직접 보지 않았다(API로만 확인)

### 환경 메모

- **`python3-venv`가 없으면 `python3 -m venv .venv`가 반쯤 만들어진 `.venv`를 남긴다**(`bin/`에 `python`만 있고 `pip`·`activate`가 없음). 패키지를 설치한 뒤 `rm -rf .venv`로 지우고 다시 만든다. README 준비물과 문제 해결에 이미 있는 내용이다.
- Ubuntu 26.04 기본 Python 3.14에서도 의존성 설치와 테스트에 문제가 없었다.

---

## 성능 검증 대시보드 데이터 출처 문구 변경 (2026-10-20, 브랜치 `fix/eval-source-label`)

### 한 일

- `grafana/dashboards/evaluation.json` 데이터 출처 패널: `mock` 값의 표시 문구를 "mock — 성능 결과 아님"에서 **"Mock data"**로 바꿨다(사용자 요청). 빨간 배경은 그대로 두었다.

### 결정 사항

| 결정 | 이유 | 팀 확인 |
|---|---|---|
| 패널 설명(툴팁)의 "mock이면 … 성능 결과가 아니다" 문장은 남김 | CLAUDE.md 12절 7항 취지(mock 숫자는 성능 결과가 아님)는 빨간 배경과 툴팁으로 계속 드러난다 | 불필요 |
| 실시간 관제의 데이터 출처 문구, evaluator 리포트 문구는 그대로 | 요청 범위가 성능 검증 대시보드였다 | 불필요 |

### 확인 결과

- `pytest`: 174 passed (대시보드 16)
- Grafana API로 provisioning 반영 확인: 매핑 문구 `Mock data`

---

## 열린 항목 추가 — UDP 통일 (2026-10-21, 브랜치 `docs/udp-open-items`)

### 한 일

- 팀 방침(통신 방식을 UDP로 통일할 예정)을 전달받아 열린 항목 Q13~Q15를 추가했다. 코드·스키마·CLAUDE.md는 바꾸지 않았다(방침이 확정되면 Q13대로 고친다).

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| UDP 1배속 전송 | collector 실행 후 `python -m mock.generator --scenario mixed --duration 300 --seed 42 --speed 1` | 6,315건 전송 = 수신 = 저장, 거부 0 (UDP 손실 없음, 같은 PC) |
| 녹화 내용 | 같은 seed로 파일 출력(`--speed 0`)한 것과 시각만 맞춰 비교 | 메시지가 완전히 같음 |
| 메시지 크기 (최대) | 위 녹화 | detection 590B, attack_run 421B, metric 174B, overhead 103B → 모두 1,400B 아래. 실제 탐지 엔진이 evidence·대상 UE를 더 많이 넣으면 detection이 커질 수 있음 |

미확인: 다른 호스트에서 보낸 UDP 수신, collector·evaluator의 중복 메시지 처리(Q14).

### 환경 메모

- 발표 백업용 녹화를 새로 만들었다: `recordings/raw-20261021-132738.jsonl` (5분, 세 공격 포함, seed 42). 이전 녹화 `raw-20261019-143902.jsonl`은 신호 폭주를 고치기 전(`af78ab4`)에 만든 것이라 폭주 구간의 연결 UE 수가 오르지 않는다. 그 녹화를 재생하면서 다시 녹화된 `raw-20261021-132149.jsonl`도 내용이 같다. 둘 다 replay에 쓰지 않는다. 녹화는 git에서 제외되므로 따로 백업한다.
- 기본 bucket에 오늘 데이터가 두 벌 있다: 옛 녹화 재생분(13:22~13:27 KST)과 새 mock(13:27~13:32 KST).

---

## M7 — AWS 배포 · CI/CD (2026-10-26~, 브랜치 `feat/dashboard-M7` → `feat/dashboard-M7-aws`)

CLAUDE.md 13절의 M1~M6 밖에서 새로 정한 마일스톤이다. 순서: CI → EC2 수동 배포 → CD.

**완료 조건 확인 (2026-10-28)**
- CI: PR마다 Python 3.10·3.14로 서비스 테스트까지 전체 통과 → PR #11부터 체크 3개(`pytest` 2 + `AWS 배포 구성`)
- AWS: EC2에서 대시보드 접속, mock·replay 데이터 표시 → 수동 배포 후 mock(10/26), replay(10/28) 확인
- CD: `main` 병합 시 자동 배포 후 헬스 체크 통과 → PR #17(`dev` → `main`) 병합으로 Deploy 첫 실행 성공
CI는 `feat/dashboard-M7`(PR #11), 배포 준비는 병합 후 최신 `dev`에서 만든 `feat/dashboard-M7-aws`에서 했다.

### 한 일

| 파일 | 역할 |
|---|---|
| `.github/workflows/ci.yml` | `dev`·`main` 대상 PR, `dev` push, 수동 실행 때 Python 3.10·3.14로 `pytest` 전체. InfluxDB·Grafana는 저장소의 `docker-compose.yml`로 띄움(`.env`는 `.env.example` 복사). 실패하면 컨테이너 로그 출력 |
| `tests/conftest.py` | `PORTRAN_REQUIRE_SERVICES=1`이면 건너뛴(skip) 테스트를 실패로 바꿈. CI가 켬. 로컬 기본 동작(서비스 없으면 skip)은 그대로 |
| `README.md` | "CI" 섹션, 문제 해결에 WSL에서 `docker`를 못 찾는 경우, 디렉터리 표에 `.github/` |
| `CLAUDE.md` | 13절 마일스톤 표에 M7(범위·완료 조건), 4절 디렉터리 구조에 `.github/workflows/ci.yml` (사용자 확인 받음) |
| `Dockerfile` | AWS 배포용 이미지 하나로 collector·mock·replay·evaluator를 모두 돌림. `python:3.14.8-slim-trixie`, 코드는 root 소유, 실행은 uid 1000 |
| `.dockerignore` | `.env`(접속 정보)를 이미지에 넣지 않음. 녹화·논문·테스트 등 실행에 필요 없는 것 제외 |
| `docker-compose.aws.yml` | AWS용 override. collector 서비스 추가, InfluxDB(8086)·collector(9999/udp)는 `127.0.0.1`에만 열기(`!override`), `tools` 서비스(profile)로 mock·replay·evaluator 실행 |
| `.github/workflows/ci.yml` | `aws-compose` 작업 추가: 서버와 같은 방식(`.env`의 `COMPOSE_FILE`)으로 띄워 포트 잠금과 mock → collector → InfluxDB 저장 확인 |
| `docs/deploy.md` | EC2 배포 절차: 비용 알람, IAM 역할·보안 그룹·인스턴스·탄력적 IP, Session Manager, Docker 설치, 배포 키, `.env`, 기동·확인, 데이터 넣기, 운영, 문제 해결 |
| `README.md`, `CLAUDE.md` | README "AWS 배포" 섹션·디렉터리 표, CLAUDE.md 3절(AWS만 컨테이너)·4절(새 파일) |
| `docs/deploy.md` (배포 후 보완) | 2절: 터미널은 브라우저 안, 내 PC와 서버 프롬프트 구분. 7절: 명령을 따로 나누고 replay는 녹화 복사본을 재생. 8절: 다시 작업하러 들어올 때(인스턴스 시작 → 접속 → 상태 확인), 안 쓸 때 중지("종료"는 누르지 않기) |
| `.github/workflows/deploy.yml` | CD. `main` push·수동 실행 → OIDC 토큰의 `sub` 출력 → AWS 역할 받기(`configure-aws-credentials` v6.3.0, SHA 고정) → SSM 문서 `portran-deploy`로 배포 명령 → 서버 결과를 최대 15분 기다려 출력, 실패면 작업 실패 |
| `deploy/server-deploy.sh` | 서버에서 현재 커밋으로 다시 빌드·기동(`up --build --wait`), 이전 이미지 정리, InfluxDB·Grafana·datasource 헬스 체크(60초 재시도). `.env`의 `COMPOSE_FILE` 줄이 없으면 중단 |
| `deploy/aws/*.json` | 콘솔에 붙여 넣을 원본: SSM 문서(커밋 SHA만 받음), GitHub 배포 역할의 신뢰 정책·권한 정책 |
| `docs/deploy.md` 9절, 8절 | CD 구조, 처음 한 번 설정(OIDC 공급자 → SSM 문서 → IAM 역할 → 저장소 변수), 실패할 때 확인할 것. 8절에 CD 이후 수동 업데이트 명령 |
| `.github/workflows/ci.yml`, `.dockerignore`, README, CLAUDE.md 4절 | ci.yml의 shellcheck 경고(쓰지 않는 반복 변수) 정리, 이미지에서 `deploy/` 제외, README CD 안내, 디렉터리 구조에 `deploy.yml`·`deploy/` |

### 결정 사항

| # | 결정 | 이유 | 팀원 확인 |
|---|---|---|---|
| D85 | AWS에는 대시보드 스택(InfluxDB·Grafana·collector)만 올린다. CU/DU·eBPF 에이전트·탐지 엔진은 테스트베드 LAN에 둔다. AWS 쪽은 원격 확인·mock/replay 데모·보관용 | USRP·eBPF는 물리 호스트에 묶임. 5G-Spector도 탐지를 near-RT RIC(제어 루프 10ms~1s)에 두고 지연 140~280ms를 보고함. 엔진을 인터넷 너머에 두면 탐지 지연에 네트워크 지연·시계 오차(Q8)가 섞이고, TeleRAN이 지적한 평문 텔레메트리와 인증 없는 collector UDP가 인터넷에 노출됨 | 필요 (Q16) |
| D86 | AWS 구성은 EC2 한 대 + docker compose. collector는 compose override 파일(`docker-compose.aws.yml`)로 컨테이너화하고 로컬 실행 방식(CLAUDE.md 3절, 호스트에서 Python 실행)은 그대로 둔다 | compose 한 장짜리 구성이고 InfluxDB가 디스크에 데이터를 쌓음. ECS Fargate는 UDP에 NLB가 필요하고 저장소를 따로 붙여야 해서 발표 일정에 비해 무거움 | 불필요 |
| D87 | CD는 GitHub OIDC → IAM Role → SSM Run Command. `main` push 때만 배포 | 장기 액세스 키와 열린 SSH 포트가 필요 없음. `main` = 배포·발표용(CLAUDE.md 12절 9항). **다음 단계에서 구현** | 불필요 |
| D88 | CI의 InfluxDB·Grafana는 GitHub service 컨테이너 대신 저장소의 `docker-compose.yml`로 띄운다 | 설정값을 워크플로에 다시 적지 않아도 되고, compose·provisioning 자체도 함께 검증됨. CD가 배포할 구성과 같음 | 불필요 |
| D89 | CI에서는 건너뛴 테스트를 실패로 센다 | 서비스가 없으면 skip하는 테스트 4개(InfluxDB 2, Grafana 2)가 CI에서 통과로 묻히지 않게 | 불필요 |
| D90 | Python 3.10, 3.14 두 버전으로 테스트 | 3.10은 CLAUDE.md 최소 버전, 3.14는 팀 PC(Ubuntu 26.04) 기본. 3.10은 2026-10 지원 종료라 최소 버전을 올릴지는 나중에 정함 | 불필요 |
| D91 | 액션은 커밋 SHA로 고정하고, 나온 지 2주가 안 된 릴리스는 쓰지 않는다(`setup-python` v7.1.0 대신 v7.0.0) | 태그가 옮겨지거나 탈취돼도 같은 코드가 돌도록(공급망). 갓 나온 릴리스는 문제가 생겨 회수되기도 함 | 불필요 |
| D92 | PR은 새 커밋이 오면 이전 CI 실행을 취소하고, `dev` push는 끝까지 돌린다 | 비공개 저장소라 Actions 사용 시간에 한도가 있음. 병합 결과는 매번 확인 | 불필요 |
| D93 | AWS 접근: Grafana(TCP 3000)만 보안 그룹에서 **내 IP**로 열고, InfluxDB·collector UDP는 컨테이너 포트도 `127.0.0.1`에만 연다. AWS 데이터는 서버 안에서 돌리는 mock·replay뿐 | 사용자 결정(본인 IP만, mock·replay는 필요할 때 실행). 보안 그룹을 실수로 넓혀도 InfluxDB·UDP는 노출되지 않게 이중으로 막음 | 불필요 |
| D94 | 서버 접속은 SSM Session Manager. 키 페어 없이 만들고 22번을 열지 않는다. IMDSv2 필수 | 열린 포트와 관리할 키를 줄임. CD(D87)도 같은 SSM 경로를 씀 | 불필요 |
| D95 | 서버는 저장소 전용 **읽기 전용 배포 키**로 clone한다 | 비공개 저장소. 개인 계정 키나 토큰을 서버에 두지 않음. 배포 키가 조직 정책으로 막혀 있어 조직 소유자가 허용함(사용자 결정, A안) | 필요 (Q17) |
| D96 | 서버 `.env`에 `COMPOSE_FILE=docker-compose.yml:docker-compose.aws.yml`을 넣는다 | 서버에서도 `docker compose up -d`처럼 로컬과 같은 명령을 쓰고, `-f`를 빠뜨려 기본 구성(InfluxDB 공개 포트)으로 뜨는 실수를 막음. CI `aws-compose`도 같은 방식 | 불필요 |
| D97 | 이미지 하나(`portran-app:local`)로 collector와 `tools`를 함께 쓴다. 베이스는 `python:3.14.8-slim-trixie` | 같은 코드·의존성. 3.14.9는 나온 지 5일이라 D91 기준으로 하나 전 패치를 씀 | 불필요 |
| D98 | 녹화·리포트는 호스트 폴더에 bind mount하고 주인을 uid 1000으로 맞춘다 | 서버에서 바로 보고 옮길 수 있게. 컨테이너는 root가 아닌 uid 1000으로 돎 | 불필요 |
| D99 | 인스턴스는 t3.small + 스왑 2GiB, gp3 30GiB, 서울 리전 | InfluxDB·Grafana·collector와 이미지 빌드에 충분한 최소 구성 | 불필요 |
| D100 | 수동 배포는 `dev`에서 한다. CD 완성 후 `dev` → `main` PR로 `main`을 따라잡게 하고 그때부터 `main`을 배포 | 현재 `main`은 M1(`8209215`)에 멈춰 있어 `dev`보다 22커밋 뒤 | 불필요 |
| D101 | `tools`에서 `build`·`depends_on: collector`를 빼고 `pull_policy: never`. 이미지는 collector만 빌드 | `dev` push CI(#4)에서 `docker compose run tools`가 collector를 다시 만들었고, 재시작 중에 보낸 mock UDP가 모두 사라짐(저장 0건). 서버에서도 tools를 쓸 때마다 collector가 재시작돼 수신이 끊기고 녹화 파일이 새로 생겼을 것 | 불필요 |
| D102 | collector에 healthcheck: `/proc/net/udp`에 수신 포트가 열려 있으면 healthy | collector는 InfluxDB 확인 뒤 포트를 열므로 "받을 준비 됨"과 같다. `up --wait`이 여기까지 기다려 CI·CD의 경쟁 상태를 없앰 | 불필요 |
| D103 | 대시보드의 query 변수(실시간 `node`, 성능 검증 `eval_id`)를 `refresh: 2`(새로고침·시간 범위 변경마다)로. 테스트로 고정 | 새 서버에서 데이터가 들어오기 전에 대시보드를 열자 `node` 목록이 비어 "All"이 빈 집합이 됐고, 노드로 거르는 패널 7개가 계속 No data였음(수집 상태 패널만 정상). `refresh: 1`은 대시보드를 열 때만 읽어 5초 자동 새로고침으로는 회복되지 않음. 실제 eBPF 에이전트가 새 노드를 보낼 때도 같은 문제 | 불필요 |
| D104 | 서버가 코드를 받는 방식은 배포 키(A안)를 유지하고, CD도 서버에서 `git fetch`하는 방식으로 만든다. S3로 코드를 보내는 B안은 Q17이 반대되면 그때 바꾼다 | 배포 키는 이 저장소 하나에 읽기 전용이라, 서버가 뚫려도 추가로 잃는 건 이미 서버에 있는 코드뿐. B안은 S3 버킷·권한 2개·코드 묶음 풀기 로직이 더 필요해 발표 일정에 비해 부품이 많음. 바꿀 때도 CD의 "서버에 명령 보내기"는 그대로 두고 코드 받는 한 단계만 바꾸면 됨 | 필요 (Q17) |
| D105 | GitHub 역할에는 `AWS-RunShellScript`(임의 셸 명령) 대신 **배포 전용 SSM 문서 `portran-deploy`** 실행 권한만 준다. 문서 입력은 `^[0-9a-f]{40}$`(커밋 SHA)만 허용 | 역할이나 워크플로가 악용돼도 서버에서 할 수 있는 건 "저장소에 있는 커밋으로 다시 배포"뿐. 입력 형식을 막아 명령을 끼워 넣을 수 없음(로컬에서 `abc; rm -rf /` 거부 확인) | 불필요 |
| D106 | 신뢰 정책의 `sub`는 ID가 들어간 형식 `repo:portranproject@337596278/dashboard@<저장소 ID>:ref:refs/heads/main`, `StringEquals`로 `main`만 | GitHub는 2026-07-15 이후 만든 저장소에 이 형식을 쓴다(조직 생성 2026-10-04). 조직·저장소 이름을 다른 사람이 다시 가져가도 역할을 받을 수 없음. 저장소 ID는 비공개 저장소라 사용자에게 받아 채움. 형식이 다르면 워크플로 첫 단계가 찍은 `sub`로 맞춘다 | 불필요 |
| D107 | 서버 쪽 배포 절차는 저장소의 `deploy/server-deploy.sh`에 두고, SSM 문서는 checkout과 이 스크립트 호출만 한다 | 배포 절차를 코드와 함께 리뷰·버전 관리. 문서(콘솔에서 고쳐야 함)는 거의 바뀌지 않게 | 불필요 |
| D108 | 역할 ARN·리전·인스턴스 ID는 GitHub **Variables**(Secrets 아님)로 | 비밀이 아니고, 로그에 가려지지 않아 디버깅이 쉬움. 코드에 박지 않음(CLAUDE.md 12절 3항) | 불필요 |
| D109 | 배포는 `concurrency: deploy`, 진행 중인 배포를 취소하지 않고 순서대로 | 빌드 중간에 끊으면 서버가 반쯤 바뀐 상태로 남을 수 있음 | 불필요 |

### 확인 결과

| 확인 | 방법 | 결과 |
|---|---|---|
| 기존 동작 유지 | 로컬 `pytest` (Python 3.12.3, Docker 없음) | 170 passed, 4 skipped (추가 전과 같음) |
| Python 3.10 호환 | uv로 3.10.22를 받아 `pytest` | 170 passed, 4 skipped |
| skip → 실패 전환 | `PORTRAN_REQUIRE_SERVICES=1 pytest` (3.12, 3.10) | 둘 다 170 passed, **4 errors**, 종료 코드 1. 사유: "PORTRAN_REQUIRE_SERVICES=1인데 건너뜀 — InfluxDB에 접속할 수 없음" 등 |
| 워크플로 문법 | actionlint 1.7.12 | 오류 없음 |
| 액션 버전 | GitHub API로 릴리스·태그 조회 | checkout v7.0.1(2026-07-20) `3d3c42e`, setup-python v7.0.0(2026-07-20) `5fda3b9` |
| 러너용 Python | `actions/python-versions` manifest | ubuntu-24.04 x64용 3.10.22, 3.14.9 있음 |
| **GitHub Actions 첫 실행** | PR #11 (`5855215`) | `pytest (Python 3.10)`, `pytest (Python 3.14)` 모두 통과, 각각 약 1분. skip을 실패로 세므로 compose 기동과 서비스 테스트 4개를 포함한 174개가 모두 실행·통과한 것 |
| AWS compose 합성 결과 | Docker Compose v5.6.0 단독 실행 파일로 `config` (데몬 없이 동작) | 서비스: influxdb·collector·grafana(+ `tools` profile). 포트: influxdb `127.0.0.1:8086`, collector `127.0.0.1:9999/udp`, grafana `3000`. collector·tools의 `INFLUX_URL`=`http://influxdb:8086`, `INFLUX_TOKEN`은 `.env`에서 들어감. 기본 `docker-compose.yml`만 쓸 때는 기존과 같음(influxdb·grafana) |
| `COMPOSE_FILE` 방식 | `.env`에 `COMPOSE_FILE`을 넣고 `-f` 없이 `config --services` | influxdb·collector·grafana — override까지 적용됨 |
| CI `aws-compose` 작업 | actionlint, 작업 안의 Python 확인 코드를 `compile()` | 오류 없음 |
| 기존 테스트 | 로컬 `pytest` | 170 passed, 4 skipped |
| **CI `aws-compose` 첫 실행** | PR #12 (`c7d7704`) | 체크 3개 모두 통과. 이미지 빌드, `COMPOSE_FILE` 방식 기동, InfluxDB·collector 포트가 `127.0.0.1`인지, mock → collector → InfluxDB 저장까지 확인됨(저장 건수는 로그를 직접 보지 않음) |
| **병합 후 `dev` push CI 실패** | CI #4 (`d96732e`) | pytest 2개는 통과, `AWS 배포 구성` 실패: "InfluxDB에 저장된 metric 0건". 로그상 `run tools` 때 collector가 Recreate → Started 직후 mock 366건이 한꺼번에 전송됨. 같은 코드가 PR에서는 통과했으므로 타이밍에 따라 갈리는 경쟁 상태 → D101·D102로 수정 |
| 수정 확인 (로컬) | healthcheck 명령을 UDP 소켓 열기 전·후로 실행, compose `config` | 닫힘 exit 1 / 열림 exit 0. 합성 결과 tools는 build·depends_on 없음, `pull_policy: never`, collector에만 healthcheck. 실제 동작은 수정 PR의 CI에서 확인 |
| 수정 PR CI | PR #13 (`0f1e88a`) | 체크 3개 통과 → 병합(`4f94f5e`) |
| **EC2 수동 배포** | `docs/deploy.md` 0~6절 (사용자 진행) | Ubuntu 24.04.5, 29G 디스크, 스왑 2.0Gi, Docker 29.9.2, Compose v5.6.1. 저장소 Deploy keys가 조직 정책으로 막혀 있어 A안(조직 소유자가 허용)으로 진행, 배포 키로 clone(사용자 확인). 처음엔 병합 전 코드(collector healthcheck 없음)로 떠서 `git pull` 후 다시 띄움 → influxdb·collector `(healthy)`, InfluxDB health `pass`, Grafana `ok`, datasource `OK`, collector 1초 로그 정상 |
| 브라우저 · mock | `http://<탄력적 IP>:3000` 로그인, mock 10분 실행 | 대시보드 2개 보임. 실시간 관제의 "수집 상태"는 KPM 2초·eKPM 7초 전 수신으로 데이터 유입 확인. **그러나 노드로 거르는 패널은 전부 No data** → 브라우저 새로고침(F5) 후 모두 표시됨(원인 확인) → D103 |
| D103 확인 (로컬) | 새 테스트를 고치기 전 JSON에 돌림, 전체 `pytest` | 고치기 전: `node`, `eval_id`에서 실패 / 고친 뒤 통과. 전체 172 passed, 4 skipped |
| D103 반영 | PR #14 CI 통과 → 병합(`2112066`) → 서버 `git pull` | 컨테이너 재시작 없이 실시간 관제 패널이 F5 없이 모두 표시됨(KPM·eKPM 그래프, 공격 구간·탐지선, 탐지 표, 접속 UE 수) |
| evaluator | 서버에서 `docker compose run --rm tools python -m evaluator.evaluate --from "$(date -d '15 min ago' --iso-8601=seconds)"` | `eval-20261026-075423`: 구간 16:39~16:54 KST, 공격 run 6, grace 5초. 성능 검증 패널 전부 표시, 데이터 출처 "Mock data". 숫자는 mock이라 성능 결과 아님 |
| **replay** (2026-10-28) | collector가 쓰던 `raw-20261026-074049.jsonl`(2MB)을 `mock-seed42.jsonl`로 복사해 `--speed 1 --retime now`로 재생 | 실시간 관제 "데이터 출처"가 **mock 재생 (성능 결과 아님)**, 지금 시각에 공격 구간·탐지선이 새로 그려짐. 성능 검증은 evaluator를 다시 돌리기 전까지 이전 결과("Mock data") 그대로 — 정상 |
| CD 파일 검사 (로컬) | shellcheck 0.11.0 `deploy/server-deploy.sh`, actionlint 1.7.12(shellcheck 포함) 두 워크플로, JSON 파싱, SSM 문서 `allowedPattern`에 값 넣어 보기 | 모두 통과(ci.yml의 쓰지 않는 반복 변수 경고는 고침). 40자리 소문자 SHA만 허용, `abc; rm -rf /`·짧은 SHA·대문자 거부 |
| OIDC 형식·버전 조사 | GitHub 문서·changelog, 공개 API | 조직 `portranproject` ID `337596278`, 생성 2026-10-04 → ID 포함 `sub` 형식 대상. `configure-aws-credentials` v6.3.0(2026-09-15) `e125382` |
| CD PR | PR #16 (`f4c7602`) | CI 체크 3개 통과 → `dev` 병합(`20bb0f3`) |
| **CD 첫 실행** | PR #17(`dev` → `main`, merge commit) 병합 → Actions → Deploy (run `40641895501`, 커밋 `6ac2cf0`) | **Success**, 24초. AWS 역할 받기(신뢰 정책의 ID 포함 `sub` 일치) → SSM 문서 실행 → 이미지 다시 빌드, collector만 Recreate → Healthy, InfluxDB·Grafana는 계속 실행(데이터 유지) → 헬스 체크 3개 통과. 서버는 이제 `6ac2cf0`에 detached HEAD |

미확인:
- 이 PC의 WSL에서 `docker`를 쓸 수 없어서(아래 환경 메모) 서비스 테스트 4개는 로컬에서도 돌리지 못했다.
- Python 3.14 로컬 실행(2026-10-20 다른 PC의 3.14.4에서 174 passed 기록이 있음).
- **실제 EC2 배포**: `docs/deploy.md`대로 사용자가 진행한다(AWS 콘솔 권한 필요).

### 환경 메모

- **이 PC의 WSL(Ubuntu 24.04)에서 `The command 'docker' could not be found in this WSL 2 distro`**: Docker Desktop의 Settings → Resources → WSL integration에서 이 배포판을 켜야 한다(Docker Desktop이 꺼져 있어도 같은 메시지). README "문제 해결"에 옮겼다.
- 다른 Python 버전으로 테스트할 때는 `pip install uv` → `uv python install 3.10` → `uv venv -p 3.10`이 가장 빠르다(시스템 Python은 건드리지 않음).
- Docker 없이 compose 파일만 검사하려면 [docker/compose 릴리스](https://github.com/docker/compose/releases)의 `docker-compose-linux-x86_64`를 받아 `./docker-compose -f docker-compose.yml -f docker-compose.aws.yml config`를 실행하면 된다(데몬이 필요 없음).
- PR #11은 기록 커밋(`8df98be`)이 push되기 전에 병합돼서 그 커밋이 `dev`에 빠졌다. `feat/dashboard-M7-aws`로 cherry-pick해 가져왔다(`7a03a96`). PR에 커밋을 더 올릴 때는 CI가 끝난 뒤 병합한다.
- **서버 명령을 내 PC의 PowerShell에서 실행하는 실수**: Windows에도 `sudo`가 있어 `sudo -i`가 "unexpected argument '-i'"로 실패한다. 서버 터미널은 Session Manager로 **브라우저 안에** 열린다. `docs/deploy.md` 2절에 프롬프트로 구분하는 법(`PS C:\...>` vs `$`/`root@ip-...#`)을 적었다.
- **문서의 꺾쇠 자리표시를 그대로 입력**: `recordings/<녹화 파일>.jsonl`을 그대로 넣으면 셸이 `<`를 입력 리다이렉션으로 해석한다(`-bash: 방금: No such file or directory`). `docs/deploy.md`는 실제 예시 이름을 쓰고 "바꿔 넣는다"고 적는 방식으로 고쳤다.
- **collector가 쓰고 있는 녹화 파일을 그대로 replay하면** 재생한 메시지가 같은 파일 끝에 다시 녹화된다. 복사본을 만들어 재생한다(`docs/deploy.md` 7절).
- 2026-10-26: 병합이 끝난 브랜치 5개(`docs/udp-open-items`, `feat/dashboard-M7`, `feat/dashboard-M7-aws`, `feat/dashboard-M7-deploy`, `fix/dashboard-variable-refresh`)를 원격·로컬에서 지웠다. `feat/dashboard-M7`의 남은 커밋 `8df98be`는 `git cherry`로 `dev`에 같은 변경(`7a03a96`)이 있음을 확인한 뒤 지웠다.

### 남은 일

- [x] 커밋 `5855215` → `feat/dashboard-M7` push → PR #11에서 CI 첫 실행 통과 (2026-10-26)
- [x] PR #11 병합 (`296dd8c`)
- [x] collector Dockerfile, `docker-compose.aws.yml` (D86), 절차 문서 `docs/deploy.md`
- [x] PR #12 CI 통과 (체크 3개, 2026-10-26)
- [x] PR #12 병합 (`d96732e`)
- [x] collector 재시작 문제 수정(D101·D102) PR #13 → CI 통과 → 병합
- [x] EC2 수동 배포 0~6절 (사용자)
- [x] 대시보드 변수 수정(D103) PR #14 → CI 통과 → 병합 → 서버 `git pull` → 실시간 관제 패널 표시 확인
- [x] 7절 evaluator를 mock이 끝난 구간으로 실행 → 성능 검증 대시보드 확인
- [x] 서버에서 replay → 실시간 관제 "mock 재생" 표시 (2026-10-28). **M7 완료 조건 중 AWS 항목 충족**
- [x] 병합된 브랜치 정리 (원격·로컬 5개)
- [x] CD 워크플로·서버 스크립트·AWS 설정 JSON 작성 (D105~D109)
- [x] 저장소 ID(`1421775186`, 저장소 페이지 소스의 `octolytics-dimension-repository_id`)로 신뢰 정책 채움 (D106)
- [x] 콘솔 설정 (사용자, 2026-10-28, `docs/deploy.md` 9-1~9-4): OIDC 공급자 → SSM 문서 `portran-deploy` → IAM 역할 `portran-github-deploy`(인라인 정책 `portran-deploy-ssm`) → 저장소 변수 3개
- [x] CD PR #16 → CI 통과 → 병합
- [x] `dev` → `main` PR #17 병합 → Deploy 첫 실행 성공 (M7 완료)
- [x] CLAUDE.md 13절 마일스톤 표에 M7, 4절 디렉터리에 `.github/`·`deploy/` 추가 (사용자 확인 받음)

M7 이후로 넘기는 것:
- [ ] 저장소 관리자: `dev`·`main` 브랜치 보호(PR 필수, CI 체크 `pytest (Python 3.10)`·`pytest (Python 3.14)`·`AWS 배포 구성` 통과 필수, M1부터 남은 일). **CD가 `main` push로 서버에 배포하므로 `main` 보호가 특히 중요하다** (D105로 서버 권한은 좁혔지만, `main`에 들어간 코드는 그대로 배포된다)
- [ ] 저장소 관리자: "Automatically delete head branches" 켜기 (남은 원격 브랜치 `docs/m7-deploy-record`, `feat/dashboard-M7-cd`, `docs/m7-complete`는 2026-10-28에 지움)
- [ ] 발표 녹화 파일을 서버로 옮기는 방법 (replay용. 후보: S3 버킷 + 인스턴스 역할에 읽기 권한)
- [ ] 팀 확인: Q16(탐지 엔진 위치), Q17(조직 Deploy keys 정책)

---

## CLAUDE.md 보완 — 배포 규칙 (2026-10-28, 브랜치 `docs/claude-md-deploy-rules`)

### 한 일

| 파일 | 변경 |
|---|---|
| `CLAUDE.md` 2절 | "포함하는 것"에 7번 AWS 배포 · CI/CD 추가 |
| `CLAUDE.md` 12절 9항 | `main` 병합 = 곧바로 EC2 배포, `dev` → `main` PR은 "Create a merge commit"으로 병합(squash·rebase 금지)과 그 이유 |

### 결정 사항

| 결정 | 이유 | 팀 확인 |
|---|---|---|
| `dev` → `main`은 merge commit만 쓴다 | squash·rebase는 `main`에 `dev`와 다른 커밋을 만들어 다음 PR에서 같은 변경이 다시 차이로 보이고 충돌하기 쉬움. M7 첫 배포(PR #17)를 merge commit으로 했고, PR #18(`main` → `dev`)로 이력도 맞춤 | 불필요 (이 저장소 규칙) |

### 확인 결과

- `pytest`: 172 passed, 4 skipped (CLAUDE.md의 JSON 예시를 읽는 스키마 테스트 포함, 서비스 테스트 4개는 로컬 Docker 없음)

---

## 지표 이름 고정 — TeleRAN Table I·II (2026-11-04, 브랜치 `docs/schema-teleran-tables`)

> **커밋하지 않고 M8에 합쳤다(2026-11-09, 사용자 결정 D113).** 다음 날 탐지 쪽 27_ 명세가 확정되면서 `metric` 형식 자체를 실제로 보내는 쪽이 없어졌다. 이 절은 기록으로 남긴다. Table I·II 대응은 SCHEMA.md 4절이 대신한다.

사용자 요청: CLAUDE.md 5절 메시지 스키마를 TeleRAN 논문 4쪽 Table I·II로 고정, SCHEMA.md도 함께.

### 한 일

| 파일 | 변경 |
|---|---|
| `CLAUDE.md` 5.1절 | 지표 이름을 Table I(eKPM 10개)·Table II(표준 KPM 14개)로 고정. 두 표를 논문 열(Category·Handler / Type·Handler·Source)과 함께 넣음. 예시를 `rrc_msg_id`로 |
| `CLAUDE.md` 5.2절 | 근거 예시를 `count(rrc_msg_id=RRCSetupRequest)`, `RRC.ConnEstabAtt`로. 근거 `metric` 규칙 한 줄 추가 |
| `CLAUDE.md` 7절, 12절 6항 | 중복 목록을 5.1절 참조로 바꿈. "모르는 것" 예에서 지표 이름을 뺌 |
| `schema/SCHEMA.md` | v0.2. 2·3절 예시와 필드 설명(`name`·`value`·`unit`·`labels`), 6절 "가안" 해제와 확정·가안 구분표, 6.2절을 지표별 14행 + TS 28.552 절 번호로, 6.4절, 변경 이력 |
| `tests/test_collector.py` | SCHEMA.md 예시를 읽는 InfluxDB 변환 테스트 3곳의 기대값을 새 예시에 맞춤 (검사 로직은 그대로) |

`messages.schema.json`, mock, collector, 대시보드 코드는 바꾸지 않았다. mock은 원래 이 24개 이름만 쓴다.

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D110 | 문서 예시(CLAUDE.md·SCHEMA.md)의 지표를 `rrc_setup_req_rate`·`RRU.PrbUsedDl`(목록 밖)에서 `rrc_msg_id`, `count(rrc_msg_id=RRCSetupRequest)`, `RRC.ConnEstabAtt`로 바꿈. 값은 `scenarios.yaml`의 `RRC_SIGNALING_STORM` 근거 범위와 맞춤 | 이름을 고정해 놓고 예시가 목록 밖 이름을 쓰면 보내는 쪽이 예시를 따라 할 수 있음 | 불필요 |
| D111 | eKPM 이름은 기존 snake_case 식별자(`ue_c_rnti` … `nas_msg_id`)를 그대로 확정 | Table I에는 설명 이름("UE Cipher Algorithm")만 있고 식별자가 없음. 논문 그림의 예(Fig. 1 `RRC.CipheringAlgorithm`, Fig. 2b `s_tmsi`)는 표기가 서로 달라 기준으로 삼기 어려움. 이미 mock·대시보드·테스트가 이 이름을 씀 | 필요 (eBPF, Q18) |

### 확인 결과

- 문서 표의 이름 = `mock/scenarios.yaml`의 `ekpm`(10)·`kpm`(14): CLAUDE.md 5.1절, SCHEMA.md 6.1·6.2절 모두 순서까지 일치 (스크립트로 대조)
- SCHEMA.md 2절의 인라인 표준 KPM 예시: 스키마 검증 통과
- `pytest`: 176 passed (CLAUDE.md·SCHEMA.md JSON 예시 검증 테스트, 서비스 테스트 포함)

### 남은 일·TODO

- [ ] JSON Schema에서 목록 밖 이름을 거부할지 결정 (지금은 형식만 검사). 거부하면 `kind`별 이름 목록을 스키마에 넣고, eBPF 팀에 먼저 알린다
- [ ] 팀 공유: Q18 (eBPF, 탐지 엔진)

---

## M8 — 탐지 엔진 연동 1: 스키마 v0.3 · collector `/ingest` (2026-11-09, 브랜치 `feat/dashboard-M8`)

배경: 탐지 쪽이 11/05에 `27_탐지엔진_1-4단계-대시보드-지표_명세서.md`(확정)와 샘플을 보냈다. 대시보드 2차 답변서(11/04, `docs/정리.md`)에 대한 답이고, 10/31의 `17_` 명세를 대신한다. 실제로 오는 레코드가 우리 스키마(`metric`·`detection`·`attack_run`)와 형식부터 달라서(아래 비교), 11/04의 지표 이름 고정(v0.2, 커밋 전)을 따로 커밋하지 않고 이 작업에 합쳤다(사용자 결정).

| 항목 | 이전 (v0.2) | 27_ |
|---|---|---|
| 레코드 | `metric`·`detection`·`attack_run`·`overhead` | 경보 경로 `alert`·`evidence`·`gap` + 상시 경로 `kpm2`(3초 묶음)·`hello`·`f1_evt` |
| KPM2 (Table II) | `metric` 한 줄 = 지표 하나 | `kpm2` 한 줄 = 셀 하나 × 3초, `cc`·`si`·`ext` 안에 원인별 하위 키 |
| KPM1 (Table I) | `metric` `kind: ekpm` 숫자 코드 | `ue_evt` 메시지 하나 = 한 줄, 이름 문자열. 상시로는 안 오고 `evidence.raw`로만 |
| 탐지 | `detection` (룰셋 `full`·`kpm_only`) | `alert` 생애 `raise`→`update`→`clear`/`end`, 룰 13개, 단계 1~4 |
| 정답 | `attack_run` | 없음 (평가는 전체 파이프라인 뒤) |
| 시각 · 모르는 필드 · `null` | ns · 거부 · 없음 | **ms** · 받음 · "모름" |
| 전송 · 중복 | UDP·파일 · 없음 | HTTPS `POST /ingest` + `X-Env` · 환경 + 레코드별 키 |

### 한 일

| 파일 | 변경 |
|---|---|
| `schema/messages.schema.json` | 탐지 엔진 레코드 6종 추가(모르는 필드 허용, `fmt`·`ver` 1, ms 시각, `kpm2`는 `agg_ms` 필수). `evidence.raw`가 KPM1 `ue_evt`면 `$defs.ue_evt`로 타임라인 필드 7개 검사. 옛 3종은 설명에 "mock 전용, 교체 예정". `$defs.evidence`(탐지 근거 항목)를 `$defs.detection_evidence`로 이름만 바꿈 |
| `schema/SCHEMA.md` | v0.3으로 다시 씀: 두 갈래, `/ingest` 요청·응답·중복 키(2절), 레코드별 검사(3절), KPM1 `ue_evt` 형식·메시지별 `f` 표(3.7절), Table I·II ↔ `kpm2` 키·`ue_evt` 필드 대응(4절, v0.2의 24개 이름 고정을 대신함), InfluxDB 저장(5절), 옛 메시지는 6절에 모음 |
| `collector/ingest.py` (새 파일) | `POST /ingest` HTTP 서버(표준 라이브러리), `X-Env` 검사, 중복 키(16바이트 해시), 크기 제한 LRU, `GET /healthz` |
| `collector/collector.py` | `--in http://host:port` 입력, `handle_request()`(저장 후 응답, 503이면 아무것도 반영 안 함), 중복 제거, 환경별 녹화 `raw-<시각>-<환경>.jsonl`, 경보 세션(첫 `evidence`의 `raw.session`) 채우기, `--env`, 로그에 중복 수 |
| `collector/influx_writer.py` | 새 measurement 6종 변환(5절 표), `kpm2` 지표 펴기, 룰별 대표 값 |
| `.env.example` | `COLLECTOR_HTTP_MAX_BYTES`(1 MiB), `COLLECTOR_HTTP_TIMEOUT_MS`(30초), `COLLECTOR_DEDUP_MAX_KEYS`(20만) |
| `tests/test_ingest.py` (새 파일) | 변환·중복 키·`X-Env`·요청 처리(재전송, 틀린 줄, 400, 503 뒤 재시도, InfluxDB 데이터 거부)·세션 채우기·UDP 입력·HTTP 서버(200/400/404/411/413/503, `/healthz`) 47개 |
| `tests/test_schema.py` | SCHEMA.md 예시가 10종 모두 덮는지, 탐지 쪽 샘플 32개 전 줄 통과, 새 레코드 거부 사례 48개(그중 `ue_evt` 10개), 모르는 필드·`null`·목록 밖 메시지 이름 허용 |
| `tests/test_influx_integration.py` | 실제 InfluxDB에 샘플 전체를 `/ingest` 요청처럼 넣어 타입 충돌·덮어쓰기가 없는지(점 수 = 줄 수), 모든 경보에 세션이 붙는지 |
| `tests/data/detection/` · `reference/detection/` | 탐지 쪽 샘플 32개(경보 경로)와 27_ 명세·샘플 분석표를 저장소로 복사. 받은 폴더 `탐지엔진-대시보드샘플/`은 그대로 둠 |
| `CLAUDE.md` | 맨 위에 "답변은 항상 한국어"(사용자 요청). 2절 그림, 4절 구조, 5·6절(두 갈래, 레코드 표, InfluxDB 매핑), 7절 mock 지표 참조, 8절 `/ingest` 약속, 13절에 M8~M10 |
| `README.md` | 그림, collector `--in http://`·`--env`, 녹화 파일, 문제 해결(Grafana 401) |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D112 | 옛 메시지 `metric`·`detection`·`attack_run`은 **단계적으로 지운다** — 이번엔 새 6종만 더하고 M10(대시보드 재구성)에서 지움. `overhead`는 R5 협의 전까지 유지 | 사용자 결정(11/09). 한 번에 지우면 mock·evaluator·replay·대시보드가 함께 깨져 단계마다 테스트를 통과시킬 수 없음 | 불필요 |
| D113 | v0.2(지표 이름 24개 고정)는 커밋하지 않고 v0.3에 합침. 24개는 `metric.name` 대신 `kpm2` 키·`ue_evt` 필드 대응표(SCHEMA.md 4절)로 | 사용자 결정(11/09). `metric` 형식을 보내는 쪽이 없어짐 | 불필요 |
| D114 | 새 레코드는 **모르는 필드를 받는다**. `alert.fmt`, `kpm2`·`hello`·`f1_evt`의 `ver`가 1이 아니면 거부 | 27_ §2.4(필드는 형식 판을 올리지 않고 더함), 답변서 D8·27_ §9 동의 | 불필요(합의됨) |
| D115 | 열거로 묶은 값: `event`·`unit`·`kind`·`stage`(1~4)·`phase`. `rule`·`severity`·`mode`는 비어 있지 않은 문자열이면 받음 | 생애·단계는 화면 로직이 기대는 값. 새 룰·심각도는 저장하고 화면이 처리(27_ §7 '모르는 값이 오면 그대로 표시') | 불필요 |
| D116 | `/ingest`의 `kpm2`는 `agg_ms` 필수(묶은 줄만). `ue_evt`·100 ms 원본 `kpm2` 단독 줄은 거부(거부 로그에 남음) | 27_ §4.1 '`/ingest`로 오는 `kpm2`는 모두 묶은 줄', §4.2 `ue_evt`는 상시로 안 보냄 | 알림 (Q20) |
| D117 | `evidence.raw`는 `type`만 검사하고 해석하지 않음 | 27_ §8: `ue_evt` 형식은 분석 엔진 답에 따라 바뀔 수 있음 | 불필요 |
| D118 | ms 시각 범위 10¹²(2001-09-09) ~ 9,999,999,999,999(2286년) | 초·마이크로초·나노초로 잘못 보낸 값을 잡음(옛 ns 하한과 같은 생각) | 불필요 |
| D119 | `/ingest`는 표준 라이브러리 `ThreadingHTTPServer`. 처리 스레드는 요청을 큐에 넣고 기다리고, collector 메인 루프 한 스레드가 처리 | 의존성 추가 없음. 중복 키·녹화·세션 표를 잠금 없이 한 스레드가 만짐 | 불필요 |
| D120 | 요청 처리 순서: 검증·중복 검사 → InfluxDB에 바로 씀 → 성공하면 녹화·중복 키·세션 표 반영 → 응답. 일시 장애면 아무것도 반영하지 않고 `503` | 답변서 D1 "2xx는 저장 뒤". 반영 전에 실패해야 재전송이 처음처럼 저장됨(중복으로 걸러지지 않음) | 불필요 |
| D121 | `Content-Length` 필수(없으면 `411`, chunked 미지원). 상한 검사는 본문을 읽기 전에 | 상한을 넘는 본문을 메모리에 올리지 않으려고. 전송기(파이썬)는 늘 길이를 보냄 | 알림 (Q20) |
| D122 | `X-Env`는 영숫자로 시작, 영숫자·`._-` 64자 이하. 틀리면 `400` | 녹화 파일 이름에 들어감(`../` 같은 경로 방지) | 불필요 |
| D123 | 중복 키는 메모리 LRU(`COLLECTOR_DEDUP_MAX_KEYS` 20만, 약 30 MB). 재시작하면 비지만 InfluxDB에서 같은 점에 덮어써져 결과는 같음(녹화엔 한 번 더 남을 수 있음) | 재전송은 끊긴 직후에 오므로 최근 키로 충분. 디스크 상태를 두지 않아 단순 | 불필요 |
| D124 | InfluxDB에서 `alert_id`를 **tag**로 둠(CLAUDE.md 6절 원칙의 예외). `evidence`·`f1_evt` 시각은 ms × 10⁶ + `seq` mod 10⁶ | 샘플에서 같은 원본 줄이 두 경보의 근거로 옴(S24 판정 보류 9줄), 같은 ms 줄이 많음 → 이렇게 안 하면 서로 덮어씀. 경보 수만큼 series가 늘지만 경보는 공격마다 하나 | 사용자 확인(11/09) |
| D125 | `kpm2`·근거 `kpm2` 지표는 모두 실수, `null`은 뺌. 룰마다 다른 묶음은 `<이름>_json` 문자열 | 27_ §7.1 타입 충돌 경고. `null`은 그래프에서 '데이터 없음' | 불필요 |
| D126 | `alert`·`gap`의 `session` 필드: 같은 요청의 `evidence`에서 먼저 알아내고, 모르면 나중에 같은 점에 `session`만 덧씀. 표는 메모리(경보 1만 개) | 27_ §7 '첫 `evidence`의 `raw.session`이 경보의 세션'. `raise`가 묶음 끝에 오면 증거는 다음 요청에 옴 | 불필요 |
| D127 | `hello`의 시각 = collector가 받은 시각 | `hello`에 시각 필드가 없음(27_ §4.3) | 불필요 |
| D128 | `alert_id`는 field로 두지 않음 | 같은 이름의 tag·field가 있으면 Flux pivot 때 열이 겹침 | 불필요 |
| D129 | 대표 값 `rep_key`·`rep_value`(실수) — 27_ §5.3 '대표 값(제안)', 판정 보류 경보는 `held_w` | 경보 목록·그래프에서 값 하나로 보이기. 룰마다 이름이 달라도 한 필드라 타입 충돌 없음 | 불필요 |
| D130 | 탐지 엔진 레코드 녹화는 환경별 파일 `raw-<시각>-<환경>.jsonl`. 옛 메시지는 기존 `raw-<시각>.jsonl` | 줄에 환경이 없어서, 나중에 replay가 `X-Env`를 붙여 다시 보내려면 파일로 갈라야 함 | 불필요 |
| D131 | UDP·파일 입력도 새 레코드를 받음(환경은 `--env`, 기본 `unknown`) | 샘플을 넣어 보거나 전송기 없이 시험할 때 | 불필요 |
| D132 | HTTP 입력은 기본으로 켜지 않음(`--in http://…`). AWS 구성(compose·Caddy)은 M9 | 기본 동작·배포 구성을 이번에 바꾸지 않으려고 | 불필요 |
| D133 | 마일스톤 M8(수신·저장) · M9(AWS 앞단·연동 시험) · M10(대시보드 재구성·옛 메시지 삭제)을 CLAUDE.md 13절에 추가 | 11/09 합의한 순서 | 불필요 |
| D134 | `evidence.raw`가 KPM1 `ue_evt`면 타임라인에 쓰는 7개(`type`·`t_ms`·`cell_id`·`du_ue_id`(정수 또는 `null`)·`dir` `UL`/`DL`·`proto` `RRC`/`NAS`/`F1AP`·`msg`)만 검사하고, 나머지·모르는 필드·목록 밖 메시지 이름은 받음. 단독 `ue_evt`는 계속 거부(D116) | 사용자 선택(11/09, 문서 + 최소 검사). 27_ §8은 `ue_evt` 형식이 초안이라 해석하지 말라고 했지만, 화면이 기대는 값이 틀리면 저장 단계에서 잡는 편이 낫다. 샘플 655줄 모두 통과. 분석 엔진이 이 7개를 바꾸면 그 근거 줄만 거부 로그로 감(경보는 저장) | 알림 (분석 엔진 답이 오면 3.7절과 대조) |

### 확인 결과

| 확인 | 결과 |
|---|---|
| `pytest` | **304 passed, 2 failed.** 실패 2개는 `test_dashboards.py`의 Grafana 쿼리 — `HTTP 401 Invalid username or password`. 실행 중인 Grafana의 관리자 비밀번호가 `.env`와 달라서다(코드와 무관, README 문제 해결에 적음). 세션을 시작할 때는 Grafana·InfluxDB에 접속이 안 돼 172 passed, 4 skipped였다 |
| 샘플 스키마 | 탐지 쪽 샘플 32개 1,758줄 모두 통과(그중 KPM1 `ue_evt` 근거 655줄 — 28개 파일, 메시지 24종 — 도 `ue_evt` 최소 검사 통과). 27_ 본문의 예시 중 묶은 `kpm2`·`hello`·`f1_evt`·`alert`·`evidence`·`gap` 통과, 원본 `ue_evt`·100 ms `kpm2`는 의도대로 거부 |
| 실제 InfluxDB (`test_detection_samples_to_influx`) | 샘플 32개 + 예시 3줄 = 1,761줄을 요청 33개로 넣어 모두 `accepted`. measurement별 점 수가 줄 수와 같음(덮어쓴 것 없음), 경보 58개 모두 `session` 필드 있음 |
| CLI | `python -m collector.collector --dry-run --in http://127.0.0.1:8088` + `curl`로 `T10_긴공격` 전송 → `{"accepted": 667, "rejected": 0, "duplicates": 0}`, 다시 보내면 `duplicates: 667`, `X-Env: a b` → `400`, `raw-…-lab.jsonl` 667줄, SIGTERM에 정상 종료 |

확인하지 못한 것: TLS 앞단·AWS(M9), 실제 전송기와의 연동, 3초 묶음 `kpm2`가 든 실제 전송 본문(Q19 — 27_ 예시 1줄로만 시험), Python 3.14(CI에서 확인; 로컬은 3.12).

### 환경 메모

- 이 세션에서는 WSL에 `docker` 명령이 없었다(Docker Desktop WSL integration 꺼짐). 그래도 Docker Desktop의 InfluxDB·Grafana는 `localhost`로 접속돼 통합 테스트가 돌았다. `docker` 명령이 필요하면 README 문제 해결의 integration 항목대로 켠다.
- 백그라운드(`&`)로 띄운 collector는 SIGINT(Ctrl+C)를 무시한다(비대화형 셸의 백그라운드 프로세스 성질). 끌 때는 `kill -TERM <pid>`(collector가 SIGTERM을 받아 flush 후 종료).

### 남은 일·TODO

- [x] 커밋 (`feat/dashboard-M8`, 2026-11-09)
- [x] push·PR (`feat/dashboard-M8` → `dev`, PR #21 병합, 2026-11-09)
- [ ] Q19 상시 경로 샘플 2개 다시 받기 → `tests/data/detection/`에 넣고 통합 테스트에 포함
- [x] Q20 탐지 쪽에 알리기 (2026-11-09 — 해결됨 참고)
- [ ] M9: Caddy(443, TLS 1.2+, 자체 서명 인증서 IP SAN) → collector `127.0.0.1:8088`, 보안 그룹에 p4 CU 박스 `43.202.191.147`, `docker-compose.aws.yml`에 `--in http://…`와 헬스 체크, `.pem` 전달, 탐지 쪽 전송기와 연동 시험
- [ ] M10: 대시보드 — 설계 초안 `docs/dashboard-design.md`(관제·성능, 데이터 출처 선택 AWS / On-Premise — 우선 AWS만), mock·replay를 새 형식으로(replay는 녹화 파일의 환경을 `X-Env`로 붙여 `/ingest`로), 옛 메시지 삭제, evaluator 재검토(평가 방식은 탐지 쪽과 정한 뒤)
- [ ] T6 첫 실측 녹화 뒤 확인 (`session` 형식, `ue_evt` 필드, Table II 나머지)
- [ ] `docs/정리.md`(11/04 답변서, 이미 보냄)와 받은 폴더 `탐지엔진-대시보드샘플/`을 저장소에 남길지 정리

---

## M9 — 탐지 엔진 연동 2: AWS 앞단 TLS · 연동 시험 (2026-11-09, 브랜치 `feat/dashboard-M9`, 완료)

목표: 탐지 쪽 전송기(p4 CU 박스)가 `https://<대시보드 탄력적 IP>/ingest`로 보낸 레코드가 InfluxDB에 저장되게 한다(CLAUDE.md 13절). `feat/dashboard-M8`에서 브랜치를 만들었다가 M8 병합(PR #21) 뒤 `dev` 위로 옮겼다(rebase).

### 한 일

| 파일 | 변경 |
|---|---|
| `deploy/nginx/ingest.conf.template` (새 파일) | 443 TLS(1.2·1.3) → `collector:${COLLECTOR_HTTP_PORT}`로 `/ingest`·`/healthz`만 넘김, 그 밖 404, 본문 `${COLLECTOR_HTTP_MAX_BYTES}` 넘으면 413, 502·504 → 503, `X-Real-IP` |
| `deploy/ingest-cert.sh` (새 파일) | 자체 서명 인증서(SAN = 공인 IP) 생성. 같은 IP면 그대로, 다르면 옛 것을 `old-<시각>/`으로 옮기고 새로. 새로 만들면 PEM 출력 |
| `docker-compose.aws.yml` | `ingest` 서비스(`nginx:1.30.5-alpine`, 443, 인증서·템플릿 마운트). collector에 `--in udp://…`·`--in http://0.0.0.0:8088`, 헬스 체크에 `/healthz` |
| `deploy/server-deploy.sh` | 배포 전에 인증서 확인·생성(공인 IP = `.env` `INGEST_PUBLIC_IP` 또는 EC2 메타데이터), 헬스 체크에 HTTPS `/ingest` 경로 |
| `.env.example` · `.gitignore` | `COLLECTOR_HTTP_PORT`, `INGEST_HTTPS_PORT`·`INGEST_PUBLIC_IP`·`INGEST_CERT_DAYS` · `certs/` 제외 |
| `collector/ingest.py` | 거부 로그 `source`에 앞단이 붙인 `X-Real-IP`(전송기 주소) 기록 |
| `.github/workflows/ci.yml` | `aws-compose` 작업: 인증서(127.0.0.1) 만들고 띄운 뒤 HTTPS 경로 검사 — collector 포트 비공개, `/healthz`, 404, 413, 엄격한 TLS 검증으로 샘플 두 번(667 저장 → 667 중복), InfluxDB `env=ci` 건수, collector를 멈추면 503 |
| `tests/test_deploy.py` (새 파일) | 인증서가 파이썬 엄격 검증 통과·다른 IP 거부·재사용·교체·잘못된 IP 거부, compose·nginx 설정 검사 (11개) |
| `tests/test_ingest.py` | `X-Real-IP` 기록 |
| `docs/deploy.md` | 구성 그림·열린 포트, 10절(보안 그룹, 인증서, 확인, 문제 해결) |
| `CLAUDE.md` · `README.md` | 디렉터리 구조, AWS 배포 설명 |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D135 | 앞단은 Caddy(답변서 D2③에서 제안) 대신 **nginx** | 도메인 없이 IP로 접속하면 SNI가 없는데, nginx는 서버 블록의 인증서 하나를 그대로 쓴다(Caddy는 이름으로 인증서를 고르는 방식이라 따로 설정이 필요). 413·503을 앞단에서 정확히 낼 수 있고 `nginx -t`로 설정을 검사할 수 있다. 전송기 쪽에서 보이는 차이는 없다 | 불필요 |
| D136 | nginx가 낸 502·504는 503으로 바꿔 답함 | 전송기는 503·연결 실패·시간 초과만 다시 보내고 그 밖의 코드는 설정 문제로 보고 멈춘다(27_ §3). 배포로 collector가 잠깐 내려가도 전송이 멈추지 않게 | 불필요 |
| D137 | nginx가 collector 주소를 요청마다 Docker DNS(`127.0.0.11`)로 찾음 | 배포 때 collector 컨테이너가 다시 만들어지면 IP가 바뀔 수 있는데, nginx는 처음 찾은 주소를 계속 쓴다 | 불필요 |
| D138 | 인증서: EC P-256 자체 서명, SAN = 공인 IP, `basicConstraints=critical,CA:TRUE`·`keyUsage=keyCertSign`, 730일(`INGEST_CERT_DAYS`) | 자체 서명 인증서가 곧 전송기의 신뢰 기준(`ca_file`). 파이썬 3.13+의 엄격한 검증(`VERIFY_X509_STRICT`)도 통과하게 함(테스트로 확인) | 불필요 |
| D139 | 배포 스크립트가 인증서를 자동으로 만든다(없거나 IP가 바뀌었을 때만). 공인 IP는 `INGEST_PUBLIC_IP`, 비면 EC2 메타데이터(IMDSv2). 새로 만들면 PEM을 배포 로그에 출력 | 서버에 따로 들어가 만들 필요가 없음. PEM은 공개 정보라 로그에 나와도 됨. 개인 키는 서버 `certs/`에만(600) | 불필요 |
| D140 | collector HTTP 포트(8088)는 호스트에 열지 않고, nginx 컨테이너에는 `.env` 전체가 아니라 필요한 값 2개만 넘김 | 바깥에서 TLS를 건너뛰고 collector로 바로 가는 길을 없앰. nginx에 InfluxDB 토큰 등이 들어가지 않게 | 불필요 |
| D141 | 서버 헬스 체크는 공인 IP 주소로 인증서를 검증하되 `curl --connect-to`로 서버 안(127.0.0.1)에 연결 | 보안 그룹이 443을 p4 CU 박스만 열어 두므로 서버 자신은 공인 IP로 못 들어옴 | 불필요 |
| D142 | `nginx:1.30.5-alpine` | nginx 안정판 1.30 계열(짝수), 2026-09 빌드 — 고정 버전 태그(CLAUDE.md 3절) | 불필요 |

### 확인 결과

| 확인 | 결과 |
|---|---|
| `pytest` | 316 passed, 2 failed (M8과 같은 Grafana 401 — 로컬 환경) |
| 인증서 (`tests/test_deploy.py`) | 파이썬 엄격 검증으로 TLS 연결 성공, 다른 IP의 인증서는 검증 실패, 같은 IP면 그대로·다른 IP면 교체(옛 것 보관), 잘못된 IP 거부 |
| nginx 설정 | 우분투 nginx 1.24 패키지로 템플릿을 채워 `nginx -t` 통과 |
| 로컬 종단 시험 | 그 nginx(127.0.0.1:18443)를 collector(`--dry-run --in http://127.0.0.1:18088`) 앞에 두고 CI와 같은 검사: `/healthz` ok, 그 밖 경로 404, 1.1 MB → 413, 엄격 TLS로 `T10` 샘플 두 번 → `accepted 667` / `duplicates 667`, collector를 멈추면 `/healthz`·`/ingest` 모두 503 |

| CI (PR #22·#24 → `dev`, `dev` → `main`) | 사용자가 병합함. CI 결과(`aws-compose`의 Docker `nginx:1.30.5-alpine`·compose 전체 검사)는 이 세션에서 직접 보지 못했다(`gh` 없음) |
| EC2 배포 (#23 → 재배포 #25) | #23 로그(사용자가 붙여 줌): 인증서 자동 생성(SAN `3.39.170.31`, 메타데이터 IP), `ingest`(nginx)·collector 기동 정상, Grafana 비밀번호 불일치로 `Grafana datasource` 확인만 실패. 서버 `.env`를 맞춘 뒤 #25 배포 — 사용자가 "배포 다 끝났어"로 알림(#25 로그는 보지 못함). `/ingest` 경로는 아래 연동 시험으로 확인 |
| 바깥에서 | 대시보드 PC에서 443은 응답 없음(보안 그룹이 p4 CU 박스만 허용 — 의도대로), Grafana 3000은 정상 |

**탐지 쪽 전송기 연동 시험** (2026-11-09 16:47 KST, p4 CU 박스 `43.202.191.147` → `https://3.39.170.31/ingest`, `X-Env: sample`, 전송기 `ran-detect-sender/1`)

탐지 쪽이 11/05 샘플 34개(경보 경로 32 + 상시 경로 2)를 두 번 보냈다.

| 확인 | 결과 |
|---|---|
| nginx 접속 기록 | `43.202.191.147 "POST /ingest" 200 "ran-detect-sender/1"` — 인증서 검증(전송기 `ca_file`)·보안 그룹·nginx → collector 정상 |
| collector 통계 | 누적 수신 5,182 = 저장 2,591 + **중복 2,591**, 거부 0 — 두 번째 전송이 모두 중복으로 걸러짐 |
| 녹화 | `recordings/raw-20261109-072830-sample.jsonl` 2,591줄, `rejected.jsonl` 없음 |
| InfluxDB (`env=sample`) | `alert` 62 · `evidence` 2,394 · `gap` 1 · `hello` 2 · `kpm2` 132 = **2,591** — 샘플 분석표와 정확히 같음(경보 경로 32개 1,758 + `T10` 상시 693 + `SAN08` 상시 140). 점 수 = 줄 수라 덮어쓴 것 없음 |

M9 완료 조건(CLAUDE.md 13절 "탐지 쪽 전송기가 EC2 `https://<IP>/ingest`로 보낸 레코드가 InfluxDB에 저장됨")을 충족했다. 상시 경로(`kpm2` 3초 묶음·`hello`)도 실제 전송기 출력으로 처음 확인됐다(Q19).

아직 하지 않은 것: 분석 엔진과 함께 보내는 실측(`X-Env: p4`) — `session` 실제 형식·`ue_evt` 필드·Table II 나머지(T6)를 여기서 확인한다.

### 남은 일

- [x] 커밋·push → CI `aws-compose` 통과 확인
- [x] M9 PR (`feat/dashboard-M9` → `dev`, PR #22) — M8 병합(PR #21) 뒤 `dev` 위로 옮김
- [x] (사용자, AWS 콘솔) 보안 그룹 인바운드 HTTPS 443, 소스 `43.202.191.147/32`(설명 `jesick`) — 2026-11-09 화면 확인
- [x] (사용자) 대시보드 탄력적 IP = `3.39.170.31` 확인 (탐지 쪽 전송기 기본값과 같음, 2026-11-09)
- [ ] 보안 그룹 점검: 같은 그룹에 소스 `49.1.157.235/32`의 **모든 트래픽** 규칙이 있다(설명 `nagyun-ho`). 문서(1-2절)는 3000만 여는 구성이라, 필요한 포트(3000, 시험용 443)로 줄이는 것을 권함 — 사용자 판단
- [x] `dev` → `main` 병합 = EC2 배포 (PR #23, 2026-11-09). 배포 로그에서 PEM 확인 — SAN `3.39.170.31`, 2028-11-08까지, SHA-256 `AF:5D:C8:69:…:C4:99:A0`
  - 결과는 **Failed**: 인증서 생성·빌드·기동(nginx `ingest`, collector)은 정상이었고, 헬스 체크 `Grafana datasource`가 실패해 스크립트가 거기서 멈춤(`/ingest` 확인은 실행되지 않음). 원인은 Grafana 관리자 비밀번호를 웹에서 바꿔 서버 `.env`와 어긋난 것(사용자 확인). 코드와 무관
  - 고침(`fix/deploy-healthcheck`): 헬스 체크가 하나 실패해도 모두 돌고 끝에서 모아 실패, 실패 줄에 마지막 HTTP 코드. `docs/deploy.md` 문제 해결에 401 경우 추가
- [x] (사용자) 서버 `.env`의 `GRAFANA_ADMIN_PASSWORD`를 바꾼 비밀번호로 맞추고 다시 배포(PR #24 → #25)
- [x] 탐지 쪽에 PEM·주소 전달 → 전송기 연동 시험 → InfluxDB·녹화 확인 → M9 완료 기록 (위 '탐지 쪽 전송기 연동 시험')
- [x] Q20 정리 — ① 전달, ②·③ 알릴 필요 없음 (해결됨으로 옮김)
- [ ] 실측: p4에서 분석 엔진 → 탐지 엔진 → 전송기, `X-Env: p4` (T6 확인)
- [ ] 다음 마일스톤 M10 — 서버 InfluxDB의 `env=sample` 데이터로 대시보드 재구성을 시작할 수 있음(`docs/dashboard-design.md`)

---

## M10 — 대시보드 재구성 · 처음 메시지·mock·evaluator 삭제 (2026-11-09~, 브랜치 `feat/dashboard-M10`, 진행 중)

목표(CLAUDE.md 13절): 관제·성능 대시보드를 탐지 엔진 레코드로 다시 만들고, replay를 새 형식으로 바꾸고, mock·evaluator·처음 메시지(`metric`·`detection`·`attack_run`)·옛 대시보드를 지운다. 설계는 `docs/dashboard-design.md`.

### 한 일 (지금까지)

| 파일 | 변경 |
|---|---|
| `replay/replay.py` | 새로 씀: 탐지 엔진 레코드를 `/ingest`로 재생(전송기처럼 500줄·1 MiB 묶음, 413 나눠서·503 다시). `--retime now`(이동량은 `kpm2` 칸 길이의 배수), 재생 표시 `~r<시각>`를 `session`·`alert_id`에 붙임, 파일 순서 + 보내는 시각 단조, 여러 파일 `--gap-sec`, `--env`(기본 `replay`), `--ca`, `file://` 출력 |
| `collector/influx_writer.py` · `collector.py` | `alert_ue` measurement(걸린 UE 한 칸 = 점 하나). 처음 메시지 변환·시각 검사 삭제 |
| `grafana/build.py` · `grafana/rule-names.json` (새 파일) | 대시보드 JSON 생성기(`--check`로 커밋된 JSON과 비교), 룰 ID → 공격 이름 대응표(27_ §5.3) |
| `grafana/dashboards/monitoring.json` (새 파일) | 관제 대시보드: 요약(열린 경보·최고 심각도·수집 상태·세션), 상시 KPM2 2개(경보 구간·gap·칸 일부 없음·세션 주석), 경보 목록·룰별 수, 경보 상세(판정 요약·근거 값·후보 공격·걸린 UE·근거 KPM2 100 ms·근거 KPM1 흐름·메시지) |
| 삭제 | `mock/`, `evaluator/`, `grafana/dashboards/realtime.json`·`evaluation.json`, `tests/test_mock_generator.py`·`test_evaluator.py`, `common/schema.py`의 시각 도우미, `.env.example` `EVAL_*`·`REPORTS_DIR`, `reports/` 폴더 처리(compose·배포 스크립트·CI·`.gitignore`·`.dockerignore`) |
| `schema/messages.schema.json` · `SCHEMA.md` | v0.4: 처음 메시지 3종 삭제, `overhead`만 남김(6절), `alert_ue` 저장 형태(5절) |
| `.github/workflows/ci.yml` | `aws-compose`의 mock 단계 → replay(tools, 샘플 마운트) + UDP `overhead` 단계 |
| `docker-compose.aws.yml` · `Dockerfile` · `deploy/server-deploy.sh` | tools는 replay용(`COLLECTOR_HTTP_HOST=collector`), reports 마운트 삭제 |
| 테스트 | `test_replay.py` 새로 씀(17개), `test_collector.py`를 overhead·샘플 기준으로 다시 씀, `test_ingest.py`(`alert_ue`), `test_dashboards.py`(생성기 `--check`, 룰 이름 대응표가 샘플·27_ 모두 덮음, 모든 쿼리가 `env`로 거름, 관제 구성), `test_schema.py`·`test_influx_integration.py`(처음 메시지 → overhead) |
| 문서 | `CLAUDE.md`(2·4·5·6·7·9·10·11·12·13절), `README.md`(collector·대시보드·개발·시연 데이터), `docs/deploy.md` 7절, `docs/dashboard-design.md`, `reference/README.md`(5G-Spector 공격 ↔ 탐지 엔진 룰 대응) |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D143 | 새 대시보드는 새 파일(`monitoring.json`·`performance.json`), 옛 `realtime`·`evaluation`은 삭제 | 사용자 결정(11/09) | 불필요 |
| D144 | mock 생성기 폐기, 개발·시연 데이터는 탐지 쪽 샘플 + replay | 사용자 결정(11/09). 샘플은 실제 탐지 엔진 코드 출력이라 룰 13개를 흉내 내는 mock을 새로 짤 필요가 없음 | 불필요 |
| D145 | 처음 evaluator 삭제. 평가는 방식이 정해지면 새로 | 사용자 결정(11/09). 정답 기록을 받지 않기로 했고(11/04) 평가는 27_ §9에 따라 파이프라인 완성 뒤 | 탐지 쪽과 평가 방식 협의 (27_ §9) |
| D146 | Blind DoS(`L3-20`) 피해자 연결은 `peers` ID만 표시 | 사용자 결정(11/09). 피해자 근거가 오지 않음(Q22) | 불필요 |
| D147 | replay 출력은 `/ingest`(HTTP)와 파일만, UDP 출력은 없앰 | 탐지 엔진 레코드는 환경(`X-Env`)을 함께 보내야 하고, 중복 키·세션 처리를 실제 전송기와 같게 시험하려고 | 불필요 |
| D148 | `alert_ue` measurement 추가 | `ues_json` 배열은 Flux·Grafana에서 행으로 펴기 어려움. 저장 형식(27_)은 그대로 | 불필요 |
| D149 | 대시보드 JSON은 `grafana/build.py`로 생성, 테스트가 `--check` | 출처 필터·datasource·공격 이름 값 매핑을 모든 패널에 똑같이 넣고, Flux를 읽을 수 있게 두려고 | 불필요 |
| D150 | 데이터 출처 변수 선택지: AWS(`p4`)·재생(`replay`)·샘플(`sample`) | 우선 AWS만 받음(Q21). 시연 백업(재생)과 개발(샘플)도 같은 화면으로 | 불필요 |
| D151 | InfluxDB 2.7 Flux 우회 3가지: 경보 합치기는 `pivot` 대신 값을 문자열 한 열로 모아 `reduce`, `union` 전에 `group()`, `map` 결과에 그대로 옮긴 열 하나 이상 | `pivot`은 경보마다 표 모양이 갈림, `reduce` 결과에 `join.left`는 내부 오류, 계산 값만 내는 `map`은 조건식이 null이 됨(로컬에서 재현) | 불필요 |
| D152 | 상태 불명 = 열린 경보에 마지막 레코드(경보·근거) 뒤 1단계 15초·2~4단계 90초 무소식. 요약 '열린 경보'에서 따로 세고, 경보 구간 주석은 마지막 레코드까지 | 27_ §7. 샘플처럼 clear 없이 끝난 경보가 지금까지 열린 것처럼 칠해지던 문제(사용자 지적) | 불필요 |
| D153 | `overhead`만 처음 형식으로 남기고 UDP 입력 유지 | 측정 주체·형식이 R5 협의 중 | 탐지 쪽 (R5) |
| D154 | Grafana provisioning `disableDeletion: false` | `true`면 JSON을 지워도 대시보드가 남는다. M10 배포 뒤 옛 대시보드 2개가 남았음. UI 수정 금지(`allowUiUpdates: false`)는 그대로 | 불필요 |
| D155 | 배포 스크립트가 `grafana/dashboards`·`grafana/provisioning`의 서버 파일과 컨테이너 안 파일(해시)을 비교해 다르면 Grafana를 다시 만든다 | M10 배포(#28)에서 checkout이 `grafana/dashboards`의 파일을 모두 바꿔 git이 폴더를 지웠다 다시 만들었고, Grafana 컨테이너는 지워진 옛 폴더(빈 폴더)를 계속 봐서 새 관제 대시보드가 안 보였다(사용자가 서버에서 확인: 서버엔 `monitoring.json`, 컨테이너 안은 비어 있음). compose는 설정이 같으면 Grafana를 다시 만들지 않음 | 불필요 |
| D156 | 상시 KPM2 선 그래프는 점 사이가 6초(3초 묶음 2칸)보다 길게 비면 선을 끊는다(`insertNulls`, `grafana/build.py`의 `KPM2_LINE_BREAK_MS`). 선 밑 채우기는 그대로 | AWS 관제 화면(p4)에서 1분 40초 동안 데이터가 없는데 1→0 사이가 비스듬히 이어져 0~1 사이 값이 있었던 것처럼 보였다(사용자 확인) | 불필요 |
| D157 | 세로선 주석을 둘로 나눈다 — 분석 엔진 세션 시작(`hello`, 파랑)과 DU·CU 재시작(`f1_evt`, 보라). 토글도 따로 | 한 색으로 그리니 AWS 화면에서 15:08~15:13의 약 30초 간격 세로선이 어느 쪽인지(분석 엔진 재시작인지 DU·CU 재시작인지) 마우스를 올려야만 알 수 있었다 | 불필요 |
| D158 | 데이터 출처 선택지에 On-Premise(`lab`)를 더한다 — AWS · On-Premise · 재생 · 샘플. On-Premise는 아직 받지 않아 고르면 빈 화면 | 두 출처(AWS·On-Premise) 구성을 화면에서 미리 갖춰 두려고(사용자 결정 11/11 — "구색만 맞추려고"). 재생(시연 백업)·샘플(개발)은 그대로 둔다(D150) | 불필요 |
| D159 | replay `--from`/`--to`: 원본 데이터 시각 `[from, to)`만 보낸다. 경보는 통째로(구간 안에서 시작한 경보는 구간 밖 근거·`clear`까지, 구간 전에 시작한 경보는 모두 뺌). 시간대 없이 적은 시각(`--retime` 포함)은 한국 시각 | 녹화에서 공격 구간만 시연하려고(사용자 요청 11/11). 시각 기준으로만 자르면 앞뒤가 잘린 경보(raise 없는 clear, pre 근거 없는 raise)가 생긴다. 서버·컨테이너 시계가 UTC라 전에는 `--retime 2026-12-04T13:00:00`이 UTC 13시(한국 22시)로 읽혔다 — Grafana 화면 시각(한국)과 맞춘다 | 불필요 |
| D160 | 요약 줄의 "열린 경보"·"최고 심각도"는 화면 시간 범위와 상관없이 지금까지 조회한다(`stop: now()`). `range`의 start·stop 기준을 섞지 않는 테스트 추가 | 근거를 `-5m`부터 화면 범위 끝까지 조회해서, 지난 범위(예: 16:02:47~16:07:47를 16:16에)를 고르면 start > stop이 되어 `cannot query an empty range`로 두 패널이 깨졌다(사용자 AWS 화면 11/11). 요약 줄은 제목대로 "지금" 상태이고 상태 불명도 now() 기준 | 불필요 |
| D161 | 성능 대시보드 `performance.json`은 탐지 성과부터 — 종류별 경보 수, 단계 비교(`${source}` 대 변수 `kpm_only`, 기본 `replay-kpm-only`), 경보 길이 분포, 룰 × 단계 × 종류 표, 경보가 어떻게 끝났나, 근거 손실, gap, 상시 KPM2 칸 채움·partial 지표. 경보는 시간 범위 안에서 시작한 것만 세고 근거는 읽지 않는다(clear·end가 없으면 '끝이 안 옴'). 수집 오버헤드는 자리만 | 사용자 결정(11/11): eBPF는 항상 켜므로 켬·끔 비교 대신 에이전트 프로세스 몫을 재야 하고(형식은 R5), 그 전에 지금 받는 경보 데이터로 만들 수 있는 탐지 성과부터. 근거를 읽지 않는 것은 넓은 실험 구간에서 근거가 수십만 점이라 느려서 | 탐지 쪽 (R5 오버헤드 형식) |

### 확인 결과 (지금까지)

| 확인 | 결과 |
|---|---|
| `pytest` | 233 passed, 1 failed — 실패는 `test_dashboards`의 Grafana 쿼리 실행(로컬 `.env` 비밀번호 불일치 401, 코드와 무관) |
| 관제 대시보드 쿼리 | 로컬 InfluxDB(샘플 32개 + 개발용 KPM2 묶음)에 Grafana처럼 `v`·변수를 채워 23개 쿼리 모두 실행 확인 |
| 화면 | 사용자가 로컬 Grafana에서 확인, 지적 반영: 경보 구간이 지금까지 칠해짐(상태 불명 처리), 범례 이름 빠짐(`pivot`으로 열 이름), 요약이 0(Flux `map` 버그 우회), 수집 상태·세션 라벨, 판정 요약 높이, 경보 구간 색 연하게 |
| 실시간 재생 | 샘플 5개 + 같은 시간대 KPM2 묶음을 1배속으로 재생해 경보 열림·해제·상태 불명 전환 확인(사용자) |

확인하지 못한 것: Grafana API로 대시보드 쿼리 실행 테스트(로컬 `.env`의 Grafana 비밀번호가 실제와 달라 401), CI(push 뒤), AWS 배포.

### 남은 일

- [x] 성능 대시보드 `performance.json` — 탐지 성과(D161). 로컬 샘플 데이터로 쿼리 11개를 Grafana(12.4.13)에서 실행하고 화면 확인
- [ ] 성능 대시보드 수집 오버헤드 — 탐지 쪽과 형식 협의(R5): 호스트 전체·eBPF 에이전트 프로세스 CPU·메모리, `ebpf_on` 빼기, `/ingest`로 `X-Env` 붙여 보내기
- [ ] 단계 비교 데이터 — 탐지 쪽이 녹화를 1단계만으로 다시 재생해 `X-Env: replay-kpm-only`로 보내기(27_ §3)
- [ ] 로컬 `.env`의 `GRAFANA_ADMIN_PASSWORD`를 실제 값으로 맞춰 대시보드 쿼리 테스트 실행
- [x] PR(`feat/dashboard-M10` → `dev`, #27) → `main` 배포(#28, 2026-11-11). 배포는 Success였지만 Grafana에 새 관제 대시보드가 안 보이고 옛 대시보드가 남음 → 원인 D154·D155. 서버에서 `docker compose up -d --force-recreate grafana`로 풀고, 같은 일이 없게 `fix/grafana-redeploy`로 고침(`docs/m9-complete`는 #27에 함께 병합). 고친 것은 #29 → `main` #30으로 배포
- [ ] (사용자) AWS·로컬 Grafana에서 옛 대시보드 2개(실시간 관제·성능 검증)를 UI에서 지우기 — `disableDeletion: true`일 때 파일이 없어지면서 provisioning 연결이 이미 끊겨, `false`로 바꿔도 저절로 지워지지 않는다(앞으로 지우는 파일부터 적용)
- [ ] AWS에서 관제 화면 확인 (서버 녹화를 `--env replay`로 재생)
