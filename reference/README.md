# 참고 논문

이 저장소의 지표 정의, 공격 유형, 탐지 규칙, 평가 방식의 근거가 되는 논문이다. 작업 전에 읽는다(CLAUDE.md 0절).

| 파일 | 논문 | 발표 |
|---|---|---|
| [`TeleRAN.pdf`](TeleRAN.pdf) | H. Wen, V. Yegneswaran, P. Porras, A. Gehani, P. Sharma, Z. Lin. *Towards Bridging the Telemetry Gap for Security Applications in 6G OpenRANs via eBPF* (TeleRAN) | FutureG Workshop 2026 (NDSS), [doi:10.14722/futureg.2026.23040](https://dx.doi.org/10.14722/futureg.2026.23040) |
| [`5GSpector.pdf`](5GSpector.pdf) | H. Wen, P. Porras, V. Yegneswaran, A. Gehani, Z. Lin. *5G-Spector: An O-RAN Compliant Layer-3 Cellular Attack Detection Service* | NDSS 2024, [doi:10.14722/ndss.2024.24527](https://dx.doi.org/10.14722/ndss.2024.24527) |

아래 요약은 빠르게 찾아보기 위한 것이다. 근거로 쓸 때는 원문을 확인한다.

## TeleRAN

- **무엇**: 기지국 SW를 고치지 않고 eBPF로 셀룰러 제어 평면 텔레메트리를 뽑는 에이전트. 커널의 eBPF 필터가 F1AP·NGAP 패킷을 골라 eBPF map으로 넘기고, 사용자 공간 파서가 ASN.1로 의미를 복원해 텔레메트리를 만든다. E2SM-KPM 등 O-RAN 표준 인터페이스로 RIC에 보고한다. OAI·srsRAN에 무수정으로 붙였다.
- **텔레메트리 API**: `update_telemetry_cntr("RRC.ConnEstabSucc", 1)` (KPM 카운터), `update_telemetry("s_tmsi", ueid, tmsi)` (UE별 값).
- **Table I — 보안 텔레메트리** (Metadata: C-RNTI·S-TMSI·암호/무결성 알고리즘, State: RRC/NAS 상태·보안 상태·메시지 ID)
- **Table II — 3GPP KPM** (TS 28.552): `RRC.ConnEstabAtt/Succ/FailCause`, `RRC.RelWithoutSuspendConfig`, `UECNTX.ConnEstabAtt/Succ`, `RRC.ReEstabAtt/SuccWithUeContext`, `RRC.ResumeAtt/Succ`, `RRC.ConnMean/Max`, `RRC.InactiveConnMean/Max`
- **보안 활용 예**: RRC/NAS 메시지 ID 순서로 위조 RRC 연결 요청 기반 시그널링 폭주 탐지, 암호·무결성 알고리즘 감시로 다운그레이드(bidding-down) 탐지, KPM의 연결 실패·재수립 급변으로 이상 징후 탐지.

**이 저장소와의 관계**: Table I → eKPM, Table II → 표준 KPM. 이름·코드표는 [`schema/SCHEMA.md`](../schema/SCHEMA.md) 6절, mock 설정은 [`mock/scenarios.yaml`](../mock/scenarios.yaml).

## 5G-Spector

- **무엇**: O-RAN에서 L3(RRC/NAS) 공격을 탐지하는 프레임워크. 제어 계층의 **SecSM**(보안용 E2 서비스 모델 + 에이전트)이 텔레메트리 스트림 **MobiFlow**를 만들고, 앱 계층의 **MobiExpert** xApp이 P-BEST 규칙으로 탐지한다.
- **MobiFlow (Table I)**: 공통 헤더(메시지 타입·ID·시각·보고자) +
  - UE 중심: C-RNTI, S-TMSI/IMEI/IMSI, 암호·무결성 알고리즘, RRC/NAS/보안 상태, RRC/NAS 메시지 ID, RRC/NAS 타이머
  - RAN 중심: MNC·MCC·TAC·CellID, 연결/유휴/최대 UE 수, 타이머
  - UE 상태는 3GPP 상태 기계로 추론하고, RAN 통계는 UE 상태가 바뀔 때 다시 계산한다.
- **규칙 세트 3종**: ① 비정상 수량(카운터가 임계값 초과) ② 비정상 메시지 순서(예: 요청 없는 IdentityResponse) ③ 비정상 상태(예: 보안 수립 후 암호화 없음)
- **대상 공격 7종 (Table II)**: BTS Resource Depletion, Blind DoS, Downlink DoS, Downlink IMSI Extractor, Uplink DoS, Uplink IMSI Extractor, Null Cipher/Integrity. 공격(attack)과 경고(warning) 두 단계로 알린다.
- **평가**: 알려진 7종 + 변형 11종 탐지(각 20회), 실제 트레이스 31개로 오탐 확인(공격 0건, 경고 8건), 무선(OTA) 재현 2종, 탐지 지연(UE 1~3대에서 수백 ms 이내), 오버헤드(RAN·RIC의 CPU·메모리를 기본 구성과 비교, UE 0~3대).

**이 저장소와의 관계**:

| 이 저장소 | 5G-Spector |
|---|---|
| eKPM (TeleRAN Table I) | MobiFlow UE 중심 레코드와 거의 같은 항목 |
| `RRC_SIGNALING_STORM` | BTS Resource Depletion (위조 RRC 연결 대량 생성) |
| `F1AP_MSG_TAMPER`의 알고리즘 다운그레이드 | Null Cipher/Integrity (탐지 신호가 같음: 보안 수립 후 NEA0/NIA0) |
| `ABNORMAL_UE_ATTACH` | Downlink/Uplink DoS 계열 (등록 거절, 인증 실패 패턴) |
| `severity`, 룰셋 | 공격/경고 단계, 규칙 세트 3종 |
| 성능 검증 대시보드 (CLAUDE.md 9.2) | 탐지율, 오탐, 탐지 지연, CPU·메모리 오버헤드 평가 방식 |

**mock의 `RRC_SIGNALING_STORM`은 이 논문의 BTS Resource Depletion을 따른다**: 공격자가 위조 RRC 연결을 잇달아 만들고, 각 연결은 `AuthenticationRequest`까지 진행한 뒤 공격자가 응답하지 않아 코어의 인증 타이머(논문은 LTE T3460, 5G는 T3560)가 끝날 때까지 몇 초간 남았다가 해제된다(transient UE). 그래서 KPM의 연결 시도·성공·연결 UE 수도 크게 오르지만, 어느 UE가 가짜인지는 UE별 텔레메트리(eKPM)로만 알 수 있다. 설정은 `mock/scenarios.yaml`의 `bts_fake_connection`.
