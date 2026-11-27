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
| M10 대시보드 재구성 · 옛 메시지 삭제 | 완료 (PR #27~#38, 배포 #28·#30·#32·#34·#36·#38 — replay·관제·성능(탐지 성과) 대시보드·정리. 남았던 수집 오버헤드는 M11로, 단계 비교는 없앰(D173)) | 2026-11-13 |
| M11 수집 오버헤드 — 스키마 v0.5 · collector · 성능 대시보드 CU 자원 | 완료 (PR #40, 배포 #41) | 2026-11-13 |
| M12 Slack 알림 — Grafana Alerting (공격 경보·수집 멈춤) | 완료 (PR #42, 배포 #43) | 2026-11-13 |

**2026-11-13 요약** — 하루에 #39~#43을 배포했다.
- 탐지 쪽 `L3-01-V` 필드 변경(11/12) 반영: 코드 그대로, 명세 사본·예시·테스트(#39, D162)
- **M11 수집 오버헤드**(#40·#41): 탐지 쪽 `overhead` 형식으로 스키마 v0.5, `overhead`·`overhead_link` 저장, replay, 성능 대시보드 CU 자원 줄(Beszel식). 실제 샘플 30줄로 확인
- 사용자 화면 확인 뒤 대시보드 정리: 단계 비교·자리 표시 삭제, 짧은 공격 이름, 단계(1~4) 표시 삭제, 링크 범례, 범례 표
- **버그 수정**: 관제 경보 목록에서 해제된 경보가 빠지던 것(#28 이후 AWS에도 있었음, D176)
- **M12 Slack 알림**(#42·#43): AWS 공격 경보 발생·끝, 수집 멈춤. README 맨 위 그림을 Mermaid로
- 관제 KPM1 메시지 흐름에서 마지막 메시지가 화면 끝까지 늘어나 보이던 것을 고침(D186), Slack Webhook이 비면 Grafana가 안 뜨는 것을 막는 테스트(D187), 표 열 순서가 새로고침마다 바뀌던 것을 고정(D188)
- 브랜치 정리: 원격·로컬 모두 `main`·`dev`만(병합된 `docs/l3-01-v-1112`·`feat/dashboard-M11`·`feat/dashboard-M12` 삭제)

**2026-11-16 요약** — 브랜치 `feat/hide-annotation-toggles`
- 관제 대시보드 위쪽 줄 간단히: 주석 토글 6개와 경보 고르기 칸을 숨김(D189). 그래프 위 표시는 늘 켜져 있고, 경보는 경보 목록 행을 눌러 고른다
- 관제 맨 위 '요약 — 지금' 줄을 없애고 성능 대시보드의 탐지 결과 줄(공격별 경보 수, 경보 길이 분포, 공격별 경보 결과)을 옮김(종류별 경보 수는 없앰). 경보 목록의 룰별 경보 수 막대도 없애고 경보 표를 한 줄 가득. 성능 대시보드의 경보·입력 품질 줄도 없애 성능은 CU 자원만(D190)
- 관제 줄·패널 제목을 짧게: 탐지 결과 · KPM · 경보 목록, RRC 연결 시도 · 성공 · 무응답, UE 컨텍스트 · 연결 UE 수, 근거 KPM, UE_EVENT — UE별 메시지 흐름, UE_EVENT — 메시지 흐름 상세, 경보 길이 분포, 성능의 Overhead · CPU 사용률 · RRC 연결 시도, 공격별 경보 결과의 열 'high까지' → 'high 도달', 성능 패널 제목의 괄호 설명 빼기(D191)
- 배포 뒤(11/16): 성능 Overhead '노드'에 AWS node_id `p4-cu`가 그대로 보여, cu로 끝나는 node_id는 'CU'로 표시(D192)
- 경보 상세: 판정 요약의 갈래 열·걸린 UE의 전제 열 삭제, 걸린 UE '불확실' → '관측 오류'(D193)
- 성능 Overhead 시간 그래프 범례가 두 개씩 나오던 것: node_id `cu`(11/15)와 `p4-cu`(11/16)가 섞인 범위라 노드별 계열이 둘이었다. cu로 끝나는 node_id를 한 노드 CU로 묶음(D194)
- 관제 패널 설명(ⓘ)에서 명세 참조('27_ §5.1' 등)를 뺌. 성능 대시보드 설명은 이미 참조가 없음(D195)
- 로컬 환경 정리(코드 변경 없음):
  - 로컬 Grafana가 켜지지 않던 것: 컨테이너가 11/04(M12 전)에 만든 것이라 `SLACK_WEBHOOK_URL`이 없어 알림 provisioning에서 멈췄다(D187과 같은 증상). `docker compose up -d grafana`로 다시 만들어 해결
  - 로컬 Grafana 관리자 비밀번호를 `.env` 값으로 맞춤(`grafana cli admin reset-admin-password`, 사용자 확인). 쿼리 테스트 401 해결 — `tests/test_dashboards.py` 30 passed
  - 옛 대시보드 'PortRAN 실시간 관제'(`portran-realtime`)·'PortRAN 성능 검증'(`portran-evaluation`)을 API로 삭제. `disableDeletion: true`였던 때 파일이 지워져 provisioning이 풀린 일반 대시보드로 남아 있었다(그래서 지금 설정으로도 자동으로 안 지워짐)

**2026-11-18 요약** — Claude Code 작업 흐름 (브랜치 `feat/agent-workflow`)
- 작업 기록 hook: 프롬프트·도구 호출·결과·실패·서브에이전트를 `logs/agent/<세션 ID>.jsonl`에(비밀 값 가림), `agent_log.py list|show|errors`로 다시 보기·오류 추적(D196~D198)
- 역할 분리: `.claude/agents/` researcher·planner·reviewer, CLAUDE.md 12절 10항. 읽기 전용 역할의 Bash 쓰기를 hook으로 막음(D199), Reviewer에게는 완료 조건·비교 기준만(D200)
- 이 변경 자체를 실제 `reviewer`로 검증: 1차 수정 필요(비밀 값 가림 빈틈·가드 우회 등 10건) → 고침 → 2차 수정 필요(한글 조사 붙은 짧은 비밀 값, 가드 우회 등 8건) → 고침 → 3차 통과(낮음 4건도 고침) → 4차 통과(중간 1·낮음 6, 4차 뒤 고친 것은 검증 안 받음)


**2026-11-18 요약** — 대시보드 로딩·표시 (브랜치 `fix/dashboard-loading-display`)
- 관제 KPM 그래프가 7일 범위에서 비던 것(시간 초과·점 수 초과·5초 새로고침 취소): 셀 거르기를 정규식으로, 3초 원본을 화면 간격에 맞춘 구간으로 묶음. 성능 대시보드도 같은 원인이라 함께(D202). AWS 7일 쿼리 30초 초과 → 0.8초 이하
- 표시: 대표 값 ratio를 %로, 판정 요약 모드 열 삭제, UE를 셀-uid로(D203). 경보 구간 어디에 마우스를 대도 툴팁에 경보가 보이게(D204)

- 배포 뒤(11/18): 관제 KPM 그래프의 경보 구간이 새로고침(5초)마다 깜빡이던 것 — 경보 구간을 주석 대신 경보 계열(refId B)로 칠함(D209, 브랜치 `fix/alert-region-flicker`)


**2026-11-20** — 관제 경보 상세 '걸린 UE' 표에서 관측 오류·근거 열 삭제(D210, 브랜치 `fix/alert-ue-columns`)

**2026-11-20** — 성능 대시보드에 수집 지연(받은 시각 − 데이터 시각) p50·p95·p99 줄, collector가 `ingest_delay`로 잼(D211, 브랜치 `feat/ingest-delay`)


**2026-11-20** — 관제 경보 목록에서 룰 ID 열 삭제(D212), 데이터 출처를 탐지 쪽 새 `X-Env` `aws`·`on-premise`로 바꾸고 Slack에 On-Premise 추가(D213) — 브랜치 `fix/alert-list-rule-column`

**2026-11-20** — 관제 '칸 일부 없음'을 세션 보고 주기로 판정(D214 — 11/13~11/15 1,000 ms 세션의 잘못된 줄무늬), 성능 노드를 늘 CU 하나로(D215 — `p4-e2e`로 보이던 것), CPU·메모리 패널을 '(전체)'·'(분석 엔진)'으로 — 브랜치 `fix/overhead-panels-partial-period`

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
| Q23 | AWS 상시 KPM2의 `ext.UeCtxMax`가 **125까지** 올라 셀 한도 96(27_ §5.3, 대시보드 `CELL_LIMIT`)을 넘었다(11/11 15:53 공격). 한도가 이 테스트베드 셀의 실제 값인지, `UeCtxMax`가 한도를 넘는 대기 UE까지 세는지. 1·2단계 경보가 high가 되는 기준(90% = 86)과 관련. `hello`의 `cells[].max_conn`에 실제 한도가 오면 그 값을 쓰도록 바꿀 수 있음. 11/12 탐지 쪽 변경으로 `L3-01-V`의 절대 수 문턱 `f_abs`도 셀 한도 × 0.1(올림)이 되어, 한도가 틀리면 `C2a` 판정도 달라진다(D162) | 탐지 엔진·테스트베드 | 관제 "UE 컨텍스트 · 연결 UE 수", `grafana/build.py` `CELL_LIMIT` |
| Q24 | AWS p4 셀이 **1개(6733824) → 4개(6733824~6733827)** 로 늘었고, 최근 3시간에 DU·CU 재시작(`f1_evt`)이 26번 왔다(11/11 오후). 의도한 테스트베드 변경·시험인지 | 테스트베드·탐지 엔진 | 관제 화면 셀 변수(셀을 하나 고르면 그 셀만 보임) |
| Q26 | AWS 상시 KPM2 신뢰도 점검(11/20)에서 나온 탐지 쪽·테스트베드 요청: ① 같은 시간대 CU 로그로 KPM2 카운터를 다시 세어 대조(탐지 쪽 `tools/ocu_log_to_kpm2.py`, 탐지 쪽 Q-08) — 지표끼리는 맞지만(RRC 시도 = 성공 + 실패, 세션 4개·3초 칸 6만 개에서 관계식이 한 번도 안 깨짐) 정답 대조는 없음 ② 시험 데이터(`hello` 노드 `stage4_yellow` 등)는 실측 `aws`가 아닌 별도 `X-Env`로 ③ 보고 주기를 100 ms로 고정할지(11/13~11/15 세션 7개는 1,000 ms — 대시보드는 D214로 세션마다 맞춤) ④ 전송기가 `hello`의 `node_id`만 `cu`로 바꾸고 `overhead`는 그대로 보냄(`p4-e2e`) — 대시보드는 D215로 쓰지 않으니 맞출지는 탐지 쪽 판단 ⑤ 정상 데이터가 적음(`aws` 10분에 연결 시도 4건, 연결 UE 최대 1대) — 1단계 룰의 평소 값 기준선이 되려면 UE 여러 대로 정상 접속을 꾸준히 | 탐지 엔진·테스트베드 | D214·D215 |
| Q25 | Claude Code 작업 기록 hook·읽기 전용 가드를 프로젝트 설정(`.claude/settings.json`)으로 커밋하면, 이 저장소에서 Claude Code를 쓰는 팀원 모두에게 적용된다(기록은 각자 PC의 `logs/agent/`에만, 비밀 값은 가림). 역할 분리는 기본 꺼짐(D208, 켜려면 `"PORTRAN_ROLE_WORKFLOW": "on"` 또는 요청), 작업 기록은 기본 켬(끄려면 각자 `.claude/settings.local.json`의 `env`에 `"PORTRAN_AGENT_LOG": "off"`) — 읽기 전용 가드는 그대로(D207). `disableAllHooks`는 가드까지 꺼서 권하지 않음 | 이 저장소에서 Claude Code를 쓰는 팀원 (알림) | D198·D207, `docs/agent-workflow.md` 4절 |

### 미정 (확정 전까지 TODO로 둠)

| # | 내용 | 현재 처리 |
|---|---|---|
| T9 | 판정 근거 키 이름(35_ 엑셀, D218)에 없는 키: L3-01-V cond `U`·values `a_w`·`f_w`·`ratio`·`base`·`sigma`·`u`, L3-20 cond `peer_uncertain`, L3-21 cond `reg_repeat`·`fail`, L3-14 cond `enquiry_before_as_sec`, 판정 보류 경보 `held_count`·`held_w`, 4단계 이상 유형(AN-*) 전부(11/25) | 원래 키로 보임. 이름이 정해지면 `grafana/evidence-key-names.json`에 더하고 `_이름_없음`에서 뺀다 |
| T8 | CLAUDE.md 0절 — 세션 시작 때 논문 PDF 25쪽을 읽어 메인 컨텍스트가 65k → 117k(+52k)로 늘고 이후 모든 응답에 실린다(11/18 세션 약 8M 캐시 읽기 ≈ 메인의 15%, D206 확인 결과). 지표·공격 유형·탐지 규칙을 다룰 때만 읽게 바꿀지 | 사용자 결정 전까지 지금 규칙대로 읽음 |
| T7 | 탐지 쪽 `overhead` 실제 출력에서 확인할 것: ① `link[]`의 `ingress`·`egress`가 빈 객체(`{}`)로 올 수 있는지(물었지만 답 없음) ② `t_start_ms`가 3초 경계에 맞는지 ③ 첫 구간 `null`의 모양. **11/13 샘플 30줄(`tests/data/overhead/`)로 ②는 확인**(구간 3,000 ms, 3초 경계, 빈틈 없이 이어짐). ①③은 샘플에 없었음(기동 직후가 아니고 링크 값이 모두 있음) | 빈 객체·키 없음·`null`을 모두 '값 없음'으로 받고 필드를 뺌 |
| T6 | 분석 엔진 실측 녹화에서 확인할 것(27_ §8): `session` 실제 형식, `ue_evt` 필드(분석 엔진 팀 답 대기), Table II 나머지(재수립·재개 4종은 `null` 예상), 실제 양(셀·UE 수) | `evidence.raw`는 해석하지 않고 그대로 저장. `session`은 비어 있지 않은 문자열만 검사 |

### 해결됨

| # | 내용 | 해결 |
|---|---|---|
| Q21 | 데이터 출처 선택 AWS / On-Premise — 우선 AWS만 받고 On-Premise는 나중(11/09) | 2026-11-20 해결: 탐지 쪽이 `X-Env`를 `aws`·`on-premise`로 바꿈. 대시보드 출처 `aws`·`on-premise`(+ 11/20 전 AWS 실측 'AWS (이전 p4)'), Slack도 출처마다 규칙(D213). On-Premise는 연구실이 아니라 우리 실물 장비에서 보내고, 그 공인 IP는 보안 그룹에 열어 둠(사용자) |
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

## M10 — 대시보드 재구성 · 처음 메시지·mock·evaluator 삭제 (2026-11-09~11-13, 브랜치 `feat/dashboard-M10` 외 — 병합 뒤 삭제, 완료)

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


### 한 일 — 첫 배포(#28) 뒤 고친 것·더한 것 (2026-11-11)

PR은 모두 `<브랜치>` → `dev` 다음 `dev` → `main`(Create a merge commit)으로 배포했다.

| PR → 배포 | 내용 | 파일 | 결정 |
|---|---|---|---|
| #29 → #30 | Grafana가 옛 대시보드 폴더(빈 폴더)를 붙잡아 새 관제 대시보드가 안 보이던 문제 — 배포 스크립트가 서버와 컨테이너 안 파일 해시가 다르면 Grafana를 다시 만든다. 지운 JSON의 대시보드도 지운다 | `deploy/server-deploy.sh`, `grafana/provisioning/dashboards/dashboards.yml`, `tests/test_deploy.py`(2개), `docs/deploy.md` 문제 해결 | D154·D155 |
| #31 → #32 | 상시 KPM2 선 그래프가 6초(3초 묶음 2칸) 넘게 데이터가 없으면 선을 끊는다 — 받지 않은 구간이 비스듬히 이어져 값이 있었던 것처럼 보이던 문제 | `grafana/build.py`(`KPM2_LINE_BREAK_MS`), `docs/dashboard-design.md` 4절 | D156 |
| #33 → #34 | ① 세로선을 분석 엔진 세션 시작(`hello`, 파랑)과 DU·CU 재시작(`f1_evt`, 보라)으로 나누고 토글도 따로 ② 데이터 출처에 On-Premise(`lab`, 선택지만) ③ replay `--from`/`--to`(원본 데이터 시각 구간, 경보는 통째로)와 시각을 한국 시각으로 읽기(`--retime` 포함, 로그 시각도) ④ Python 3.10에서 `…Z` 시각을 못 읽던 것(CI 실패) | `grafana/build.py`, `replay/replay.py`, `tests/test_dashboards.py`·`test_replay.py`(구간·KST 4개), README·CLAUDE.md 9·11절·`docs/deploy.md` 7절 | D157·D158·D159 |
| #35 → #36 | 지난 시간 범위를 고르면 요약 줄 "열린 경보"·"최고 심각도"가 `cannot query an empty range`로 깨지던 문제 — 두 패널은 지금(`now()`)까지 조회. 모든 쿼리의 `range` start·stop 기준이 섞이지 않는지 검사하는 테스트 | `grafana/build.py`(`alert_summary`의 `stop`), `tests/test_dashboards.py`, CLAUDE.md Flux 주의 | D160 |
| #37 → #38 | **성능 대시보드** `performance.json`(uid `portran-performance`) — 탐지 성과: 종류별 경보 수, 단계 비교(요약·룰별 막대), 경보 길이 분포, 룰 × 단계 × 종류 표, 경보가 어떻게 끝났나, 근거 손실, 입력 끊김(gap), 상시 KPM2 칸 채움, 일부만 측정된 지표, 파이프라인 완성 뒤 자리. CI의 Grafana 쿼리 테스트에 `${kpm_only}` 값 추가(빠뜨려 CI 실패)와 바꾸지 않은 변수 검사 | `grafana/build.py`(`performance()`, `alert_summary`가 근거 없이도 동작), `grafana/dashboards/performance.json`, `tests/test_dashboards.py`, README·CLAUDE.md 9.2절·`docs/dashboard-design.md` 3절 | D161 |
| (정리) | 원격·로컬 브랜치를 `main`·`dev`만 남기고 지움(모두 `main`에 병합된 것: 원격 10개, 로컬 12개). 지운 원격 브랜치는 각 PR의 "Restore branch"로 되살릴 수 있다 | — | — |

### 한 일 — 탐지 쪽 `L3-01-V` 필드 변경 반영 (2026-11-13, 브랜치 `docs/l3-01-v-1112`)

탐지 쪽 알림(11/12): `L3-01-V` `raise` 줄의 `params`에서 `k`가 빠지고 `z`(급증 문턱의 표준편차 배수, 3.0)·`f_abs_frac`(0.1, normal 모드만)가 생김. `f_abs`는 고정 10에서 셀 한도 × `f_abs_frac` 올림(한도 96이면 10)으로 바뀌고 normal 모드이고 셀 한도를 알 때만 실림. `values`에 `sigma`(기준선 표준편차)가 `base` 뒤에 생김. `C3`은 `a_w` ≥ `base` + `z` × `sigma`(전에는 `k` × `base`), `C2a`는 셀 한도를 모르면 나오지 않음.

| 파일 | 변경 |
|---|---|
| `reference/detection/27_…명세서.md` | 맨 위에 변경 반영 표시, §5.4 `L3-01-V` 표(`C2a`·`C3` 뜻, `sigma`, `z`·`theta`·`f_abs_frac`·`f_abs`), §5.7 예시, §7.1 필드 타입 표(실수: `sigma`·`z`·`f_abs_frac`) |
| `CLAUDE.md` 5.1절 · `schema/SCHEMA.md` 3.1절 | 경보 예시를 새 형식으로(테스트의 예시 메시지도 이것을 씀) |
| `tests/test_ingest.py` | 새 형식 3가지(normal, `dl_missing`, 셀 한도 모름 — `f_abs`·`C2a` 없음)가 스키마를 통과하고 `values_json`·`params_json`에 그대로 저장되는지, 대표 값은 `ratio`가 있을 때만 |
| 코드 | 바꾸지 않음(D162) |
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
| D162 | 탐지 쪽 `L3-01-V` 경보 필드 변경(11/12 알림)을 반영 — 코드는 그대로, 탐지 쪽 명세 사본(27_ §5.4·§5.7·§7.1)과 예시(CLAUDE.md 5.1절, SCHEMA.md 3.1절)를 새 형식으로 고치고 테스트 추가. 저장소의 탐지 쪽 샘플(`tests/data/detection/`, `k` 형식 4개 파일)은 바뀌기 전 형식 그대로 둔다 | `values`·`params`는 스키마에서 형식 제한 없는 객체이고, 저장은 JSON 문자열 통째(`values_json`·`params_json`), 화면(경보 상세 '판정 근거 값')도 그대로 보여 주므로 필드가 바뀌어도 받기·저장·표시가 그대로 된다. 대표 값(`ratio`)도 그대로 있음. 샘플은 탐지 엔진이 실제로 낸 출력이라 임의로 고치지 않음(새 샘플은 탐지 쪽에서 받으면 바꿈) | 불필요 |

### 확인 결과 (지금까지)

| 확인 | 결과 |
|---|---|
| `pytest` | 233 passed, 1 failed — 실패는 `test_dashboards`의 Grafana 쿼리 실행(로컬 `.env` 비밀번호 불일치 401, 코드와 무관) |
| `pytest` (11/11, #37 기준) | 253개 — 로컬에서 251 passed + Grafana 쿼리 실행 2개는 임시 Grafana(아래)로 통과. CI는 Python 3.10에서 두 번 실패(`…Z` 시각 #33, `${kpm_only}` 누락 #37) → 고친 뒤 병합 |
| 임시 Grafana로 확인 (11/11) | 로컬 InfluxDB가 있는 compose 네트워크에 `grafana/grafana:12.4.13`을 포트 3001로 따로 띄워(저장소 provisioning 마운트) 관제 23개·성능 11개 쿼리 오류 0, `test_all_queries_run_without_error` 2 passed. Edge headless로 성능 화면을 캡처해 표 열 순서·막대 이름 잘림·단위를 다듬음. 끝나면 컨테이너를 지움 |
| 단계 비교 계산 | 1단계만 재생 결과가 없을 때 '재생 없음', 있을 때(샘플을 자기 자신과 비교) 41·41·0, '못 잡은 경보' 합은 임의 값으로 따로 확인 |
| replay 구간 | `TZ=UTC`(서버처럼)에서 두 샘플 경보를 이은 파일에 `--from 12:50:06 --to 12:50:30` → 구간 안에서 시작한 경보 하나만, 구간 뒤 clear까지 667건 |
| 탐지 쪽 `L3-01-V` 변경 (11/13) | `pytest tests/test_ingest.py tests/test_schema.py tests/test_collector.py` 175 passed(새 형식 테스트 3개 포함) |
| AWS (사용자, 11/11) | #28 뒤 Grafana를 다시 만들어 관제 대시보드가 보임. 실측 p4 데이터로 관제 화면 확인: UE 컨텍스트 고갈 공격(15:53·16:02 등, UE 컨텍스트 최대 125)이 경보 구간·빨간 위험 구간으로 보임, 선 끊기(#31)·세로선 색(#33) 반영. 지난 범위를 고를 때의 요약 오류를 사용자가 찾아 #35로 고침 |
| 관제 대시보드 쿼리 | 로컬 InfluxDB(샘플 32개 + 개발용 KPM2 묶음)에 Grafana처럼 `v`·변수를 채워 23개 쿼리 모두 실행 확인 |
| 화면 | 사용자가 로컬 Grafana에서 확인, 지적 반영: 경보 구간이 지금까지 칠해짐(상태 불명 처리), 범례 이름 빠짐(`pivot`으로 열 이름), 요약이 0(Flux `map` 버그 우회), 수집 상태·세션 라벨, 판정 요약 높이, 경보 구간 색 연하게 |
| 실시간 재생 | 샘플 5개 + 같은 시간대 KPM2 묶음을 1배속으로 재생해 경보 열림·해제·상태 불명 전환 확인(사용자) |

확인하지 못한 것: AWS에서 성능 대시보드를 p4 실험 구간으로 본 화면(11/11에는 로컬 Grafana를 보고 있었음), 실제 1단계만 재생(`replay-kpm-only`) 데이터로 본 단계 비교, 로컬 `.env`의 Grafana 비밀번호(아직 실제와 다름).

### 환경 메모 (11/11)

- **로컬 Grafana 비밀번호가 `.env`와 달라 쿼리 테스트가 401일 때**: 임시 Grafana를 `.env` 계정으로 띄워 같은 테스트를 돌린다. `docker run -d --rm --name portran-grafana-check --network dashboard_default -p 127.0.0.1:3001:3000 --env-file <INFLUX_ORG·INFLUX_BUCKET·INFLUX_TOKEN·GF_SECURITY_ADMIN_USER·GF_SECURITY_ADMIN_PASSWORD만 담은 파일> -v <저장소>/grafana/provisioning:/etc/grafana/provisioning:ro -v <저장소>/grafana/dashboards:/etc/grafana/dashboards:ro grafana/grafana:12.4.13` 뒤 `GRAFANA_PORT=3001 pytest tests/test_dashboards.py -k run_without_error`. 끝나면 `docker stop portran-grafana-check`.
- **Windows Docker Desktop**에서는 바인드 마운트한 대시보드 JSON을 고쳐도 실행 중인 Grafana가 다시 읽지 않았다 → 컨테이너를 다시 시작한다. AWS(Linux)에서는 배포 때 바로 반영됐다.
- **서버에서 명령은 `sudo -i` 뒤 `/opt/portran/dashboard`에서** 실행한다. 일반 사용자로 하면 `.env` 읽기 거부, git `dubious ownership`이 난다.

### 남은 일

- [x] 성능 대시보드 `performance.json` — 탐지 성과(D161). 로컬 샘플 데이터로 쿼리 11개를 Grafana(12.4.13)에서 실행하고 화면 확인
- [ ] 성능 대시보드 수집 오버헤드 — 탐지 쪽과 형식 협의(R5): 호스트 전체·eBPF 에이전트 프로세스 CPU·메모리, `ebpf_on` 빼기, `/ingest`로 `X-Env` 붙여 보내기
- [x] ~~단계 비교 데이터 — 탐지 쪽이 녹화를 1단계만으로 다시 재생해 `X-Env: replay-kpm-only`로 보내기~~ — 단계 비교를 대시보드에서 없애 필요 없음(D173, 11/13)
- [ ] 로컬 `.env`의 `GRAFANA_ADMIN_PASSWORD`를 실제 값으로 맞춰 대시보드 쿼리 테스트 실행(그 전까지는 위 환경 메모의 임시 Grafana로)
- [ ] AWS에서 성능 대시보드 확인 — `http://3.39.170.31:3000/d/portran-performance?var-source=p4`, 시간 범위를 실험 구간으로
- [ ] 탐지 쪽 확인: Q23(셀 한도 96 vs `UeCtxMax` 125), Q24(셀 4개·DU·CU 재시작 26회)
- [x] PR(`feat/dashboard-M10` → `dev`, #27) → `main` 배포(#28, 2026-11-11). 배포는 Success였지만 Grafana에 새 관제 대시보드가 안 보이고 옛 대시보드가 남음 → 원인 D154·D155. 서버에서 `docker compose up -d --force-recreate grafana`로 풀고, 같은 일이 없게 `fix/grafana-redeploy`로 고침(`docs/m9-complete`는 #27에 함께 병합). 고친 것은 #29 → `main` #30으로 배포
- [ ] (사용자) AWS·로컬 Grafana에서 옛 대시보드 2개(실시간 관제·성능 검증)를 UI에서 지우기 — `disableDeletion: true`일 때 파일이 없어지면서 provisioning 연결이 이미 끊겨, `false`로 바꿔도 저절로 지워지지 않는다(앞으로 지우는 파일부터 적용)
- [x] AWS에서 관제 화면 확인 — 재생 대신 실측 p4 데이터로 확인(11/11, 사용자). 고친 것은 #31·#33·#35
- [x] #29~#38 배포 (2026-11-11) — 위 "첫 배포 뒤 고친 것·더한 것"
- [x] 브랜치 정리 — 원격·로컬 모두 `main`·`dev`만 (2026-11-11)

---

## M11 — 수집 오버헤드: 스키마 v0.5 · collector · 성능 대시보드 CU 자원 (2026-11-13, 브랜치 `feat/dashboard-M11`)

목표: 탐지 쪽이 11/13에 보낸 `overhead` 형식(분석 엔진 계측기가 3초마다)을 받아 저장하고, 성능 대시보드에 CU 자원 사용률 추이를 Beszel식으로 보인다. 지금까지 받던 옛 `overhead`(ns `ts`·`node`·`ebpf_on`·`cpu_pct`·`mem_mb`, UDP, 실제로 보내는 곳 없음)는 지운다.

탐지 쪽 답(11/13, 사용자 정리): ① 상시 지표와 오버헤드 모두 3,000 ms마다 ② 전송기가 `/ingest`로 보냄 ③ (`link` 빈 객체 질문 — 답 없음, T7) ④ `node_id`는 `cu`로 통일 ⑤ CU에 분석 엔진과 탐지 엔진을 함께 두고 CU 자원 사용률 추이를 본다(eBPF 프로그램 커널 시간을 따로 재지 않음) ⑥ 실제 출력 샘플은 요청하기로 ⑦ 오버헤드는 기존 전송기와 **별개의 전송기**가 같은 `/ingest`로 1초마다 POST한다 — 1초는 보내는 주기이고 측정 구간은 3초 그대로.

### 한 일

| 파일 | 변경 |
|---|---|
| `schema/messages.schema.json` · `SCHEMA.md` (v0.5) | `overhead`를 새 형식으로(6절): `ver` 1, `session`·`seq`, `t_start_ms`·`t_end_ms`(ms), `cpu`(`count` ≥ 1, `node_busy_cores`·`process_cores` 0 이상 실수·`null`), `memory`(바이트 정수·`null`), `link[]`(`interface_name` 필수, `ingress`·`egress`의 패킷·바이트 증가분). 모르는 필드 받음. 옛 형식과 `$defs.epoch_ns`·`$defs.node` 삭제. 1절 공통 규칙을 모든 레코드 하나로 합침 |
| `collector/influx_writer.py` | `overhead` 점(`t_start_ms`, tags env·session·node, 코어 수는 늘 실수, 바이트는 정수, `null` 뺌), `overhead_link_points`(NIC 한 칸 = 점 하나) |
| `collector/collector.py` · `ingest.py` | `overhead`도 환경별 녹화(`raw-<시각>.jsonl` 따로 쓰던 것과 `raw_path` 삭제), 중복 키 (`session`, `seq`), 시각 순서 경고(`t_start_ms` ≥ `t_end_ms`) |
| `replay/replay.py` | `overhead`도 재생: 나가는 시각 = `t_end_ms`, `t_start_ms`·`t_end_ms`를 옮기고 `session`에 재생 표시 |
| `grafana/build.py` · `performance.json` · `monitoring.json` | 성능 대시보드에 **CU 자원** 줄(D168·D172). 사용자 화면 확인 뒤(11/13): 단계 비교·자리 표시 삭제(D173), 짧은 공격 이름(D174), 단계 표시 삭제(D175), 경보 목록 정렬 버그 수정·열 순서(D176), 링크 범례(D177), '부하와 함께' 범례 표(D178). 탐지 쪽 overhead 샘플을 `tests/data/overhead/`에 넣고 테스트 3곳(스키마·`/ingest`·통합) |
| `.github/workflows/ci.yml` | `aws-compose`의 UDP `overhead` 단계를 새 형식(링크 한 칸 포함)으로, `overhead`·`overhead_link` 저장 확인 |
| 테스트 | `test_schema.py`(새 형식 받기 9가지·거부 15가지, 옛 형식 거부), `test_collector.py`(공통 동작 시험을 새 `overhead`로, 변환 3개), `test_ingest.py`(중복 키·UDP 거르기), `test_replay.py`(재생), `test_influx_integration.py`(실제 InfluxDB에 `overhead`·`overhead_link`), `test_dashboards.py`(CU 자원 줄 구성) |
| 문서 | CLAUDE.md(2·5·6·8·9.2·13절), README(collector 녹화·성능 대시보드), `docs/dashboard-design.md` 3절(배치도, 3.3절 새로), `.env.example`·`docker-compose.aws.yml` 주석(UDP는 시험용) |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D163 | `overhead`를 탐지 쪽 형식으로 바꾸고 옛 형식은 받지 않는다(스키마 v0.5). 규칙은 다른 레코드와 같게(ms, 모르는 필드 받음, `null` = 모름, `ver` 1) | 사용자 결정(11/13 "M11 시작"). 옛 형식은 보내는 곳이 없었고, 같은 `type`에 두 형식을 두면 검증이 흐려진다 | 탐지 쪽 (형식은 탐지 쪽이 정함) |
| D164 | NIC별 링크 값은 `overhead_link` measurement로 따로(한 칸 = 점 하나, tags iface·role) | `link[]` 배열을 Flux에서 행으로 펴기 어렵다(`alert_ue`와 같은 이유). NIC 수만큼 series가 생기지만 NIC는 몇 개뿐 | 불필요 |
| D165 | 코어 수(`node_busy_cores`·`process_cores`)는 늘 실수, 바이트·패킷은 정수로 저장. 점유율(%)·초당 값은 화면에서 계산 | 예시처럼 `0`(정수)과 `0.03`(실수)이 같은 필드에 섞이면 InfluxDB가 거부한다. 분모(코어 수·구간 길이)를 함께 저장해 두면 나중에 다른 비율도 낼 수 있다(탐지 쪽 설명과 같은 이유) | 불필요 |
| D166 | `overhead` 중복 키 = (`session`, `seq`) | `hello`·`f1_evt`·`kpm2`(원본)·`ue_evt`와 한 번호열(탐지 쪽 설명) | 탐지 쪽 (27_ §3의 상시 키처럼 답 대기) |
| D167 | 녹화를 모두 환경별 파일 하나로(`raw-<시각>-<환경>.jsonl`). 따로 쓰던 `raw-<시각>.jsonl`과 `Collector.raw_path` 삭제 | 그 파일은 옛 `overhead` 전용이었다. 새 `overhead`는 `X-Env`로 와서 다른 레코드와 같은 녹화에 남아야 replay로 함께 재생된다 | 불필요 |
| D168 | 성능 대시보드 **CU 자원** 줄 — Beszel식 2열: 노드(코어·메모리·마지막 수신), 고른 범위 요약(평균·최대 CPU %, 최대 메모리 %, 분석 엔진 평균 코어·최대 RSS), CPU 사용률, CPU 내역(분석 엔진 + 그 밖, 쌓기, 점선 = 코어 수), 메모리 사용량(점선 = 전체), 메모리 내역, F1·N2 트래픽(바이트/초, 위 들어옴·아래 나감), 부하와 함께(왼쪽 CPU %, 오른쪽 RRC 연결 시도 막대 — 고른 셀 합, 3초). 선은 6초 넘게 비면 끊음. 노드 변수는 두지 않음 | 사용자 결정(11/13, Beszel 화면 예시). eBPF는 늘 켜므로(11/11) 켬·끔 비교 대신 추이와 분석 엔진 몫. 부하와 함께는 오버헤드·상시 KPM2가 모두 3초 칸이라 칸끼리 겹친다. 노드는 `cu` 하나뿐 | 불필요 |
| D169 | `link[]`의 빈 객체·키 없음·`null`은 모두 '값 없음'(필드 뺌). `interface_name`이 없는 칸은 거부 | 빈 객체가 올 수 있는지 답이 없어(T7) 너그럽게 받는다. NIC 이름이 없으면 어느 링크인지 알 수 없다 | 탐지 쪽 (T7) |
| D170 | replay도 `overhead`를 재생한다(`kpm2`처럼 시각을 옮기고 `session`에 재생 표시) | 녹화를 재생하면 CU 자원 줄도 함께 보여야 시연 백업이 된다 | 불필요 |
| D171 | 오버헤드 전용 전송기(1초마다 POST)를 그대로 받는다 — collector·nginx·대시보드 바꿀 것 없음 | collector는 여러 연결의 `/ingest` 요청을 큐에 넣어 하나씩 처리하므로 두 전송기가 동시에 보내도 섞이지 않는다. nginx에 요청 수 제한이 없고 같은 CU IP라 보안 그룹도 그대로. 빈 묶음은 `200 {"accepted":0,…}`. 보내는 주기만 1초이고 구간은 3초라 3초에 한 줄씩 생긴다 | 탐지 쪽: 새 전송기도 `X-Env`(`p4`)·주소·인증서·헤더·응답 처리(503 다시, 400 버림)를 기존 전송기와 같게, 줄은 계측기가 만든 그대로(`session`·`seq` 유지) |
| D172 | 링크는 두 칸 — **F1·N2 SCTP 트래픽(바이트/초)**과 **F1·N2 SCTP 패킷(패킷/초)**, '부하와 함께'는 아래 줄에 넓게. 이름·설명에 'SCTP 시그널링만'을 밝힌다 | 사용자 결정(11/13): 바이트는 바이트/초 그대로(비트/초 아님), 초당 패킷 추가. 탐지 쪽 답: `wire_byte_count`·`sctp_packet_count`는 SCTP 패킷만(F1-U 사용자 데이터는 빠짐). 3초 증가분 ÷ 3초라 1초 안의 순간 최대는 안 보인다(사용자 확인) | 불필요 |
| D173 | 성능 대시보드에서 **단계 비교(1~4단계 vs 1단계만)를 없앤다** — 요약 칸·룰별 두 막대·변수 `kpm_only` 삭제, 막대는 '공격별 경보 수'(막대 하나). '파이프라인 완성 뒤 채울 것' 자리(글)도 없앤다 | 사용자 결정(11/13). 1단계만 재생 데이터를 받을 계획이 없고, 빈 '재생 없음'·자리 표시가 화면을 차지했다 | 불필요 (탐지 쪽에 `replay-kpm-only` 재생을 부탁하지 않아도 됨) |
| D174 | 공격 이름은 두 대시보드 모두 **짧은 이름**('#1 UE 컨텍스트 고갈 (RRC 폭주, 변형)' → 'UE 컨텍스트 고갈'). `grafana/build.py` `short_rule_name`이 `rule-names.json`의 이름에서 `#번호`·괄호 설명·' — ' 뒤·'이상 유형 — '를 뺀다 | 사용자 요청(11/13). 긴 이름은 막대 그래프·표에서 잘렸다. 원래 이름(논문 번호·변형)은 `rule-names.json`에 그대로 둔다 | 불필요 |
| D175 | 화면에서 **단계(1~4) 표시를 없앤다** — 관제 경보 목록·판정 요약의 단계 열, 경보 상세 제목의 '(1단계 경보)'·'(2~4단계)', 경보 구간 주석 글의 '단계 n', 성능 표의 룰·단계 열(표 이름 '룰 × 단계 × 종류' → '공격별 경보 결과'). 근거 메시지 표의 phase 열은 '단계' → '구간'(pre·active·post). 판정 기준(상태 불명 15초·90초 등)은 그대로 | 사용자 요청(11/13) | 불필요 |
| D176 | **관제 경보 목록의 정렬을 `map` 앞으로**(원래 열 `start`로), 열 순서를 organize로 고정. 성능 '공격별 경보 결과'도 같게 | InfluxDB 2.7에서 `map`으로 만든 열("시작")로 `sort`하면 줄이 빠졌다 — 해제된 1단계 경보(UE 수가 빈 경보)가 목록에서 사라짐. **#28 이후 AWS 관제 화면에도 있던 버그**(M11 확인 중 임시 스택에서 찾음, dev 판으로 재현). 열은 이름순으로 섞여 나왔다 | 불필요 |
| D177 | 링크 범례를 'F1 들어옴 (DU → CU)'·'N2 나감 (CU → AMF)'처럼(링크 × CU 기준 방향), NIC 이름(`ens5`·`br-…`)은 범례에서 빼고 툴팁에만 | 사용자 질문(11/13 '밑에 4개·괄호가 무슨 뜻인지'). 4개 = 링크 2(F1·N2) × 방향 2, 괄호 = NIC 이름이라 알아보기 어려웠다 | 불필요 |
| D178 | '부하와 함께' 범례를 **오른쪽 표**(이름·평균·최대), 계열 이름은 괄호 없이 'CPU 사용률'·'RRC 연결 시도'(셀 합·3초는 설명으로) | 아래 목록이면 Grafana가 오른쪽 축 계열을 따로 떼어 두고, 아래 표는 이름과 값 사이가 너무 벌어졌다. 오른쪽 목록도 해 봤지만 값이 줄마다 어긋나 표로 되돌림(사용자 11/13). 표 모드는 오른쪽 축 계열에 '(right y-axis)'를 붙이는데 끌 설정이 없고, 범례 글자 크기도 Grafana에 설정이 없다 | 불필요 |
| D179 | '공격별 경보 수'는 **가로 막대 그대로** | 세로 막대(이름 -45°)로 바꿔 봤다가 사용자가 되돌림(11/13) | 불필요 |

### 확인 결과

| 확인 | 결과 |
|---|---|
| `pytest` | 265 passed, 3 skipped(로컬 Grafana·InfluxDB가 꺼져 있어 건너뛴 것 — 아래 임시 스택에서 따로 통과) |
| 실제 InfluxDB 통합 테스트 | 임시 InfluxDB 2.7.12(아래)로 `test_influx_integration.py` 1 passed — 샘플 32개 + 예시 4종(`overhead` 포함)을 넣어 점 수 = 줄 수(덮어쓰기·타입 충돌 없음), `overhead_link` 포함 |
| 대시보드 쿼리 | 임시 Grafana 12.4.13에서 관제 23개·성능 20개 쿼리 오류 0(최종). CU 자원 쿼리가 30분 가짜 데이터에서 시계열 580행씩, 트래픽·패킷 각 4계열(f1·n2 들어옴·나감) |
| 화면 | Edge headless로 성능 대시보드 캡처: 공격 구간 두 곳에서 CPU 사용률·CPU 내역·메모리·F1 SCTP 바이트/초·패킷/초·RRC 연결 시도가 함께 오르고, 분석 엔진이 멈춘 1분은 선이 끊김. 노드 칸의 열 순서를 고정(organize)함 |
| 탐지 쪽 실제 overhead 샘플 30줄 | 스키마 30/30 통과, 구간 3,000 ms·3초 경계·빈틈 없음, 세션 하나·`node_id` cu·링크 2칸(f1 `ens5`, n2 `br-…`), `null`·빈 객체 없음. 계측기 코어 수가 정수 0(16줄)과 실수(14줄)로 섞여 옴 → InfluxDB에는 실수로(D165가 필요했음). 값: CPU 2.1~4.6 %, 메모리 4.95 GiB / 7.59 GiB, 계측기 RSS 310 MiB, F1 시그널링 최대 42 패킷/초. `/ingest`로 30줄 저장·다시 보내면 30줄 중복, 실제 InfluxDB(임시)에 타입 충돌 없음, 성능 대시보드 CU 자원 줄에 표시 |
| 경보 목록 정렬 버그 | 임시 스택(경보 2개: 해제된 `L3-01-V`, 상태 불명 `L3-24`)에서 dev 판 쿼리는 1개만, 고친 판은 2개 모두 — 단계를 나눠 실행해 `map` 뒤 `sort`에서 줄이 빠지는 것을 확인 |
| 사용자 화면 확인 | 임시 Grafana(`localhost:3002`)를 띄워 사용자가 직접 봄 → 위 D173~D178 반영 뒤 다시 캡처 |
| CI용 단계 | 바꾼 `ci.yml` YAML 문법 확인. 실제 실행은 push 뒤 |

확인하지 못한 것: 탐지 쪽 실제 `overhead` 출력(샘플 요청함), AWS 배포 뒤 실측. 경보가 하나뿐일 때 "경보 길이 분포" 히스토그램이 비는 것은 Grafana 동작이라 그대로 둠(경보가 여럿이면 표시됨, M10 확인).

### 환경 메모

- **로컬 데이터를 건드리지 않고 대시보드를 확인하는 법**: 임시 네트워크에 InfluxDB(`DOCKER_INFLUXDB_INIT_MODE=setup`, 별칭 `influxdb`)와 Grafana(저장소 provisioning 마운트, 익명 Admin)를 따로 띄우고, `Collector` + `InfluxWriter`로 가짜 데이터를 `handle_request`에 넣는다. 통합 테스트는 `INFLUX_URL`·`INFLUX_TOKEN`·`INFLUX_ORG`·`INFLUX_BUCKET`을 임시 값으로 주고 실행(`.env`보다 먼저 읽힌다). 끝나면 컨테이너·네트워크를 지운다.

### 남은 일

- [x] PR(`feat/dashboard-M11` → `dev`, #40) → `main` 배포(#41, 2026-11-13)
- [x] 탐지 쪽 `overhead` 실제 출력 샘플(11/13, 30줄 = 90초) → `tests/data/overhead/overhead-sample-3s-30.jsonl`에 넣고 스키마·`/ingest`·실제 InfluxDB·대시보드로 확인(T7 ②)
- [ ] (있으면) 계측기 기동 직후·링크 값을 못 읽은 구간이 든 샘플로 T7 ①③ 확인
- [ ] 탐지 쪽 확인: 오버헤드 전용 전송기의 `X-Env`·주소·인증서·헤더·응답 처리가 기존 전송기와 같은지(D171)
- [ ] AWS에서 탐지 쪽이 계측기를 켠 뒤 CU 자원 줄 확인(데이터 출처 AWS)
- [ ] 노드가 늘면(예: DU) 노드 변수 추가
- [ ] 배포 뒤 AWS 관제 경보 목록에 해제된 경보(UE 컨텍스트 고갈 등)가 다시 보이는지(D176)

---

## M12 — Slack 알림: Grafana Alerting (2026-11-13, 브랜치 `feat/dashboard-M12`)

목표: AWS(p4) 실측에서 공격 경보가 나면 Slack으로 알리고, 실험 중 데이터가 끊기면 알린다. 사용자 결정(11/13): ① Webhook은 사용자가 만들어 서버 `.env`에 ② 데이터 출처는 AWS만(On-Premise는 받기 시작하면) ③ 공격 경보 발생 + 해제(이상 유형·판정 보류·high 오름은 알리지 않음) ④ 메시지 = 공격 이름·셀·심각도·시작 시각 + 경보 상세 링크 ⑤ 수집 멈춤 알림도.

### 한 일

| 파일 | 변경 |
|---|---|
| `grafana/build.py` | `alerting()` — 알림 provisioning을 만든다: 규칙 2개(공격 경보, 수집 멈춤), Slack 연락처 2개(수집 멈춤은 해제 알림 없음), 알림 정책(경보 하나 = 알림 하나), 메시지 템플릿. 공격 경보 상태는 대시보드와 같은 `alert_summary`, 공격 이름은 같은 짧은 이름. `--check`가 알림 파일도 본다 |
| `grafana/provisioning/alerting/portran.json` (새 파일) | 위 생성 결과 |
| `docker-compose.yml` · `.env.example` | Grafana에 `SLACK_WEBHOOK_URL`(비어 있으면 아무 데도 안 가는 주소)·`GF_SERVER_ROOT_URL`(= `GRAFANA_ROOT_URL`) |
| `tests/test_dashboards.py` | 알림 provisioning 구성 검사(AWS만, 공격만, 연락처·정책, 템플릿에 `$` 없음, `.Values`는 `with` 안), 알림 쿼리를 Grafana에서 실행(Grafana 있을 때) |
| 문서 | CLAUDE.md 4·9.3·13절, README "Slack 알림", `docs/deploy.md` 11절(Webhook 만들기·서버 `.env`·시험) |
| `README.md` 맨 위 그림 | ASCII 흐름도를 **Mermaid 그림**으로(GitHub에서 그려짐): 테스트베드(분석 엔진·탐지 엔진·전송기·오버헤드 전송기) → 대시보드 서버(nginx → collector → InfluxDB → Grafana, 녹화·replay) → Slack·팀원 브라우저, On-Premise는 점선(나중). 사용자 요청(11/13). Edge headless로 mermaid 10.9.1을 그려 미리 확인 |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D180 | 알림은 **Grafana Alerting**(provisioning) — collector가 직접 보내지 않는다 | 새 코드가 거의 없고, 발생·해제 상태·중복 묶기·재전송을 Grafana가 한다. 시간 기반 알림(수집 멈춤)도 같은 방식. collector에 외부 연결을 만들지 않는다 | 불필요 |
| D181 | 공격 경보 규칙: 6시간 범위의 AWS 공격 경보마다 한 계열, 값 = 열림 1(medium)·2(high) / 해제 0 / 강제 종료 -1, 0보다 크면 울림. 10초마다, 바로(`for` 0초) | 값에 끝난 모양을 담아 해제 알림에 '해제·강제 종료'를 적는다(라벨에 넣으면 상태가 바뀔 때 다른 알림이 된다). 6시간 안에 끝이 안 오면 범위를 벗어나며 '끝 소식 없음'으로 끝난다. 상태 불명(15초·90초 무소식)으로 끝내지 않는 건, 근거가 잠깐 늦을 때 발생·끝이 번갈아 와 Slack이 시끄러워지지 않게 | 불필요 |
| D182 | 수집 멈춤: 마지막 레코드(상시 KPM2 `n`·오버헤드·경보·근거·hello) 뒤 5분 넘으면 울림. 최근 1시간에 아무것도 없으면 조회 결과 없음 = 정상(테스트베드를 끈 것). 해제 알림은 보내지 않음 | 실험 중 끊김만 알리고, 끈 테스트베드로 매번 울리거나 '다시 들어옴'·'1시간 지남'을 해제처럼 알리지 않게. 일부러 멈춘 실험에도 한 번은 온다(메시지에 적음) | 불필요 |
| D183 | 조회 실패는 마지막 상태 유지(`execErrState: KeepLast`), 결과 없음은 정상(`noDataState: OK`), 같은 알림 다시 보내기 24시간 | InfluxDB가 잠깐 죽거나 오래 열린 경보로 Slack에 오류·반복 알림이 쏟아지지 않게 | 불필요 |
| D184 | Webhook 주소는 `.env` → Grafana 환경변수 → provisioning `${SLACK_WEBHOOK_URL}`. 비어 있으면 `http://127.0.0.1:9/…`(연결 거부)로 | 비밀 값을 저장소에 두지 않는다. 비어 있어도 Grafana가 뜨고(잘못된 연락처로 provisioning이 실패하지 않게) Slack 서버로도 나가지 않는다 | 불필요 |
| D185 | 메시지 템플릿·주석에 `$`를 쓰지 않는다(`.CommonLabels`·`.CommonAnnotations`·`.ExternalURL`), `.Values`는 `{{ with .Values }}` 안에서만 | provisioning 파일은 환경변수를 바꿔 넣는다. 조회 결과가 없을 때(NoData) `.Values.B`를 꺼내면 템플릿이 깨졌다(임시 Grafana에서 확인) | 불필요 |
| D186 | 관제 "근거 KPM1 — UE별 메시지 흐름"은 UE마다 마지막 메시지 1초 뒤(`TIMELINE_END_S`)에 빈 값을 끼워 거기서 끝낸다(빈 값은 투명) | 상태 타임라인은 값을 다음 값이 올 때까지 늘여 그려서, 마지막 메시지(예: `UEContextReleaseComplete`)가 화면 끝(지금)까지 24분짜리 상태처럼 보였다(사용자 AWS 화면 11/13, Blind DoS 경보 해제 뒤). 임시 Grafana에서 샘플 S24로 마지막 메시지 뒤가 빈칸인 것 확인 | 불필요 |
| D187 | Grafana에 `SLACK_WEBHOOK_URL`이 비어서 가지 않게 compose 기본값을 지키는 테스트 | 값이 비면 Slack 연락처 검사(`recipient must be specified`)에 걸려 **Grafana가 아예 뜨지 않는다**(11/13 임시 Grafana에서 확인). compose는 비어 있을 때 `http://127.0.0.1:9/…`를 넘겨 괜찮지만, 이 기본값이 빠지면 배포 헬스 체크가 실패한다 | 불필요 |
| D188 | 관제·성능의 모든 표는 `organize` 변환(`column_order()`)으로 열 순서를 박아 둔다(판정 요약: 룰·공격·종류·셀·심각도·마지막 이벤트·모드·갈래·세션) | Flux `map`이 만든 열은 순서가 정해져 있지 않아, 판정 요약 같은 표의 열이 새로고침마다 뒤섞였다(사용자 AWS 화면 11/13). 모든 표 패널에 `indexByName`이 있는지 테스트로 지킨다. 임시 Grafana에서 샘플 S24를 두 번 띄워 순서가 같은 것 확인 | 불필요 |
| D189 | 관제 대시보드 위쪽 줄 간단히: 주석(경보 구간·데이터 없음·칸 일부 없음·세션 시작·DU·CU 재시작·근거 데이터 없음)은 늘 켜 두고 토글을 숨기고(`hide: true`), 경보 고르기 칸(`alert_id`)도 숨긴다(`hide: 2`) | 사용자 요청(11/16, "파란 버튼들 다 없애자", "경보 고르는 것도 없애자 어차피 아래에 있으니까"). 그래프 위 표시는 그대로 보인다. 경보는 경보 목록 행 링크(`var-alert_id`)·Slack 링크로 고르고, 처음 열면 가장 최근 경보, 고른 경보는 '경보 상세 — …' 행 제목에 보인다. 테스트가 주석·변수 숨김을 본다 | 불필요 |
| D190 | 관제 대시보드 맨 위 '요약 — 지금'(열린 경보·최고 심각도·수집 상태·세션) 줄을 없애고, 성능 대시보드의 '탐지 결과' 줄을 그 자리로 옮긴다(`add_detection_rows`, 성능에서는 뺌). 탐지 결과의 '경보 수 — 종류별' stat도 없앤다. 경보 목록의 '룰별 경보 수' 막대를 없애고 경보 표를 24칸으로. 성능 대시보드의 '경보·입력 품질' 줄(경보가 어떻게 끝났나·근거 손실·gap·칸 채움·일부만 측정된 지표)도 없앤다 — 성능은 CU 자원만 | 사용자 요청(11/16). 요약 줄의 상태 불명 수가 최근 7일 기준이라 목록·그래프(고른 범위)와 어긋나 헷갈렸다. 탐지 결과는 고른 시간 범위 기준이라 관제의 다른 줄과 기준이 같다. 룰별 경보 수는 맨 위 공격별 경보 수와 겹친다. 수집이 멈춘 것은 Slack '수집 멈춤' 알림(M12)이 알린다 | 불필요 |
| D191 | 관제 줄·패널 제목을 짧게 한다 — 줄: '탐지 결과', 'KPM'(상시 KPM2), '경보 목록'. 패널: 'RRC 연결 시도 · 성공 · 무응답', 'UE 컨텍스트 · 연결 UE 수', '근거 KPM'(100 ms 근거 KPM2), 'UE_EVENT — UE별 메시지 흐름', 'UE_EVENT — 메시지 흐름 상세'(근거 `ue_evt`), '경보 길이 분포'. 성능 대시보드 줄 'Overhead'(CU 자원 — 수집 오버헤드), 패널 'CPU 사용률 · RRC 연결 시도'(전 '부하와 함께'). 공격별 경보 결과 열 'high 도달'(전 'high까지' — 뜻이 헷갈림). 패널 제목의 괄호 설명을 뺀다 — CPU 사용률 · CPU 내역 · 메모리 사용량 · 메모리 내역 · F1·N2 SCTP 트래픽 · F1·N2 SCTP 패킷 | 사용자 요청(11/16). 빠진 설명(셀·3초 묶음·TeleRAN Table II·셀 한도 96·행을 누르면 경보 상세가 바뀜)은 패널 설명(ⓘ)에 둔다 | 불필요 |
| D192 | 성능 Overhead '노드' 칸은 node_id가 `cu`로 끝나면(`p4-cu`·`cu`) 'CU'로 보인다(값 매핑, 정규식 `^(.+-)?(cu|CU)$`). 저장값은 그대로 | 사용자 요청(11/16). 11/13에 `cu`로 통일하기로 했지만 AWS 탐지 쪽은 `p4-cu`로 보낸다. 표시만 바꾸고 데이터는 건드리지 않는다. 로컬 Grafana에서 `p4-cu` 오버헤드로 'CU' 표시 확인 | 탐지 쪽에 `p4-cu` 그대로 써도 되는지 알릴 것(대시보드는 둘 다 됨) |
| D193 | 관제 경보 상세: 판정 요약의 '갈래'(`branch`) 열과 걸린 UE의 '전제'(`conditions`) 열을 없애고, 걸린 UE '불확실'(`uncertain`)은 '관측 오류'로 | 사용자 요청(11/16). 갈래는 L3-21·L3-14·AN-02, 전제는 L3-14에만 있어 대부분 빈칸이었다. 값은 InfluxDB·원본 녹화에 그대로 있고, 경보 전체의 전제는 판정 근거 값 표의 '공격자 행동 전제' 줄에 남아 있다 | 불필요 |
| D194 | 성능 Overhead의 노드별 시간 그래프(CPU 사용률·CPU 내역·메모리 사용량·메모리 내역)는 node_id가 cu로 끝나면(`cu`·`p4-cu`, 대소문자 무시) 한 노드 'CU'로 묶어 계열을 만든다(`NODE_FLUX`) | 사용자 AWS 화면(11/16, 최근 24시간): 범례가 '분석 엔진·그 밖·코어 수', '사용 중·전체'로 두 번씩 나왔다. AWS node_id가 11/15엔 `cu`, 11/16엔 `p4-cu`로 달라 노드별로 계열이 둘이 됐고 이름이 같았다(D192는 노드 칸 표시만 바꿨음). 로컬에서 `cu`·`p4-cu`를 섞어 넣고 범례가 한 벌만 나오는 것 확인(확인용 데이터는 지움) | 불필요 |
| D195 | 대시보드 패널·변수 설명(ⓘ)에는 명세 참조(`27_ §5.1` 같은 절 번호)를 넣지 않는다. 근거 절 번호는 `build.py` 주석·`docs/dashboard-design.md`에만 | 사용자 요청(11/16, '달러사인 같은 이상한 문구'). 화면을 보는 팀원·발표 청중에게는 뜻 없는 기호였다. 관제 설명 11곳에서 뺐고 테스트가 지킨다 | 불필요 |

### 확인 결과

| 확인 | 결과 |
|---|---|
| `pytest` | 266 passed, 4 skipped(로컬 Grafana·InfluxDB가 필요한 테스트 — 알림 쿼리는 아래 임시 Grafana에서 직접 실행해 오류 0) |
| 임시 스택에서 실제 알림 | 임시 InfluxDB·Grafana 12.4.13 + 가짜 Slack 수신기(같은 네트워크의 작은 HTTP 서버)로: ① AWS에 6분 전 상시 KPM2 한 줄 → "⚠️ 수집 멈춤 … 마지막 수신 370초 전" ② 샘플 T10 경보 raise → "🚨 UE 컨텍스트 고갈 · 셀 1 · medium · 시작 2026-11-13 17:23:18 + 경보 상세 링크", 수집 멈춤은 조용히 끝남 ③ T10 clear → "✅ … 해제" ④ 샘플 T07(`end` session_reset) → "✅ … 강제 종료". 환경변수 Webhook 주소가 들어가고 JSON provisioning이 읽힘 |
| 고친 것 | 조회 결과 없을 때 템플릿 오류(→ `with`), 링크의 `//`(→ `ExternalURL`은 `/`로 끝남) |

확인하지 못한 것: 실제 Slack 채널로 온 메시지(Webhook은 사용자가 만들어 서버에 넣음), AWS 배포 뒤 실측 경보.

### 환경 메모

- **Slack 알림을 놓치지 않으려면**: Webhook 메시지는 멘션이 아니라서 Slack 기본 설정으로는 푸시가 오지 않는다. 각자 알림 채널 → 알림 설정 → **모든 새 메시지**. 이메일로는 오지 않는다(Slack 이메일 알림은 멘션·DM만). 이메일이 필요하면 ① 메시지에 `@channel` 멘션 ② Grafana 이메일 연락처(SMTP 설정 필요) 가운데 정한다.
- **Grafana가 안 뜰 때(로그에 `failed to validate integration "PortRAN Slack" … recipient must be specified`)**: Grafana에 `SLACK_WEBHOOK_URL`이 비어서 갔다. compose로 띄우면 기본값이 들어가니, compose 밖에서 Grafana를 띄울 때는 이 값을 꼭 준다(D187).
- **알림이 안 올 때**: ① 서버 `.env`를 고친 뒤 `docker compose up -d grafana`를 했는지(`.env`만 바꾸면 CD가 모른다) ② Contact points의 Test ③ 데이터 출처가 AWS(p4)인지(재생·샘플은 알리지 않음) ④ Grafana → Alerting → Alert rules에서 규칙 상태·오류.

### 남은 일

- [x] PR(`feat/dashboard-M12` → `dev`, #42) → `main` 배포(#43, 2026-11-13)
- [x] (사용자) Slack 워크스페이스 `portran`, 알림 채널, Slack 앱 `PortRAN-Alarm`의 Incoming Webhook 만듦(11/13). 앱은 api.slack.com/apps → Create New App → **Pick features**(화면이 바뀌어 'From scratch'가 둘로 나뉨) → Incoming Webhooks On → Add New Webhook
- [ ] 서버 `.env`에 `SLACK_WEBHOOK_URL`·`GRAFANA_ROOT_URL=http://3.39.170.31:3000` → `docker compose up -d grafana` → Contact points → `PortRAN Slack` → Test로 채널에 시험 메시지가 오는지(`docs/deploy.md` 11절) — 사용자 확인 전
- [ ] 다음 AWS 공격 실험 때 실제 알림(🚨·✅·⚠️)이 오는지
- [ ] 팀원 초대·채널 알림 설정('모든 새 메시지') — 각자
- [ ] On-Premise를 받기 시작하면 알림 출처에 `lab` 더하기

---

## Claude Code 작업 기록 hook · 역할 분리 워크플로우 (2026-11-18, 브랜치 `feat/agent-workflow` → 오후 `docs/lean-agent-workflow`)

목표: ① AI 코딩 에이전트의 프롬프트와 실행 로그를 hook으로 남겨 작업 과정을 재현하고 오류 원인을 거슬러 찾는다. ② Researcher·Planner·Reviewer로 역할을 나눠, 구현 결과를 별도 Reviewer가 독립적으로 검증한다. 사람용 설명은 `docs/agent-workflow.md`.

### 한 일

| 파일 | 변경 |
|---|---|
| `.claude/settings.json` | hook 등록: 12개 이벤트(SessionStart·UserPromptSubmit·Pre/PostToolUse·PostToolUseFailure·PermissionDenied·SubagentStart/Stop·Stop·StopFailure·PreCompact·SessionEnd) → `agent_log.py`, PreToolUse `Bash` → `readonly_guard.py` |
| `.claude/hooks/agent_log.py` | 작업 기록기(hook 입력 → `logs/agent/<세션 ID>.jsonl`, 비밀 값 가림, 긴 문자열 앞뒤만, 늘 exit 0·stdout 없음)이자 보기 도구(`list`·`show`·`errors`). 표준 라이브러리만 |
| `.claude/hooks/readonly_guard.py` | researcher·planner·reviewer의 Bash 가운데 파일·git 상태를 바꾸는 명령을 거부하고 `GuardDenied`로 기록 |
| `.claude/agents/researcher.md` · `planner.md` · `reviewer.md` | 역할별 서브에이전트: 도구 제한(Edit·Write 없음), 규칙, 보고 형식. Reviewer는 완료 조건 표·문제(심각도·파일:줄·실패 시나리오·재현 명령)·판정 |
| `tests/test_agent_log.py` | 296개: 비밀 값 가림 33가지(짧은 `.env` 값·한글 조사·따옴표·이스케이프된 따옴표·닫지 않은 따옴표, 코드는 남기기 포함)·큰 입력 속도·깊은 중첩, 기록 형식, hook이 실패·출력하지 않음, 보기 명령(결과 없는 호출 포함), 가드 허용 58·거부 87가지(거부는 역할 2개씩)·반복 입력 속도, 설정·에이전트 정의 |
| `CLAUDE.md` | 4절 디렉터리, 12절 10항(역할 분리 흐름), 11항(작업 기록) |
| `docs/agent-workflow.md` | 흐름도, 역할, 독립성 장치, 기록 형식·보는 법·오류 추적 순서, 설정·끄기·한계 |
| `README.md` | "AI 작업 흐름 (Claude Code)", 문제 해결(hook error), 디렉터리 |
| `.gitignore` · `.dockerignore` | `logs/`·`.claude/settings.local.json` git 제외, 이미지에서 `.claude`·`logs` 제외 |

### 결정 사항

| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D196 | 기록 위치 `logs/agent/<세션 ID>.jsonl`(저장소 안, git·Docker 제외), 이벤트 하나 = 한 줄. 결과 줄에는 입력을 다시 쓰지 않고 `tool_use_id`로 짝짓는다 | 세션별로 다시 보기 쉽다. Claude Code 원본 대화(`transcript_path`)는 30일 뒤 지워지므로 오래 남을 기록이 따로 필요하다 | 불필요 |
| D197 | 쓰기 전에 비밀 값을 가리고(`.env` 비밀 값 3자 이상 — 6자 미만은 ASCII 낱말 단위라 한글 조사가 붙어도 가림, 토큰·비밀번호 KEY=VALUE, `--password`·`curl -u`, Webhook, 개인 키, 키 형식, Authorization, 비밀 파일 내용), 긴 문자열은 4000자(앞 40%·뒤 60%)만. 코드(`os.environ.get(…)`)·`${…}` 참조는 남긴다 | 이 저장소는 `.env`·인증서·Slack Webhook을 다룬다. 로컬 관리자 비밀번호가 4자라 길이 문턱을 두면 README의 `reset-admin-password` 명령에서 새어 나간다(Reviewer 1차 지적) — 짧은 값은 낱말 단위로 가려 다른 글자를 지우지 않는다. 오류는 보통 출력 끝에 있다 | 불필요 |
| D198 | hook을 프로젝트 설정(`.claude/settings.json`)으로 커밋 | 이 저장소에서 Claude Code를 쓰는 사람 모두에게 같은 기록·가드가 적용된다. 기록은 각자 PC에만 남는다 | **필요 — 이 저장소에서 Claude Code를 쓰는 팀원에게 알림** (끄는 법: `.claude/settings.local.json`에 `disableAllHooks`) |
| D199 | 읽기 전용 역할의 Bash를 PreToolUse hook으로 거부. git은 전역 옵션(`-C`·`-c`)을 건너뛰고 하위 명령·인자로 판정(`stash list`·`tag -l`·`branch -a`는 허용). `bash -c`·`eval`·`docker exec` 안의 명령도 다시 검사. `pytest`·`build.py --check`·로컬 확인 요청(GET, `/ingest` POST)은 허용, curl DELETE·PUT·PATCH는 거부 | 도구 목록에서 Edit·Write를 빼도 Bash로는 바꿀 수 있고, 프롬프트 규칙만으로는 지켜지는지 알 수 없다. 서브에이전트 안의 호출에는 hook 입력에 `agent_type`이 실려 와 역할별로 가를 수 있다(실제 세션에서 확인). 검증에 필요한 명령은 막지 않는다 | 불필요 |
| D200 | Reviewer에게 요구 원문·완료 조건·비교 기준만 넘기고, 다시 검증할 때는 새 Reviewer에 지난 문제 목록만 더 넘긴다 | 구현자의 설명·자기 평가를 받으면 그 시각으로 검증하게 된다 | 불필요 |
| D201 | (**D206에서 1회로 바꿈**) Reviewer 검증은 **최대 3차**. 3차에서도 수정 필요면 멈추고 사용자에게 묻는다. 마지막 검증 뒤에 고친 것은 '검증받지 않음'으로 적는다 | 사용자 결정(11/18). 이번 작업에서 통과 뒤 낮음 문제를 고치고 다시 검증하느라 4차까지 갔다 | 불필요 |
| D206 | **작업 크기별 단계 · Reviewer 검증 1회** (CLAUDE.md 12절 10항 고침, D201의 최대 3차를 바꿈): 오타·문서 = 구현만 / 작은 화면·문구·설정 = 구현 → 검증 / 원인 모르는 문제 = 좁은 조사(질문 목록) → 메인이 계획(사용자 승인) → 구현 → 검증 / 마일스톤·스키마·여러 파일 설계 = 조사 → `planner` → 구현 → 검증. 검증은 1회 — 수정 필요면 고치고 '검증 안 받음'으로 적음. 역할 정의에 질문 범위만·보고 짧게·외부 서버 측정 1회·논문 PDF는 필요할 때만을 더함. Researcher 모델은 그대로(Opus) | 사용자 결정(11/18 "하네스 도입 전보다 느려졌고 토큰도 늘었다", "검증 한번만"). 11/18 대시보드 수정 세션 실측은 아래 확인 결과 '하네스 비용' | 불필요 |
| D207 | **작업 기록·역할 분리 켬·끔**: 각자 `.claude/settings.local.json`(git 제외)의 `env`에 `PORTRAN_AGENT_LOG`·`PORTRAN_ROLE_WORKFLOW` = `off`. 기본 켬. 기록 끔 = `agent_log.py`가 아무것도 안 씀(가드는 막기만 하고 `GuardDenied`도 안 남김). 역할 분리 끔 = SessionStart hook이 Claude 컨텍스트에 "[PortRAN 설정] 역할 분리 워크플로우가 꺼져 있다"를 넣고, CLAUDE.md 12절 10항이 서브에이전트 없이 메인이 하라고 정함. hook이 env를 못 받아도 같게 파일을 직접 읽음. 읽기 전용 가드는 끄지 않음(`disableAllHooks`는 가드까지 꺼서 권하지 않음) | 사용자 요청(11/18) — 두 기능을 켜고 끌 수 있게. 가드는 서브에이전트에만 작동해 끌 이유가 없다 | 불필요 |
| D208 | **역할 분리 기본 꺼짐** — 사용자가 "역할 분리 켜고"라고 요청하거나 `PORTRAN_ROLE_WORKFLOW=on`일 때만 서브에이전트를 쓴다. 기본은 메인 에이전트 하나가 조사·계획·구현하고 테스트로 확인(사용자 확인 규칙은 그대로). SessionStart 알림은 기본값과 다른 설정만(역할 분리 켜짐, 작업 기록 꺼짐). 켬 값 on·1·true·yes·켬·켜짐, 알 수 없는 값은 기본값 | 사용자 결정(11/18) — 하네스가 느려서 단일 에이전트를 기본으로 | 불필요 |

### 확인 결과

| 확인 | 결과 |
|---|---|
| `pytest` | 572 passed, 4 skipped(로컬 Grafana·InfluxDB가 필요한 테스트 — 기존과 같음). 새 `tests/test_agent_log.py` 296 passed |
| 가짜 hook 입력 | SessionStart·프롬프트·Bash 성공·`.env` 읽기·Bash 실패·Stop·JSON 아님 10가지: 모두 exit 0, stdout 없음. 토큰·Webhook·Authorization·`.env` 값이 `***` |
| 실제 세션 1 | `dashboard/`에서 `claude -p`(haiku)로 researcher 서브에이전트 1회 + 실패하는 `ls` 1회: 15줄 기록. 서브에이전트 안 호출에 `agent_type`·`agent_id`, 결과에 `duration_ms`·`prompt_id`가 실려 옴. 실패는 `PostToolUseFailure`. `errors`가 실패 명령·프롬프트·오류를 보임. `_hook_errors.log` 없음 |
| 실제 세션 2 | reviewer 서브에이전트에게 `touch /tmp/guard_probe_xyz`를 시킴 → 실행 전에 거부(파일 안 생김), 기록에 `GuardDenied`, `errors`에 나옴 |
| 가드 판정 | (1차 수정 뒤) 허용 30가지(`git diff`, `git -C … log`, `git stash list`, `tag -l`, `pytest … 2>&1`, `> /dev/stderr`, heredoc 안 `>` 등)·거부 35가지(`rm`, 앞 공백 ` rm`, `then rm`, 백틱·`$( )`, `env`·`time`·`timeout` 뒤, `> 파일`, `sed -i`, `git -C . commit`, `git stash`, 새 브랜치·태그, `curl -o`, `wget`, `grafana cli admin`, `influx write`, `--check` 없는 `build.py` 등) — 테스트에 고정 |
| Python 3.10 | `ast.parse(feature_version=(3, 10))` 통과(로컬에 3.10 없음 — CI matrix가 실제로 돌린다) |
| Reviewer 1차 | **수정 필요**(실제 `reviewer` 서브에이전트, `claude -p`). 완료 조건 10개 중 8개 ✅, 4(비밀 값)·10(문서 일치) ❌. 중간 3: 4자 `.env` 비밀번호와 `PASSWORD=` 꼴이 안 가려짐, 가드 우회(앞 공백·`git -C`·`then rm`·백틱 등). 낮음 7: `git stash list` 등 오탐, 따옴표 안 공백 값, 입력의 `ts`·`event`가 덮어씀, 서로게이트 쓰기 오류, 코드 가림, 설정 테스트 9/12, 열린 항목 누락. 검증 중 Reviewer의 `git stash list`가 가드에 실제로 막힘 → **모두 고침**(D197·D199, Q25, 테스트 72 → 158) |
| Reviewer 2차 | **수정 필요**(새 Reviewer, 1차 문제 목록만 더 받음). 1차 문제 10건 중 9건 고쳐짐 확인, 조건 4만 ❌. 중간 1: 짧은 `.env` 값의 낱말 경계가 유니코드 `\w`라 한글 조사가 붙으면(`<값>로`) 안 가려짐. 낮음 7: `bash -c "rm …"`·`eval`·`{ rm; }`·`/bin/rm`·`nice -n 10 rm`·`docker exec … rm`·`docker volume rm`·`git bisect`·`cd grafana && python build.py` 통과, curl 허용 범위 문서 불일치, 따옴표 붙은 `--password "…"`·스킴 없는 Webhook, 결과 없는(권한 거부) 호출이 `errors`에 안 나옴, 문서의 개수 불일치·중복 테스트 → **모두 고침**(경계 ASCII, 안쪽 명령 재검사, 테스트 158 → 225) |
| Reviewer 3차 | **통과**(새 Reviewer, 2차 문제 목록만 더 받음). 완료 조건 10개 모두 ✅, 2차 문제 7건 해결 확인(8번 '흔한 낱말 오가림'은 한계로 문서화). 낮음 4: 이스케이프된 따옴표(`\"…\"`) 안 값이 샘, 감싸는 명령 반복(`nice -n 1 ` ×22)에서 정규식이 지수적으로 느려져 hook 제한 시간을 넘길 수 있음, `curl -X "DELETE"`·`curl -sSo x`·`git reflog expire`·`unlink`·`npm i`·`build.py --checkout` 통과, 거부 이유의 줄바꿈·`> >(cat)` 오탐 → 통과였지만 **모두 고침**(값 패턴, 해석이 하나뿐인 정규식 — 500번 반복도 10 ms 미만, 테스트 225 → 268) |
| Reviewer 4차 (마지막) | **통과**(새 Reviewer, 3차 문제 목록만 더 받음 — 사용자가 허락한 마지막 검증, D201). 완료 조건 10개 모두 충족, 3차 낮음 4건 해결 확인, 가드 거부 대상 112가지 누락 0, 감싸는 명령 2000번 반복도 35 ms. 중간 1: build.py 규칙이 실행이 아니라 이름만 나와도 막아 `git diff -- grafana/build.py`·`git blame`·`grep … grafana/build.py` 같은 읽기가 거부됨(researcher.md 예시 명령 포함). 낮음 6: 문자열 속 `bash -c`·`curl -X DELETE` 글자로도 막힘, `git grep -o` 오탐, `.env`에 없는 값의 드문 꼴(두 번 이스케이프·`Authorization: Token "v"`·닫지 않은 따옴표·값 속 이스케이프·`$`로 시작), 80 KB 반복 명령 9초, 깊이 1000 넘는 중첩은 기록 안 됨, `pdftotext <파일>`이 저장소에 파일을 만듦 |
| 4차 뒤 수정 (**Reviewer 검증 안 받음**, D201) | build.py는 실행할 때만 막음, `bash -c`·`eval`·curl 메서드는 명령 자리에서만 봄(heredoc 본문 제외), git `-o`를 `--output`으로 보지 않음, `Authorization` 따옴표 값·닫지 않은 따옴표·값 속 이스케이프 가림, 30,000자 넘는 명령은 판정 없이 거부(28 KB 1.1초), 깊은 중첩은 내용 없이 이벤트만 기록, `pdftotext`는 `<파일> -`만 허용·`pdftoppm` 거부(researcher.md도 고침). 남긴 한계: 두 번 이스케이프한 따옴표·`$`로 시작하는 값·소문자 키(`docs/agent-workflow.md`에 적음). 확인은 테스트로만: 268 → 296 passed, 전체 572 passed |


**오후 추가 (브랜치 `docs/lean-agent-workflow`)** — 한 일: CLAUDE.md 12절 10항(작업 크기별 단계 표, Reviewer 검증 1회, 역할 분리 끔일 때 동작)·11항(기록 끔), `.claude/agents/`(researcher: 질문 목록에만·보고 짧게·논문 PDF는 필요할 때만·외부 측정 1회 / planner: 마일스톤에만 / reviewer: 1회, 측정 반복 안 함), `.claude/hooks/agent_log.py`(켬·끔 `switch_on`, SessionStart에서 꺼진 설정 알림)·`readonly_guard.py`(기록 끔이면 막기만), `tests/test_agent_log.py` +4, `docs/agent-workflow.md` 0·4절, README. Reviewer 1회 통과(완료 조건 8개 충족) — 지적한 문서 4건(Q25 안내, 작업 흐름 문서의 stdout 설명, 이 절 제목·한 일, 논문 비용을 미정 표에)은 그 뒤 고침(**Reviewer 검증 안 받음**, D206).

**하네스 비용과 개선 (11/18 오후, D206)** — Claude Code 세션 기록(`~/.claude/projects/…/<세션>.jsonl`, 서브에이전트는 `<세션>/subagents/`)의 응답별 `usage`로 셈.

| 측정 | 결과 |
|---|---|
| 하네스 전 세션 (11/09~11/16 M8~M12 등 4개) | 서브에이전트 0~2개. 메인 응답당 입력(컨텍스트) 중앙값 219k~492k |
| 11/18 대시보드 수정 세션 (하네스 적용) | 메인 55.1M 토큰(캐시 읽기 54.4M, 출력 244k), 응답당 입력 중앙값 366k — **메인은 전과 비슷하거나 작다**. 서브에이전트 5개 **20.0M 토큰(메인의 +36%), 출력 252k, 기다린 시간 약 50분** |
| 단계별 | 조사 16.6분·입력 9.82M·출력 75k / 계획 16.3분·4.17M·**출력 110k(메인 세션 전체 출력의 45%)** / 검증 1차 12.6분·3.59M·47k(같은 AWS 측정 5번 반복) / 추가 조사 3.9분·1.82M·19k / 검증 2차(중단) 0.6분 |
| 원인 | ① 단계가 차례로 돌아 메인이 기다림 ② 서브에이전트마다 CLAUDE.md부터 새로 읽고(시작 입력 27~30k) 앞 단계가 읽은 파일을 다시 읽음(계획 단계 20개) ③ 계획 단계의 긴 출력 ④ 검증의 반복 측정(서버도 느려짐) ⑤ 검증 여러 차. hook은 호출당 0.1~0.3초(세션 전체 1~2분)라 원인 아님 |
| 개선 (같은 일을 새 규칙으로 했다면, 단계별 실측으로 계산) | 원인 모르는 문제 → 계획은 메인이 직접(`planner` 생략), 검증 1회: **기다린 시간 50.0 → 33.1분(−34%, 각 단계 첫 응답~마지막 응답 기준), 서브에이전트 입력 19.7M → 약 15.2M(−23%), 출력 252k → 약 140k(−44%)** — 메인이 계획을 쓰는 몇 분·토큰은 더해진다. 조사 질문을 1번(원인 모름)으로만 좁히고 2~5번(고칠 곳 분명)을 빼면 더 준다 — 이 몫은 다시 돌려 재지 않아 숫자가 없다 |
| Researcher 모델 비교 (같은 질문 'Grafana 주석·툴팁 가능 여부'를 다시 돌림) | Opus 3.9분·입력 1.82M·출력 18.6k → Sonnet 1.6분(−59%)·0.35M(−81%)·7.9k(−58%). 그러나 Sonnet은 '툴팁이 null 칸에서 가까운 값을 쓰나'를 소스 대신 요약본으로 판단해 틀렸다(Opus는 uPlot 소스로 15 px 안의 가까운 값을 쓴다고 확인 — 경보 툴팁 구현이 이 사실에 기댐). **모델은 그대로 둠** |
| 켬·끔 (D207) | `tests/test_agent_log.py` 296 → 300 passed: 기본 켬 → 파일·환경변수로 끔(off·0·false·no·끔·꺼짐), 환경변수가 파일보다 먼저, 깨진 파일은 켬 / 기록 끔이면 로그 파일 없음 / SessionStart만 꺼진 설정을 stdout에(다른 이벤트는 빈 stdout) / 기록 끔에도 가드는 거부하고 기록은 안 남김. 실제 Claude Code 세션에서 env가 hook에 넘어가는지는 확인 못 함(파일을 직접 읽어 같은 결과) |
| 남은 비용 (하네스와 무관, 사용자 결정 필요) | CLAUDE.md 0절 — 세션 시작에 논문 PDF 25쪽을 읽어 메인 컨텍스트가 65k → 117k(+52k)로 늘고 이후 모든 응답에 실린다(이 세션 약 8M 캐시 읽기 ≈ 메인의 15%). 하네스 전 세션도 같았다. CLAUDE.md 자체도 35.6 KB → 42.3 KB로 커져 서브에이전트마다 실린다 |

확인하지 못한 것: Windows PowerShell에서 직접 실행한 Claude Code, `PermissionDenied`·`StopFailure`·`PreCompact`의 실제 입력(시험 세션에서 일어나지 않음 — 받은 필드를 그대로 남기므로 형식이 달라도 기록은 된다).

### 환경 메모

- hook은 Claude Code를 **이 폴더(`dashboard/`)에서 시작했을 때만** 돈다. 상위 폴더(`/mnt/c/portran`)에서 시작한 세션은 기록되지 않는다.
- `claude -p`(비대화 모드)에서는 `--allowedTools`에 없는 Bash 명령이 조용히 거부된다. 기록에는 결과 없는 `PreToolUse`로 남는다(`show`의 "결과 없음(중단·거부)").

### 남은 일

- [x] 최신 `origin/dev`에서 만든 `feat/agent-workflow`에 이번 파일만 커밋(11/18, 사용자 확인). 작업 트리에 함께 있던 README 3번째 줄 수정·`docs/정리.md`·`탐지엔진-대시보드샘플/`은 이번 작업과 별개라 넣지 않음
- [x] push, `dev`로 PR — #54로 `dev`에 병합됨(11/18)
- [ ] 팀원 알림(D198)
- [ ] 다음 작업부터 12절 10항 흐름을 적용하고 Reviewer 판정을 이 문서 확인 결과에 남기기


## 대시보드 로딩·표시 수정 (2026-11-18, 브랜치 `fix/dashboard-loading-display`)

사용자 요구(11/18): ① 그래프 로딩이 오래 걸려서 불러오지 못하는 문제(관제, AWS, 최근 7일 — KPM 두 그래프가 경고 삼각형 + No data) ② 대표 값 ratio를 소수 셋째 자리에서 반올림해 ×100, %로 ③ 판정 요약의 모드 열 삭제 ④ 걸린 UE의 UE(cell-du_ue_id-uid)를 UE(cell-uid)로 ⑤ UE_EVENT 두 패널의 UE도 cell-uid로. 작업 중 추가: ⑥ 경보 구간 어디에 마우스를 대도 공격 정보가 보이게(보라 세모 키우기는 사용자 결정으로 그대로 둠).

흐름(CLAUDE.md 12절 10항): Researcher(원인 측정) → Planner(완료 조건 24개) → 사용자 승인 → 구현 → Reviewer. ⑥은 작업 크기별 기준(사용자 결정 11/18 — CLAUDE.md 반영은 이번 작업 뒤 따로)에 따라 좁은 Researcher(Grafana 가능 여부) → 메인이 계획 → 구현.

### 원인 (①, AWS Grafana 12.4.13에 `/api/ds/query`로 실측)
- 셀 거르기 `contains(value: r.cell, set: ${cell:json})`가 range 바로 뒤 filter에 있어 InfluxDB가 저장소에서 거르지 못함 → 7일 kpm2를 다 읽어 30초 넘김 → Grafana 데이터 프록시 시간 제한(30초)
- 3초 원본을 묶지 않고 가져옴 → 데이터가 꽉 찬 날은 24시간에도 프레임당 maxDataPoints × 10행을 넘어 `too many datapoints`
- 관제 새로고침 5초가 진행 중인 쿼리를 취소하고 다시 보냄 → 5초 넘는 쿼리는 화면에 결과가 한 번도 안 옴
- 성능 대시보드도 기본 24시간에서 시간 그래프 6개가 `too many datapoints`

### 한 일
| 파일 | 내용 |
|---|---|
| `grafana/build.py` | `WINDOW`(v.windowPeriod를 3초 배수로 올린 `win`), `window_by`(저장소에서 series마다 묶고 group 뒤 한 번 더 — 세션 합치기, 빈 구간 null), `kpm2_source`, `CELL_REGEX`. 관제 KPM 막대(구간 합, 막대가 자기 구간을 덮게 `barAlignment` 1)·UE 선(구간 최대, 평균 선은 평균)·'칸 일부 없음' 주석(구간마다 하나, 칸 수·가장 적은 n). 성능 시간 그래프 6개 + CPU · RRC 연결 시도: 필드를 구간 평균으로 먼저 묶고 계산(`overhead_windowed`, `null_unless` — `debug.null`), 링크는 증가분 구간 평균 ÷ 3초. `insertNulls` 삭제. 대표 값 ratio %(`math.round`), 판정 요약 mode 삭제, 걸린 UE·peers·UE_EVENT 두 패널 셀-uid. 경보 툴팁 계열(`alert_hover_query`, refId B, `ALERT_HOVER_OVERRIDE`) |
| `grafana/dashboards/*.json` | build.py로 다시 만듦(`grafana/provisioning/alerting/portran.json`은 바뀌지 않음) |
| `grafana/query_timing.py` (새 파일) | 저장소의 대시보드 JSON 쿼리를 실제 Grafana에 읽기로만 보내 시간·최대 행·상한을 재고, 오류·점 수 초과·시간 초과면 1로 끝남. `--parallel`은 동시에 보내 가장 늦은 응답 |
| `tests/test_dashboards.py` | 바뀐 검사(선 끊기 = `createEmpty: true`, 셀 = `${cell:regex}`, 링크 ÷ 3.0, 모드 없음) + 새 검사 5개(range 뒤 첫 filter에 contains 없음, 원본 시간 그래프는 모두 win으로 묶음, 막대 정렬, 대표 값 %, UE 셀-uid, 경보 툴팁 계열) |
| `tests/test_dashboard_flux.py` (새 파일) | 대시보드 Flux를 실제 InfluxDB 임시 bucket에서 돌려 값 확인 7개: 세션 합치기·구간 합, 3초 구간 = 원본, 빈 구간 null(관제 UE 선·성능 CPU 내역·CPU 사용률), 칸 일부 없음 끝 시각, ratio %, UE 셀-uid(du_ue_id를 uid와 다르게 넣어 가림), 경보 툴팁 계열이 경보 구간을 빈틈없이 채움 |
| `tests/conftest.py`, `tests/test_influx_integration.py` | `temp_bucket` 픽스처를 conftest로 옮김(파일마다 따로 bucket — bucket 전체 점 수를 세는 통합 테스트와 안 섞이게) |
| CLAUDE.md | 4절 트리, 9.1 KPM 행, 9.1 Flux 주의에 '긴 시간 범위' 규칙 4개, 9.2 묶음 설명 |
| `docs/dashboard-design.md` | 2절(새로고침 5초 조건, KPM 묶음, 대표 값 %, 판정 정보, UE 셀-uid), 3.3절(성능 묶음), 4절(선 끊기 D156 → D202, 칸 일부 없음) |
| README | 관제 표(긴 범위 묶음, ratio %, UE 셀-uid), '쿼리 시간 재기', 디렉터리 표 |

### 결정 사항
| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D202 | **긴 시간 범위 쿼리 규칙**: ① 셀은 정규식 `r.cell =~ /^${cell:regex}$/`(range 바로 뒤 filter에 contains 금지) ② 상시 KPM2·overhead 원본은 `win` = v.windowPeriod를 3초 배수로 올린 구간으로 range·filter 바로 뒤에서 묶고, group 뒤 한 번 더(세션 합치기) ③ 묶음 함수: KPM 막대 구간 합, UE 컨텍스트·RRC 연결 UE(최대) 구간 최대, RRC 연결 UE(평균)·성능 시간 그래프 모두 구간 평균(사용자 결정) ④ 선 끊기는 빈 구간 null 행(`createEmpty: true`, 선택 함수 뒤에는 mean으로 한 번 더) — D156 `insertNulls` 6000 대체. 1시간 화면에서는 칸 하나만 빠져도 끊김(사용자 승인) ⑤ '칸 일부 없음'은 고정값(agg_ms 3000, n < 30)으로 걸러 구간마다 하나 ⑥ KPM 막대 `barAlignment` 1(막대가 실제 칸 자리 — 3초 오른쪽, 사용자 승인) ⑦ 링크 초당 값 = 증가분 구간 평균 ÷ 3초(AWS 7일 217,834줄 모두 3000 ms) ⑧ 관제 새로고침 5초 유지 ⑨ 측정 도구 `grafana/query_timing.py`(사용자 승인) | 7일 kpm2 184만 점, 칸 일부 없음 6만 칸. contains·열끼리 비교·한 from 나눠 쓰기는 저장소 계산을 막아 수 초~30초. `max` + `createEmpty: true`는 7일 1~2초 | 불필요 |
| D203 | **화면 표시**: 대표 값 `ratio`는 `math.round(x × 100)` % 정수(0.5714 → 57% — 둘째 자리 반올림 뒤 ×100은 56.99999…%), 다른 키는 그대로, 판정 근거 값의 원값도 그대로. 판정 요약 모드 열 삭제. UE·peers·UE_EVENT는 셀-uid(`6733824-63`), 열 이름 'UE (cell-uid)', 타임라인 행 이름은 앞에 'UE' 없이. '피해자 연결 (peers)' 열은 '피해자 연결'로(필드 이름은 화면에서 뜻이 없음, 사용자 결정 11/18 — Reviewer 검증 뒤 바꿈). InfluxDB `alert_ue.ue` 태그·peers 저장값은 그대로(덮어쓰기 방지 키). 타임라인은 (셀, du_ue_id, uid) 전체로 묶어 겹치는 셀-uid가 있어도 합치지 않음 | 사용자 요청·결정(11/18). uid는 세션 안에서 유일(27_), 경보 상세는 경보 하나(세션 하나)라 화면에서 구분됨 — AWS 30일 51행에서 겹침 0 | 불필요(화면만) |
| D204 | **경보 툴팁 계열**: 관제 KPM 두 그래프에 refId B — 경보마다 시작·끝과 그 사이 구간 경계(win)를 채운 계열(값 = 심각도, 이름 = 종류 — 공격 이름 · 셀 · 상태)을 그래프·범례에서 숨기고(`hideFrom.viz`·`legend`) 툴팁에만, 자기 숨은 축. 구간 끝은 경보 구간 주석과 같다. 채우기는 `experimental.unpivot` + `interpolate.linear`(경보 길이에 비례). 경보 요약은 필요한 필드만 읽는다(B·경보 구간 주석 = severity·reason, 탐지 결과 = severity — 알림 규칙·경보 표는 그대로). 보라 세모(DU·CU 재시작)는 그대로. kpm2가 없는 출처(샘플)에서는 KPM 패널이 'No data' 대신 빈 그래프 | Grafana 12.4.13은 주석 마커 크기가 CSS 5 px 고정이고, 주석 글은 마커에서만 뜬다(구간 영역 호버 기능 없음, `AnnotationMarker2.tsx`). 툴팁은 커서 칸 값이 null이면 15 px 안의 가장 가까운 값을 쓰므로 구간 끝 바로 밖에서도 보일 수 있음. 보라 세모는 사용자 결정(11/18)으로 그대로. 처음 구현(경보마다 화면 범위 전체를 `aggregateWindow(createEmpty)`로 채움)은 7일 패널 요청 5~11초로 1번을 되살려 Reviewer 1차에서 걸림 → 위 방식으로 바꿈. 7일 프로파일: 경보 요약 2.9초 중 대부분이 경보 필드 읽기(경보 tag마다 series) | 불필요 |
| D205 | **Reviewer 검증은 1회만** — '수정 필요'면 고치고 다시 검증하지 않으며, 고친 것은 'Reviewer 검증 안 받음'으로 적는다 (D201의 최대 3차를 바꿈) | 사용자 결정(11/18): 역할 분리 흐름이 너무 느리다. 이번 작업은 1차(수정 필요) 뒤 2차를 중단 | 불필요 |

### 확인 결과
| 확인 | 결과 |
|---|---|
| AWS 측정 — 바꾸기 전(Researcher, 셀 All) | RRC 연결 시도 1h 0.44 s / 24h 2.30 s / 꽉 찬 날 24h 9.61 s `too many datapoints` / 3d 13.54 s 같은 오류 / 7d 29.99 s 시간 초과. UE 컨텍스트 7d 30.04 s 시간 초과. 주석 '칸 일부 없음' 7d 30.03 s 시간 초과. 성능 24h: 시간 그래프 6개 `too many datapoints` |
| AWS 측정 — 바꾼 뒤 (`grafana/query_timing.py --url http://3.39.170.31:3000 --source p4`, 배포 없이 읽기만, **패널 단위** — 패널의 쿼리 A·B를 한 요청으로) | Reviewer 1차 뒤 최종: 관제 19개 요청: **7d 패널마다 0.47 s 이하**(KPM 막대 A+B 0.22 s, UE 선 A+B 0.47 s, 경보 표 0.46 s), **동시에 보냈을 때 가장 늦은 응답 1.93 s**, 24h 동시 0.97 s, 1h 동시 1.00 s — 오류·점 수 초과 0. 성능 9개: 7d 최대 3.20 s('고른 시간 범위 요약' — 원본으로 평균·최대, 새로고침 1분), 24h 최대 0.49 s. 측정이 몰리면 AWS(t3.small)가 4~5배 느려진다 — Reviewer 1차 중 경보 표 0.44 → 1.5~2.8 s(CPU 크레딧 소진으로 보임, 확인은 못 함). 그 상태에서도 최종 쿼리는 7d 동시 2.96~3.07 s로 통과 |
| AWS 실데이터 값 | 경보 목록 `ratio = 57%`·`83%`·`100%`, 다른 키 `victims = 1`·`stalls_w = 20` 그대로. 판정 요약에 모드 없음. Blind DoS 경보의 걸린 UE `6733824-63`, peers `6733824-62`, 타임라인 행 `6733824-63`, 메시지 표 `6733824-63`. 경보 툴팁 계열: 최근 3시간 경보 13개 모두 6초 구간마다 빈틈없이, 이름 '공격 — 인증 단계 고착 · 셀 6733824 · 해제' 꼴 |
| `pytest` | 전체 589 passed(로컬 InfluxDB·Grafana 떠 있음, 건너뜀 0). `tests/test_dashboards.py` 42, `tests/test_dashboard_flux.py` 7. `python grafana/build.py --check` 0, 알림 provisioning(`portran.json`) 기준 커밋과 같음 |
| Reviewer 1차 | **수정 필요**. 완료 조건 26개 중 25개 ✅, 17(관제 7d 동시 5 s) ❌ — 5회 모두 실패(동시 7.9~8.8 s). 높음 1: 경보 툴팁 계열(B)이 경보마다 화면 범위 전체를 채워 7일 패널 요청 5~11 s(1번 회귀). 중간 2: `query_timing.py`가 패널의 A·B를 따로 재 실제보다 낮게 잼, progress 수치 재현 안 됨. 낮음 5: 경보 툴팁이 README·설계·CLAUDE.md에 없음, kpm2 없는 출처는 빈 그래프, `kpm2_source` extra가 여러 필드면 마지막 필드에만 걸림, 3초·100 ms 고정 전제(D202에 적음), peers 형식 밖 값은 그대로 보임 → **고침**: B를 unpivot + interpolate로(경보 길이 비례), 경보 요약 필드 줄임, 측정을 패널 단위로, 문서 반영, `kpm2_source` 괄호. 3초 고정·peers는 그대로 두고 기록 |
| Reviewer 2차 | **하지 않음** — 사용자 결정(11/18 "검증 한번만, 너무 느려")으로 시작한 2차 검증을 중단했다(D205). **1차 뒤 고친 것(경보 툴팁 쿼리 unpivot + interpolate, 경보 요약 필드 줄임, `query_timing.py` 패널 단위 측정, 문서, `kpm2_source` 괄호)은 Reviewer 검증을 받지 않았다** — 확인은 위 테스트(589 passed)와 AWS 측정으로만 |

확인하지 못한 것: **화면에서 마우스를 대 본 것** — 경보 툴팁이 구간 어디서나 뜨는지, 숨긴 계열이 y축에 영향이 없는지, 막대 위치(barAlignment 1). 헤드리스 브라우저가 이 PC에서 실행되지 않음(`libasound.so.2` 없음, 설치에 sudo 필요). Grafana 12.4.13 소스(TooltipPlugin2·uPlot 1.6.32·`buildScaleKey`)와 쿼리 결과로만 확인했다 — 배포 뒤 AWS 화면에서 확인한다.

### 환경 메모
- 대시보드 쿼리를 바꾸면 배포 전에 `python grafana/query_timing.py --url http://<탄력적 IP>:3000 --source p4 --range 7d --parallel`로 잰다. 로컬 데이터(샘플)는 양이 적어 이번 문제를 재현하지 못한다(로컬 쿼리 실행 테스트는 15분·샘플).
- Flux에서 null 값을 내려면 `import "internal/debug"`의 `debug.null(type: "float")`(InfluxDB 2.7.12에서 확인). `array.from` 행처럼 타입이 정해진 레코드에서는 없는 열을 `r.x`로 읽으면 타입 오류다.

### 남은 일
- [ ] 커밋(README 3번째 줄 사용자 수정 포함 — 사용자 결정 11/18), push, `dev`로 PR, `main` 병합(= AWS 배포) — 모두 사용자 확인
- [ ] 배포 뒤 AWS 관제 'Last 7 days' 화면 확인: KPM 두 그래프 표시, 경보 구간 툴팁, 막대 위치
- [ ] 작업 크기별 단계 기준과 **Reviewer 검증 1회(D205)** 를 CLAUDE.md 12절 10항·`docs/agent-workflow.md`에 넣기(사용자 결정 — 이번 작업 뒤 따로)
- [ ] 이번 범위 밖: '근거 KPM'(경보 하나의 100 ms 근거)은 30분 넘는 경보면 점 수 상한에 걸릴 수 있다(기록만, 측정에서 뺌)


## 경보 구간 깜빡임 (2026-11-18, 브랜치 `fix/alert-region-flicker`)

사용자 요구(11/18): "그래프 두 개에서 Refresh 될 때마다 공격 구간이 깜빡깜빡 거리는데 왜 이러는 거야?" → 제안대로 고침. 역할 분리 꺼짐(D208)이라 서브에이전트 없이 진행, Reviewer 검증 없음.

### 원인 (Grafana 12.4.13 소스)
- 경보 구간은 대시보드 주석(`경보 구간`)으로 칠했고, 주석은 새로고침(5초)마다 다시 조회한다.
- Grafana `runRequest`는 쿼리가 200 ms 안에 안 끝나면 '로딩 중, 빈 결과'를 먼저 내보낸다(`public/app/features/query/state/runRequest.ts:185` `timer(200)`). 주석 레이어는 그 빈 결과를 그대로 패널에 넘겨(`@grafana/scenes` 7.3.0 `standardAnnotationQuery.ts`·`AnnotationsDataLayer.tsx`) 그 순간 주석이 지워지고, 쿼리가 끝나면 다시 그려진다. 패널 데이터(막대·선)는 로딩 중에도 이전 값을 유지해 깜빡이지 않는다.
- 경보 구간 주석은 경보 요약(근거 포함)을 계산해 0.14~0.5초 — 200 ms를 넘는 주석이 이것뿐이었다(나머지는 7일에도 0.13초 이하).

### 한 일
| 파일 | 내용 |
|---|---|
| `grafana/build.py` | 경보 계열(refId B, `alert_hover_query`)이 경보 구간을 직접 칠함: 값 1, 자기 숨은 축 0~1, 계단(stepAfter)·선 두께 0·채우기 12%·주황(예전 주석 색과 같음), 범례 숨김·툴팁 표시. 툴팁 이름에 심각도를 더함(종류 — 공격 이름 · 셀 · 상태 · 심각도), 값은 '경보 구간'. `경보 구간` 주석과 그 쿼리 삭제. 패널 설명 |
| `grafana/dashboards/monitoring.json` | build.py로 다시 만듦(알림 provisioning 그대로) |
| `tests/test_dashboards.py`, `tests/test_dashboard_flux.py` | 주석 목록에 '경보 구간' 없음, B override(그림·축·색), 이름에 심각도 |
| CLAUDE.md 9.1, `docs/dashboard-design.md` 2.2, README | 경보 구간 = 경보 계열, 깜빡임 원인 |

### 결정 사항
| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D209 | **경보 구간은 주석이 아니라 경보 계열(refId B)로 칠한다**. 아래쪽 작은 주황 마커(주석)는 없어짐 — 정보는 영역 툴팁에 다 있음. 대시보드 주석은 200 ms 안에 끝나는 가벼운 것만 둔다 | 주석은 쿼리가 200 ms를 넘으면 새로고침마다 깜빡인다(Grafana 동작). 패널 데이터는 안 깜빡이고, 주석 쿼리가 하나 줄어 가벼워짐 | 불필요 |

### 확인 결과
| 확인 | 결과 |
|---|---|
| `pytest tests/test_dashboards.py tests/test_dashboard_flux.py` | 49 passed(로컬 InfluxDB·Grafana). `python grafana/build.py --check` 통과, `portran.json` 그대로 |
| AWS 측정(`grafana/query_timing.py`, 한 번) | 관제 7일: 요청 18개(주석 하나 줄어듦), KPM 막대 A+B 0.21 s·UE 선 A+B 0.43 s, 남은 주석 0.13 s 이하, 동시 가장 늦은 응답 1.61 s. 1시간: KPM 0.08·0.35 s |

확인하지 못한 것: 화면에서 깜빡임이 사라졌는지와 영역 모양(계단 채우기가 예전 주석 영역과 같아 보이는지) — 브라우저로 보지 못함. 배포 뒤 AWS에서 확인. 7일 범위의 '칸 일부 없음' 주석은 0.13 s라 서버가 느리면 200 ms를 넘어 깜빡일 수 있다.

### 남은 일
- [ ] 커밋·push·PR(사용자 확인), 배포 뒤 화면 확인


## 걸린 UE 열 정리 (2026-11-20, 브랜치 `fix/alert-ue-columns`)

사용자 요구(11/20): "걸린 UE 패널에서 근거랑 관측오류 없애자". 역할 분리 꺼짐(D208)이라 서브에이전트 없이 진행.

### 한 일
| 파일 | 내용 |
|---|---|
| `grafana/build.py` | '걸린 UE' 쿼리에서 `관측 오류`(`uncertain`)·`근거`(`evidence`) 열을 빼고 열 순서·패널 설명 고침 |
| `grafana/dashboards/monitoring.json` | build.py로 다시 만듦 |
| `tests/test_dashboards.py` | `test_alert_detail_columns`: 두 열 없음, 열 순서 고정 |
| `docs/dashboard-design.md` 2.2 | 걸린 UE 열 목록 |

### 결정 사항
| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D210 | 걸린 UE 표의 관측 오류·근거 열 삭제. 값은 InfluxDB `alert_ue`(`uncertain`·`evidence` 필드)와 원본 녹화에 그대로 남는다. 관측 오류뿐인 경보는 경보 목록의 종류 '판정 보류'로 보인다 | 사용자 요청(11/20) | 불필요 |

### 확인 결과
| 확인 | 결과 |
|---|---|
| `pytest` | 처음엔 Docker Desktop이 꺼져 있어(WSL에서 `docker` 없음) 39 passed, 10 skipped. Docker를 켠 뒤 전체 테스트 건너뜀 없이 통과(아래 커밋 전). `python grafana/build.py --check` 통과 |
| AWS Grafana(읽기만) | 바뀐 '걸린 UE' 쿼리를 최근 경보 `20261119T070012Z-L3-06-6733831-629`로 실행: 오류 없음, 열 8개(걸린 시각·UE (cell-uid)·S-TMSI·C-RNTI·조건·피해자 연결·UE 관측값·이벤트) |


## 수집 지연 측정 (2026-11-20, 브랜치 `feat/ingest-delay`)

사용자 요구(11/20): "대시보드에 데이터가 표시되는 지연시간도 중요하려나" → "표시되는 순간의 p50, p95, p99를 보여줘야 하나" → 진행. 역할 분리 꺼짐(D208)이라 서브에이전트 없이 진행.

### 한 일
| 파일 | 내용 |
|---|---|
| `collector/influx_writer.py` | `ingest_delay_point`, `DELAY_REFERENCE` — 받은 시각 − 데이터 시각(kpm2·overhead = `t_end_ms`, alert = `t`, f1_evt = `t_ms`) |
| `collector/collector.py` | `/ingest` 요청에서 받아들인 줄마다 지연 점을 레코드 점과 같은 쓰기에 더함(503이면 함께 빠짐, 중복은 재지 않음) |
| `grafana/build.py`, `performance.json` | 성능 대시보드 줄 '수집 지연': '수집 지연 백분위' 표(한 행 = 'KPM 지연'(상시 KPM2)·'경보 지연', 열 p50·p95·p99·개수 — 처음 stat 숫자 6개를 사용자 요청으로 표로 바꾸고 최대 열은 뺌), '수집 지연 추이'(그래프 구간마다 평균 — 'KPM 지연' 파란 선·'경보 지연' 주황 선. 처음의 최대 계열은 사용자 요청으로 뺌) |
| `tests/test_ingest.py` | 지연 점(값·태그·겹치지 않는 시각·중복·503), 레코드 점 수를 세던 테스트는 지연 점을 빼고 셈 |
| `tests/test_dashboards.py`, `tests/test_dashboard_flux.py` | 성능 줄 배치, 백분위·추이 값(실제 InfluxDB) |
| CLAUDE.md 6절·9.2, `schema/SCHEMA.md` 5절, `docs/dashboard-design.md` 3.4절, README | `ingest_delay` 저장 형태와 패널 |

### 결정 사항
| # | 결정 | 이유 | 팀 확인 |
|---|---|---|---|
| D211 | **수집 지연 = collector가 받은 시각 − 데이터 시각**, 줄마다 `ingest_delay` 점 하나(tags env·type·event, field delay_ms, 시각 = 받은 시각 + 요청 안 순번 ns). 기준 시각: 상시 KPM2·overhead는 칸 끝(칸 시작으로 재면 3초 묶음이 섞임), 경보는 판정 시각. evidence(지난 원본 줄)·gap·hello는 재지 않음. 화면까지 더해지는 새로고침 대기(최대 5초)·쿼리 시간은 재지 않고 설명에 적음(서버에서 잴 수 없음). 백분위 표: 종류마다 p50·p95·p99·개수(경보는 개수가 적어 p99가 맨 위 값에 가까워 개수를 같이 보임). 추이는 추세만 — 구간 평균 한 계열씩(사용자 요청 11/20). 메시지 형식(스키마)은 그대로 — 새 measurement만 | 발표에서 "공격이 몇 초 만에 대시보드에 오나"를 실측 숫자로 말하려고(5G-Spector도 탐지 지연을 평가). 대시보드 구간은 우리 담당이라 지금 잴 수 있다 | 불필요 — 단, 두 서버 시계 동기화(Q8)는 탐지 쪽·테스트베드 확인 필요 |

### 확인 결과
| 확인 | 결과 |
|---|---|
| `pytest` | Docker를 켜고 전체 597 passed(로컬 InfluxDB·Grafana, 건너뜀 0 — 새 `test_ingest_delay_percentiles_and_trend` 포함). `python grafana/build.py --check` 통과 |
| 로컬 시연 | 목 송신기(상시 KPM2 셀 2개 3초 칸·overhead·40초마다 경보, 레코드마다 지연 0.2~1.5초 · 5%는 2~6초)로 `X-Env: sample`을 8분 동안 `/ingest`에 보냄 → 수집 지연 백분위(8분 끝, 505줄 모두 저장): 상시 KPM2 320개 p50 718·p95 2470·p99 5411 ms, 경보 24개 p50 600·p95 2067·p99 2174 ms(송신기가 준 지연 — 5%는 2~6초 — 과 맞음). `query_timing.py --source sample --range 15m`: 성능·관제 모두 통과 |
| AWS Grafana(읽기만, 가짜 데이터) | 두 패널 쿼리의 `from`을 `array.from`(상시 KPM2 지연 10~1000 ms 100개, 경보 300·800·1200·5000 ms)으로 바꿔 실행: 백분위 = 500·950·990 / 800·1200·5000(기대값과 같음), 추이 = 6초 구간 601행, 빈 구간 null, 경보 점이 같은 구간 행에 들어감 |

확인하지 못한 것: 실측 지연 값과 7일 범위 쿼리 시간은 배포 뒤 데이터가 쌓여야 잴 수 있다(`grafana/query_timing.py --dashboard performance --range 7d`). 두 서버 시계 동기화(Q8).

### 남은 일
- [ ] 커밋·push·PR(사용자 확인), 배포 뒤 실측 지연 값과 7일 쿼리 시간 확인


## 경보 목록 룰 열 삭제 (2026-11-20, 브랜치 `fix/alert-list-rule-column`)

사용자 요구(11/20): "관제 대시보드의 경보 목록에서 룰 항목은 없애줘". 역할 분리 꺼짐(D208).

| 구분 | 내용 |
|---|---|
| 한 일 | `grafana/build.py` 경보 목록 쿼리·열 순서·열 너비에서 `룰` 삭제, `monitoring.json` 다시 만듦, `tests/test_dashboards.py`(룰 열 없음), CLAUDE.md 9.1·README·`docs/dashboard-design.md` 2.2 |
| 결정 D212 | 경보 목록의 룰 ID 열 삭제 — 공격 열이 같은 룰을 짧은 공격 이름으로 보인다. 룰 ID는 경보 상세 '판정 요약'과 alert_id에 남는다. 사용자 요청, 팀 확인 불필요 |
| 확인 | `pytest` 전체 597 passed(로컬 InfluxDB·Grafana), `python grafana/build.py --check` 통과 |

## 데이터 출처 aws·on-premise, Slack On-Premise (2026-11-20, 같은 브랜치)

사용자 요구(11/20): "탐지 쪽에서 node-id: cu, X-env: aws, X-env: on-premise로 바꿨는데 그거에 맞게 되어 있어?" → 맞지 않아 고침. 결정: ① 이전 `p4` 데이터는 'AWS (이전 p4)'로 따로 보임(`aws`로 받되) ② On-Premise 공격 경보·수집 멈춤도 Slack으로 ③ On-Premise는 연구실이 아니라 우리 장비에서 보내고, IP는 이미 열어 둠. 역할 분리 꺼짐(D208).

| 구분 | 내용 |
|---|---|
| 확인 | AWS 서버 최근 30일 `env` 값: `lab`·`minwoo-probe`·`p1`·`p1-probe`·`p4`·`portran-p1`·`sample` — `aws`·`on-premise`는 아직 없음(11/20 17:37까지 `p4`, 노드 `p4-e2e`). collector는 형식 검사(`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)로 `aws`·`on-premise`를 받는다. 노드 `cu`는 이미 'CU'로 보임 |
| 한 일 | `grafana/build.py` `SOURCES`(AWS `aws`·On-Premise `on-premise`·AWS (이전 p4) `p4`·재생·샘플, 기본 AWS), 알림 `NOTIFY_SOURCES` — 출처마다 공격 경보·수집 멈춤 규칙(AWS UID 예전 그대로, On-Premise `-onprem`), 라벨 `source`·`env`, 메시지 제목 끝에 출처·경보 상세 링크 `var-source`를 그 출처로. `grafana/query_timing.py` 기본 `--source aws`. `collector/ingest.py` 설명. 테스트: 출처 변수, 알림 4규칙·라벨·템플릿, `X-Env` `aws`·`on-premise` 받음. 문서: CLAUDE.md 1.1·4·6·7·9·9.3·13절, README(그림·변수·Slack), `docs/dashboard-design.md` 1절·열린 질문, `schema/SCHEMA.md` 2절, `docs/deploy.md`. 열린 항목 Q21 → 해결됨 |
| 결정 D213 | 데이터 출처 = 탐지 쪽 `X-Env` 그대로: AWS `aws`, On-Premise `on-premise`. 11/20 전 AWS 실측(`p4`)은 쿼리를 바꾸지 않고 선택지 'AWS (이전 p4)'로 따로. Slack은 출처마다 규칙 — 재생·샘플·이전 p4는 알리지 않음. 사용자 결정, 팀 확인 불필요(탐지 쪽이 정한 값) |
| 확인 결과 | `pytest` 전체 599 passed(로컬 InfluxDB·Grafana — 알림 4규칙 쿼리 실행 포함), `python grafana/build.py --check` 통과. 실제 `aws`·`on-premise` 데이터는 아직 서버에 없어 화면·Slack은 탐지 쪽이 보내기 시작한 뒤 확인 |

## 칸 일부 없음 보고 주기, 성능 노드 CU, CPU·메모리 패널 (2026-11-20, 브랜치 `fix/overhead-panels-partial-period`)

사용자 요구(11/20): ① AWS 상시 KPM2 신뢰도 점검에서 찾은 '칸 일부 없음' 오판을 고침("1번 고쳐줘") ② 성능 노드가 왜 `p4-e2e`로 보이나 ③ "CPU 사용률 / 내역 → CPU 사용률(전체) / CPU 사용률(분석 엔진), 메모리 사용량 / 메모리 내역 → 메모리 사용량(전체) / 메모리 사용량(분석 엔진), 점선은 없애도 돼". 역할 분리 꺼짐(D208).

| 구분 | 내용 |
|---|---|
| 원인 ① | 관제 '칸 일부 없음'은 보고 주기를 100 ms로 박아 두고 `n` < 30이면 칠했다. AWS p4 11/13~11/15 세션 7개는 `hello.period_ms` 1,000 ms라 가득 찬 칸이 `n` 3 — 그 기간 칸이 모두 '일부 없음'으로 칠해졌다(데이터는 빠짐없음) |
| 원인 ② | 분석 엔진이 `--node p4-e2e`로 실행되고(`node_id`는 실행 옵션 또는 호스트 이름, telemetry `main.c`), 탐지 쪽 전송기는 `hello`의 `node_id`만 `cu`로 바꾸고 `overhead` 줄은 그대로 보낸다(detection `tools/dashboard_sender.py` `_hello_out`·`overhead` 분기). AWS 30일: `overhead` 노드 `cu`(11/13~15) → `p4-cu`(11/16~19) → `p4-e2e`(11/19~, `aws`도). 한 출처 안에서 이름이 다른 노드가 같은 시각에 보낸 적은 없음(겹침 0) |
| 한 일 | `grafana/build.py`: 칸 일부 없음 쿼리 — 저장소에서 세션·셀마다 구간으로 묶은 뒤(`n` < 30 고정 거르기 그대로) 세션 → 주기 사전(`hello.period_ms`, 처음부터 찾음, 없으면 100 ms)으로 '가득 찬 n'(3000 ÷ 주기)과 비교. 주기가 100 ms가 아니면 칸 수 대신 주기를 적음(`n` < 30 칸 수가 일부 없는 칸 수가 아니라서). 노드 — `NODE_FLUX`·`NODE_MAPPINGS` 삭제, 노드 칸은 늘 'CU', `overhead_windowed`는 노드로 나누지 않음. 패널 — 'CPU 사용률(전체)'(그대로), 'CPU 사용률(분석 엔진)'(`process_cores` / `cpu_count` × 100, '그 밖' 쌓기·점선 코어 수 없앰), '메모리 사용량(전체)'(점선 전체 없앰), '메모리 사용량(분석 엔진)'(RSS만, '그 밖' 없앰) — 계열 하나라 범례 숨김. 테스트: `tests/test_dashboards.py`(제목 4개, 노드 CU, 노드로 안 나눔, 범례·단위, hello 읽기는 묶기 검사에서 뺌, 제목 괄호 규칙에 '(전체)'·'(분석 엔진)' 예외), `tests/test_dashboard_flux.py`(1,000 ms 세션 `n` 3은 가득·`n` 2는 일부 없음, hello 없는 세션은 100 ms, 분석 엔진 CPU 12.5%·RSS·사용 중 값과 빈 구간 null). 문서: CLAUDE.md 5.2·9.1·9.2, README, `docs/dashboard-design.md` 2·3절, `schema/SCHEMA.md` 6절 |
| 결정 D214 | '칸 일부 없음' = `n` < 3000 ÷ 그 세션의 `hello.period_ms`(없거나 0이면 100 ms). 세션 → 주기는 Flux `dict`로 찾는다 — `join` 패키지는 한쪽이 비면 `cannot join on an empty table`로 깨지고(일부 없는 칸이 없으면 늘 빔), 빈 배열에 `array.map`을 쓰면 형식을 잃어(`fromList`가 `[string]`으로 받음) 기본 항목 하나를 늘 붙인다. 주기가 100 ms보다 짧은 세션은 `n` 30 미만만 본다(저장소 거르기 고정값). 팀 확인 불필요(대시보드 표시) |
| 결정 D215 | 성능 노드는 늘 CU 하나 — overhead는 CU 박스의 분석 엔진만 보내고(27_ §9 R5), `node_id`는 실행 때 붙인 이름이라 바뀌어 왔다(범례가 이름이 바뀔 때마다 둘씩 나왔음, 11/16·11/20). D192('cu로 끝나면 CU')를 바꿈. 같은 출처에서 CU 말고 다른 노드가 overhead를 보내게 되면 다시 나눈다. 팀 확인 불필요, 탐지 쪽에는 Q26 ④로 알림 |
| 결정 | 'CPU 사용률(분석 엔진)' 단위는 노드 CPU 전체의 %(분석 엔진 코어 / 노드 코어 수) — 왼쪽 전체와 같은 기준이라 바로 비교된다. '고른 시간 범위 요약'의 '분석 엔진 평균'은 그대로 코어 수 |
| 확인 결과 | `pytest` 전체 600 passed(로컬 InfluxDB·Grafana — 바뀐 쿼리를 Grafana로 실행 포함), `python grafana/build.py --check` 통과, 알림 JSON 바뀌지 않음. AWS 서버(읽기만, 한 번씩): `query_timing.py --source p4 --range 7d` 관제 18요청·성능 11요청 모두 통과 — 칸 일부 없음 0.24초, CPU·메모리 4패널 0.08~0.09초. 칸 일부 없음(3초 구간, p4 10일) 154개 — 11/14·11/15는 0개(전에는 그 기간 전부), 11/13은 1,000 ms 세션의 시작·끝 칸(`n 1 / 3 (보고 주기 1000 ms)`)과 100 ms 칸만. `aws` 하루 4개(세션 시작·끝 칸) |
| 추가 요청 | "%로 맞춰줘, 글자 크기를 왼쪽 노드 칸이랑 통일" — '고른 시간 범위 요약'의 '분석 엔진 평균'(코어, `0.000 코어`로 보였음)을 '분석 엔진 평균 CPU'(`process_cores` / `cpu_count` × 100 평균, 소수 자리 자동)로. 노드·요약 칸 글자 크기를 `OVERHEAD_STAT_TEXT`(제목 14 px, 값 24 px)로 고정 — 자동이면 칸 폭·값 수에 따라 요약 칸 숫자가 훨씬 컸다. 테스트: 단위·쿼리·두 칸 글자 크기 같음, 실제 InfluxDB 값(분석 엔진 0.5 / 4코어 = 12.5%, 평균·최대 CPU 50·75%, 메모리 50%). AWS(읽기만, 한 번): 요약 7일 4.39초(전 3.2초 — 분석 엔진 몫도 원본 줄마다 나눠서, 새로고침 1분이라 둠), 값 p4 7일 0.0155%·`aws` 1일 0.0204% |
| 추가 요청 2 | "고른 시간 범위 요약도 CPU 평균 사용률 / 메모리 평균 사용률 / 분석 엔진 평균 메모리로, 더 좋은 대안 있으면 추천" → 평균 넷(전체 CPU·메모리, 분석 엔진 CPU·메모리)으로 추천·적용: 'CPU 평균 사용률', '메모리 평균 사용률'(전에는 최대), '분석 엔진 평균 CPU'(바로 전 요청으로 %), '분석 엔진 평균 메모리'(전에는 최대). '최대 CPU' 삭제 — 3초 한 칸의 순간값이라 CU의 다른 프로그램 하나로도 튀고(p4 7일 76.6%, 평균 2.8%) 시간 그래프에 보인다. 열 순서는 organize로 고정. AWS(읽기만, 한 번): 7일 3.27초, p4 7일 CPU 2.83%·메모리 71.0%·분석 엔진 0.0155%·306 MiB, `aws` 1일 2.57%·79.5%·0.0220%·309 MiB |
| 추가 요청 3 | "F1·N2 그래프의 나감·들어옴을 Outgress·Ingress로" → Ingress·Egress로(Outgress는 표준 용어가 아니고, 필드 이름이 `ingress_*`·`egress_*`). 범례 'F1 Ingress (DU → CU)'·'N2 Egress (CU → AMF)', Egress는 그대로 아래(음수 쪽). 테스트: 범례 이름·Egress 아래 |
| 추가 요청 4 | "고른 시간 범위 요약 → CPU/Memory 평균 사용률로", "Cpu/Memory" → 패널 제목을 'Cpu/Memory 평균 사용률'로(내용은 그대로) |
| 추가 요청 5 (11/25) | "CPU 사용률이 너무 작게 보인다, 잘 보이게" — 'CPU 사용률(전체)'·'CPU 사용률 · RRC 연결 시도'는 세로축 최대를 100%로 고정(`max: 100`)해 평소 2~5%(AWS 5분 평균 2.47%·최대 5.6%)가 바닥에 붙었다. 분석 엔진 패널은 고정이 없어 0.2% 축으로 자동 확대돼 크게 보였다. 고정 최대 대신 Grafana 소프트 최대 `custom.axisSoftMax` = `CPU_AXIS_SOFT_MAX`(10) — 축이 적어도 0~10%이고 넘으면 늘어난다. 함께 찾은 문제: 같이 그리는 패널의 오른쪽 축(RRC 연결 시도)도 0~100으로 묶여 있었다 — 기본값 `max: 100`을 override `max: null`로 풀려 했지만 Grafana가 null을 '설정 없음'으로 보지 않음(스크린샷에서 0인 막대 축이 0~100). 축 범위를 기본값이 아니라 'CPU 사용률' override에만 건다. 패널 설명에 축 규칙을 적음 |
| 결정 D216 | 노드 CPU % 그래프 축 = 소프트 최대 10%(100 고정 아님, 완전 자동도 아님). 완전 자동이면 2%→5% 흔들림이 꼭대기까지 튀어 과장돼 보인다. 분석 엔진 CPU(0.01~0.2%)는 자동 그대로 — 소프트 최대 10을 걸면 다시 바닥에 붙는다. 두 패널 축이 달라 높이로 비교하지 않는다(설명에 단위 기준이 같다고 적혀 있음). 사용자 요청, 팀 확인 불필요 |
| 확인 결과 5 | `python grafana/build.py` 다시 씀(`performance.json`만 바뀜, 관제·알림 JSON 그대로), `--check` 통과, `pytest` 처음 587 passed·14 skipped(InfluxDB 접속 실패로 서비스 테스트 건너뜀 — 아래 환경 메모), Grafana를 다시 만든 뒤 전체 601 passed(건너뜀 없음, 실제 InfluxDB·Grafana 포함). 쿼리는 바뀌지 않았다. 로컬 Grafana(12.4.13): 목업(scratchpad 스크립트, `X-Env` 대신 collector `--env sample`, 15분 = 3초 칸 300개마다 `overhead`·`kpm2` 셀 1, 가운데 2분 CPU 20~35%·RRC 연결 시도 30~60, 그 밖 CPU 2~5%) 601줄 저장·거부 0. Grafana API로 읽은 대시보드에 `axisSoftMax` 10(전체 패널 기본값, 함께 그리는 패널은 'CPU 사용률' override), `max` 없음. `query_timing.py --source sample --dashboard performance --range 1h` CPU 패널 셋 통과. **화면(축 모양)은 사용자가 보고 확인** — Reviewer 검증 없음(작은 화면 설정 수정, 역할 분리 꺼짐 12절 10항) |
| 환경 메모 5 | 로컬 Grafana 컨테이너에 대시보드가 하나도 없었다 — WSL을 거친 마운트(`docker-desktop-bind-mounts`)가 비어 있었고(`provisioning/dashboards: no such file or directory`), WSL에서 `docker` 명령도 없었다(WSL integration 꺼짐). Windows `docker.exe compose up -d --force-recreate --no-deps grafana`로 다시 만들어 Windows 경로로 마운트. README 문제 해결의 같은 항목에 한 줄 더함. 그 뒤 `build.py`로 다시 만든 JSON을 Grafana가 알아채지 못했다(Windows 경로 마운트라 10초 다시 읽기가 안 먹음) — 관리자 API `POST /api/admin/provisioning/dashboards/reload`(알림은 `alerting/reload`)로 반영, README 문제 해결에 새 항목 |
| 추가 요청 6 (11/25) | "Cpu/Memory 평균 사용률 → CPU/메모리 평균 사용률로" — 패널 제목만 바꿈(내용 그대로). 생성기·테스트·CLAUDE.md·README·설계 문서 함께. `pytest` 전체 통과 |
| 추가 요청 7 (11/25) | "관제에서 하향 IMSI 추출 → IMSI 노출, UE 능력 탈취 → 단말 성능 정보 탈취, NAS 카운터 비동기화 → NAS 카운터 불일치" — `grafana/rule-names.json`의 L3-24·L3-14·L3-06·L3-06-O1(후보) 이름을 바꿈(번호·괄호 영문은 27_ 대조용으로 남김, `_설명`에 27_와 다른 이름 적음). 짧은 이름은 한 곳에서 나오므로 관제·성능·Slack 알림이 함께 바뀐다. README 예시·`tests/test_dashboards.py` 기대값 고침. 생성된 JSON 셋에 옛 이름 0개 |
| 결정 D217 | 화면의 공격 이름 셋은 27_ §5.3과 다르게 쓴다(사용자 요청). 후보 L3-06-O1도 같은 공격(#6)이라 함께 바꿈('다 이렇게'). #25 '상향 IMSI 추출'은 요청에 없어 그대로. 팀 확인: 불필요(화면 표시) — 발표 자료·탐지 쪽 문서와 이름을 맞출지는 사용자가 판단 |
| 남은 일 | Q26(탐지 쪽·테스트베드 요청) — 사용자가 전달 |

## 판정 근거 키 이름 (2026-11-25, 같은 브랜치)

사용자 요구(11/25): "관제 판정 근거 값에 보이는 탐지 JSONL 필드값의 이름을 바꾼 엑셀(`35_탐지엔진_판정근거-대시보드값_분석표.xlsx`)을 반영해 줘. 탐지 쪽에서 바꿔 보내면 알아서 반영되는 거 아닌가?"

| 구분 | 내용 |
|---|---|
| 엑셀 | 시트 7개(L3-01-V·L3-01-O·L3-20·L3-21·L3-24·L3-14·L3-06) — 판정 근거 값 표를 옮기고 키마다 뜻과 '바꿀 값'(대시보드가 키 대신 띄울 이름, 줄임말 없이). 후보 룰 ID는 안 바꿈. 같은 키라도 룰·항목마다 이름이 다르다: `unsolicited`(L3-24 → `unsolicited_identity_response`, L3-14 → `unsolicited_capability_information`, L3-06 → `unsolicited_security_mode_reject`), `branch1_ues`·`branch2_ues`(L3-21·L3-14), L3-20 `concurrent`(성립 조건 → `victim_connected`, 관측값 → `victim_connected_count`) |
| 한 일 | `grafana/evidence-key-names.json`(새 파일): 룰 → 항목(cond·conditions·values·params·refs) → 키 → 이름, 72개. 엑셀에서 프로그램으로 뽑아 대조(같음). `reference/detection/35_…xlsx`: 근거 엑셀 복사. `grafana/build.py`: Flux 함수 `rename(rule, field, s)` 생성 — 판정 근거 값 JSON 문자열에서 룰·필드마다 `"키":`(객체)·`"키"`(배열 원소)를 `strings.replaceAll`로 바꿈(따옴표까지 맞춰 `C2`가 `C2a`를 안 건드림, 이름이 키와 같으면 건너뜀). 경보 목록 '대표 값' 키도 같은 이름(`'룰\|키'` 사전, L3-01-O `stalls_w`·L3-20 `victims`·L3-21 `fails_w` — % 판단은 원래 키). 테스트: 대응표 모양(룰·항목·snake_case·새 이름 중복·새 이름이 다른 원래 키와 겹치지 않음), 쿼리 조각, 실제 InfluxDB에서 L3-20 성립 조건·관측값·설정값과 L3-01-V(엑셀에 없는 `a_w` 등 그대로), 대표 값 `victim_count = 1`. 문서: CLAUDE.md 4·9·9.1절, README, `docs/dashboard-design.md` 6.1절, `reference/README.md` |
| 결정 D218 | **화면에서만 바꾼다**(레코드 형식 27_·InfluxDB·녹화는 원래 키). 이유: 엑셀이 '대시보드가 키 대신 띄울 이름'이라고 적음, 탐지 엔진·collector·샘플·스키마를 안 고쳐도 되고 지난 데이터(p4·aws 녹화)도 같은 이름으로 보임. 탐지 쪽이 키를 바꿔 보내면 판정 근거 값 표는 따라가지만 대표 값(collector `REPRESENTATIVE_KEY`)이 비고 지난 데이터와 이름이 갈린다. 엑셀에 없는 키는 지어내지 않고 원래 키로 둔다(T9). 대표 값도 같은 이름으로(같은 경보의 같은 값이 두 이름으로 보이지 않게 — 요청 밖이라 사용자에게 알림). 걸린 UE 표의 `ues[].cond`·`values_json`은 엑셀에 없어 그대로. 팀 확인: 불필요(화면 표시, 탐지 쪽이 만든 이름표) |
| 확인 결과 | `python grafana/build.py --check` 통과, `pytest` 전체 604 passed(로컬 InfluxDB·Grafana 포함, 건너뜀 없음). 탐지 쪽 샘플 32개를 40분 전으로 옮겨(`replay --out file://` → collector `--once --env sample`) 1,758줄 저장·거부 0. 룰 7개 경보마다 판정 근거 값 쿼리를 InfluxDB에서 돌려 이름이 바뀐 것 확인(예 L3-01-O `["authentication_stall_count"]`, `{"stalls_window":5,…,"uectxmax":96}`). 엑셀에 없어 원래 키로 남은 것: L3-14 `enquiry_before_as_sec`, L3-21 `reg_repeat`·`fail`(성립 조건), L3-24 판정 보류 `held_count`·`held_w`, L3-01-V `a_w`·`f_w`·`ratio`·`base`, 옛 형식 `k`. `query_timing.py --source sample --dashboard monitoring --range 1h` 18개 통과. 화면은 사용자가 확인. Reviewer 검증 없음(역할 분리 꺼짐, 12절 10항) |
| 남은 일 | T9 — 엑셀에 없는 키의 이름(탐지 쪽·사용자) |

## 경보 상세가 누른 경보에서 첫 경보로 되돌아감 (2026-11-25, 같은 브랜치)

사용자 보고(11/25): 경보 목록에서 경보(L3-01-O-1-56)를 누르니 경보 상세가 그 경보로 떴다가 다른 경보(L3-01-V-1-55)로 바뀐다.

| 구분 | 내용 |
|---|---|
| 조사 | ① 바뀐 경보 L3-01-V-1-55는 변수 `alert_id`의 **첫 선택지**(가장 최근 raise)다. ② 누른 경보는 그때 선택지 안에 있었다(raise 15:08:54, 클릭 약 15:53, 범위 최근 1시간) — 범위 밖이라 되돌아간 것이 아니다. ③ `alert_id`는 refresh 2라 **5초 자동 새로고침마다 다시 조회·검증**된다(헤드리스 Chrome CDP Network로 5초마다 변수 쿼리 확인). ④ Grafana 12.4 번들(scenes)에서: 쿼리 변수는 요청이 **취소되면 선택지를 `[]`로** 받고(`catchError: cancelled ? of([]) : throw`), 단일 값 변수는 선택지가 0개면 값을 `""`로, 다음 검증에서 `""`가 선택지에 없으면 **첫 선택지로** 바꾼다. ⑤ 화면 이동·클릭은 진행 중인 쿼리를 취소한다(서버 로그 `context canceled`가 클릭 시각에 남음). ⑥ 사용자 흐름(AWS로 열고 드롭다운으로 샘플 → 행 클릭, 변수 쿼리 순간 0~2,500 ms 뒤 클릭 등 20여 번)을 헤드리스로 재현했지만 **되돌아감은 재현하지 못함** — 취소와 주소 반영의 순서에 달린 간헐적 경합으로 본다. 함께 찾은 것: 행 링크의 `var-cell=${cell}`이 여러 셀을 `{1,2}` 한 값으로 넘겨 셀 변수가 기본값으로 돌아감 |
| 한 일 | `grafana/build.py`: `query_variable`에 `refresh` 인자, `alert_id`는 refresh 1(열 때·출처를 바꿀 때만 조회 — 값은 행 링크 주소로 들어와 선택지 검증을 거치지 않음), 조회 범위를 경보 목록처럼 1시간 앞부터(범위 전에 시작해 아직 열린 경보도 선택지에). 행 링크 셀은 `${cell:queryparam}`. 테스트: refresh 규칙(alert_id만 1), 링크·범위. CLAUDE.md 9.1절 |
| 결정 D219 | `alert_id`만 refresh 1(D103의 예외). 잃는 것: 경보가 하나도 없을 때 연 화면은 첫 경보가 들어와도 상세가 저절로 채워지지 않는다(전에는 다음 새로고침에 첫 경보로) — 목록 행을 누르거나 새로 연다. 얻는 것: 누른 경보가 유지, 5초마다 돌던 변수 쿼리(7일 범위면 7일치 raise 조회) 없어짐. 사용자 보고로 정함, 팀 확인 불필요 |
| 확인 결과 | `pytest` 전체 605 passed, `--check` 통과, 로컬 Grafana provisioning 다시 읽음. 헤드리스 Chrome(CDP, scratchpad 스크립트)로 AWS로 열기 → 드롭다운 샘플: 경보 변수가 다시 조회되어 첫 경보로, 그 뒤 15초 동안 변수 쿼리 0건(전 5초마다), 행 링크 `var-cell=$__all`, 행 6번 눌러 6번 모두 10초 유지. 고치기 전 되돌아감을 재현하지 못해 **같은 현상이 다시 안 나는지는 사용자 화면에서 확인 필요**. Reviewer 검증 없음(역할 분리 꺼짐) |

## 경보 목록도 셀로 거름 (2026-11-25, 같은 브랜치)

사용자 요구(11/25): "셀을 고르면 탐지 결과·KPM은 걸러지는데 경보 목록은 모든 셀을 보여 주는 것 같다" → 맞음(경보 목록 쿼리에 셀 조건이 없었고, 셀 변수 설명도 '탐지 결과·상시 KPM2'만. 일부러 정한 기록은 없음) → "경보 목록에도 넣어줘".

| 구분 | 내용 |
|---|---|
| 한 일 | `grafana/build.py`: 경보 목록 쿼리의 거르기에 `r.cell =~ /^${cell:regex}$/`(탐지 결과와 같은 조건) — 범위 전에 시작해 아직 열린 경보도 고른 셀 것만. 경보 요약을 만든 뒤 거르는 것이라 저장소 거르기(D202)와 상관없다. 셀 변수 설명·패널 설명 고침. 테스트(실제 InfluxDB): 셀 1·여러 셀 `(1\|2)`은 경보가 보이고 셀 2는 비어 있음. CLAUDE.md 9.1절, `docs/dashboard-design.md` |
| 확인 결과 | `pytest` 전체 606 passed, `--check` 통과, 로컬 Grafana `query_timing.py --source sample --dashboard monitoring --range 1h` 통과 |
| 배포 전 AWS 측정 (11/25) | 바뀐 관제 쿼리를 배포 없이 읽기만, 명령마다 한 번: `query_timing.py --url http://3.39.170.31:3000 --dashboard monitoring --range 7d --parallel`. `--source p4` 18개 통과 — 가장 느린 경보 목록 0.31초(경보 39행), 판정 근거 값 0.05초, 동시 18개 가장 늦은 응답 1.30초. `--source aws` 18개 통과 — 가장 느린 UE 컨텍스트 0.14초, 동시 0.61초. 모두 5초 상한 안. 경보 변수 쿼리는 이 도구가 재지 않지만 이제 열 때·출처를 바꿀 때만 돈다(D219) |


## 공격 이름 상향 DoS → 등록 폭주 공격 (2026-11-26, 브랜치 `fix/rename-uplink-dos`)

사용자 요구(11/26): "상향 dos -> 등록 폭주 공격으로 바꾸자". 역할 분리 꺼짐(D208)이라 서브에이전트 없이 진행.

| 구분 | 내용 |
|---|---|
| 한 일 | `grafana/rule-names.json`: `L3-21` "#21 상향 DoS — 위조 자격증명 (Uplink DoS)" → "#21 등록 폭주 공격 — 위조 자격증명 (Uplink DoS)"(짧은 이름 '등록 폭주 공격'), `_설명`에 11/26 변경을 더함. `python grafana/build.py`로 관제 JSON(탐지 결과·경보 목록·경보 상세 후보 공격·경보 툴팁의 이름 7곳)과 알림 provisioning(AWS·On-Premise 공격 경보 규칙 2곳)을 다시 만듦 — Slack 알림 공격 이름도 바뀜. 성능 JSON은 그대로(공격 이름 없음). `tests/test_dashboards.py`에 `"L3-21": "등록 폭주 공격"` 확인을 더함. 쿼리 구조는 바뀌지 않음(이름 문자열만) |
| 확인 결과 | `python grafana/build.py --check` 통과, `pytest` 590 passed·16 skipped — Docker Desktop이 꺼져 있어 InfluxDB·Grafana가 필요한 테스트를 건너뜀(PR CI에서 돈다). 화면은 확인하지 않음. Reviewer 검증 없음(역할 분리 꺼짐) |

## 하향·상향 IMSI 노출 이름, 이상 유형으로 보일 룰, AN-02 후보 (2026-11-27, 브랜치 `fix/imsi-anomaly-kind`)

탐지 쪽 요청(사용자가 전달, 11/27): ① 이름 AN-02 식별 요청 증가 → 상향 IMSI 노출, IMSI 노출(L3-24) → 하향 IMSI 노출 ② 상향 IMSI 노출·하향 IMSI 노출·단말 성능 정보 탈취의 종류를 공격 → 이상 유형 ③ AN-02 후보 공격에서 상향 IMSI 추출(L3-25-OV) 제거. 역할 분리 꺼짐(D208)이라 서브에이전트 없이 진행.

| 구분 | 내용 |
|---|---|
| 한 일 | `grafana/rule-names.json`: L3-24 '#24 하향 IMSI 노출 (Downlink IMSI Extractor)', AN-02 '이상 유형 — 상향 IMSI 노출', 새 키 `shown_as_anomaly` `["L3-24","L3-14"]`·`hidden_candidates` `{"AN-02":["L3-25-OV"]}`, `_설명`. `grafana/build.py`: `CLASS_EXPR` — `kind` `attack`이어도 `shown_as_anomaly` 룰이면 이상 유형(판정 보류 경보는 그대로). 판정 요약 '종류'를 원래 `kind`(attack·anomaly) 대신 같은 계산·색(경보 목록과 맞춤). `candidate_hide_fn()`(Flux `hide_candidates`) — 압축 JSON에서 `"ID",`·`,"ID"`·`"ID"`를 지움 — 후보 공격 표(경보의 rule을 함께 읽음)·판정 근거 값 candidates 행에 씀. Slack 공격 경보 규칙의 거르기 `r.kind == "attack"` → `r.class == "공격"`. 패널·규칙 설명. JSON 다시 생성(관제·알림, 성능 그대로). 테스트: `tests/test_dashboards.py`(이름 둘, 설정 키 검사, 판정 근거 값 쿼리, Slack 규칙), `tests/test_dashboard_flux.py`(탐지 쪽 샘플 raise 5개를 셀 3으로 — 종류: L3-24·L3-14 공격 → 이상 유형, 같은 룰 판정 보류 → 판정 보류, AN-02 → 이상 유형, 셀 1 공격 그대로, 판정 요약 같음 / 후보: AN-02 '후보 없음'·판정 근거 값 `[]`, L3-24 `L3-28-V` 그대로). 문서: CLAUDE.md 4·9·9.1·9.3, README, `docs/dashboard-design.md` 6절 |
| 결정 사항 | **D220** 종류·후보는 화면에서만 바꾼다(레코드·InfluxDB·녹화의 `kind`·`candidates`는 그대로 — 지난 데이터도 같게 보이고, 탐지 엔진이 나중에 `kind`를 바꿔 보내도 `AN-` 아닌 anomaly가 '판정 보류'로 잘못 보이지 않게 룰 ID로 정함). 판정 보류 경보(`kind` anomaly, `cond` `held_count`)는 요청 범위(공격 → 이상 유형)가 아니라 그대로 판정 보류. **Slack 공격 경보도 화면 종류로 골라 L3-24·L3-14 공격은 더 알리지 않는다**(이상 유형은 알리지 않는다는 11/13 결정에 맞춤 — 사용자 확인 필요). 상향 IMSI 노출(AN-02)은 원래 이상 유형이라 종류는 그대로. L3-25-OV 이름은 대응표에 남김(다른 곳에서 오면 이름으로 보이게). 팀 확인: 탐지 쪽 — 탐지 엔진 `kind`를 바꿀지 |
| 확인 결과 | `python grafana/build.py --check` 통과, `pytest` 전체 609 passed(Docker Desktop을 켜고 로컬 InfluxDB·Grafana 포함, 건너뜀 없음). 화면은 보지 않음. Reviewer 검증 없음(역할 분리 꺼짐) |
| 배포 전 AWS 측정 (11/27) | 읽기만, 명령마다 한 번: `query_timing.py --url http://3.39.170.31:3000 --dashboard monitoring --range 7d --parallel`. `--source aws` 18개 통과 — 가장 느린 UE 컨텍스트 0.14초, 경보 목록 0.11초(12행), 판정 요약 0.03초, 판정 근거 값 0.08초, 후보 공격 0.04초, 동시 18개 가장 늦은 응답 0.87초. `--source p4` 18개 통과(최대 0.11초, 동시 0.72초) — p4는 11/20 전 데이터라 최근 7일에 경보가 0건이어서 경보 쿼리는 빈 결과로만 잼. 보고서 초안(Claude 문서) 2.4절 예시 이름을 '하향 IMSI 노출'로 고침 |
