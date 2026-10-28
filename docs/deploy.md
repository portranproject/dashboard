# AWS 배포 (EC2)

대시보드 스택(InfluxDB + Grafana + collector)을 EC2 한 대에 올리는 절차다. 처음 보는 팀원이 그대로 따라 할 수 있게 쓴다.
범위와 이유는 `docs/progress.md` M7의 결정 D85~D87에 있다.

- **AWS에 올리는 것**: 원격에서 대시보드를 보고, mock·replay 데이터로 시연하고, 평가 리포트를 만드는 용도
- **올리지 않는 것**: 테스트베드 실시간 경로(CU/DU, eBPF 에이전트, 탐지 엔진). 이것들은 테스트베드 LAN에 둔다
- **AWS 데이터는 mock 또는 replay다.** 성능 결과로 쓰지 않는다(CLAUDE.md 12절 7항)

## 구성

```
내 PC 브라우저 ──(TCP 3000, 내 IP만)──> EC2 (Ubuntu 24.04, t3.small, 서울 리전)
                                        └─ docker compose  (docker-compose.yml + docker-compose.aws.yml)
                                           ├─ grafana    0.0.0.0:3000   ← 보안 그룹이 내 IP만 허용
                                           ├─ influxdb   127.0.0.1:8086 ← 서버 안에서만
                                           ├─ collector  127.0.0.1:9999/udp ← 서버 안에서만
                                           └─ tools      (필요할 때 실행: mock, replay, evaluator)
서버 접속: SSH 대신 SSM Session Manager (22번 포트를 열지 않는다)
코드 받기: GitHub 배포 키(읽기 전용)
```

| 항목 | 값 |
|---|---|
| 리전 | 서울 `ap-northeast-2` |
| 인스턴스 | t3.small (2 vCPU, 2GiB) + 스왑 2GiB |
| 디스크 | gp3 30GiB |
| 열린 포트 | TCP 3000 (내 IP만) |
| 배포 브랜치 | CD가 생기기 전 수동 배포는 `dev`, CD 이후는 `main` |

콘솔 메뉴 이름은 한국어 콘솔 기준이고, 괄호 안은 영어 콘솔 이름이다.

---

## 0. 비용 알람 먼저

**Billing and Cost Management → 예산(Budgets) → 예산 생성**
- 템플릿: 월별 비용 예산, 금액은 팀에서 정한 상한, 알림 받을 이메일 입력
- IAM 사용자에게 결제 메뉴 권한이 없으면 계정 관리자에게 부탁한다

인스턴스를 **중지**해도 EBS 디스크와 퍼블릭 IPv4(탄력적 IP) 요금은 계속 나간다. 안 쓰는 기간이 길면 관리자와 상의해 정리한다.

## 1. AWS 콘솔 작업

### 1-1. EC2용 IAM 역할 (Session Manager 접속용)

**IAM → 역할(Roles) → 역할 생성**
1. 신뢰할 수 있는 엔터티 유형: **AWS 서비스**, 사용 사례: **EC2**
2. 권한 정책: **`AmazonSSMManagedInstanceCore`** 하나만
3. 역할 이름: `portran-ec2-ssm`

### 1-2. 보안 그룹

**EC2 → 보안 그룹(Security Groups) → 보안 그룹 생성**
1. 이름: `portran-dashboard`, VPC: 기본 VPC
2. 인바운드 규칙 1개: 유형 **사용자 지정 TCP**, 포트 **3000**, 소스 **내 IP**(My IP), 설명 `Grafana - <이름>`
3. 아웃바운드: 기본값(전체 허용) 그대로

SSH(22), InfluxDB(8086), UDP 9999는 **추가하지 않는다.** 집·학교를 옮기면 내 IP가 바뀌므로 이 규칙의 소스를 다시 "내 IP"로 고친다.

### 1-3. EC2 인스턴스

**EC2 → 인스턴스 → 인스턴스 시작(Launch instances)**

| 항목 | 값 |
|---|---|
| 이름 | `portran-dashboard` |
| AMI | **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type**, 64비트(x86) |
| 인스턴스 유형 | `t3.small` |
| 키 페어 | **키 페어 없이 계속 진행**(Proceed without a key pair). 접속은 Session Manager로 한다 |
| 네트워크 설정 | 기본 VPC, 퍼블릭 IP 자동 할당 **활성화**, 기존 보안 그룹 `portran-dashboard` 선택 |
| 스토리지 | 30 GiB, gp3 |
| 고급 세부 정보 → IAM 인스턴스 프로파일 | `portran-ec2-ssm` |
| 고급 세부 정보 → 메타데이터 버전 | **V2만**(IMDSv2 required) |

### 1-4. 탄력적 IP (주소 고정)

**EC2 → 탄력적 IP(Elastic IPs) → 탄력적 IP 주소 할당** → 만든 주소 선택 → **작업 → 탄력적 IP 주소 연결** → 인스턴스 `portran-dashboard`

이 주소가 대시보드 주소가 된다: `http://<탄력적 IP>:3000`

## 2. 서버 접속 (Session Manager)

**EC2 → 인스턴스 → `portran-dashboard` 선택 → 연결(Connect) → Session Manager 탭 → 연결**

**브라우저 안에** 서버 터미널이 열린다. 이 문서의 서버 명령은 모두 여기서 실행한다. 내 PC의 PowerShell·WSL에서 실행하는 게 아니다(프롬프트가 `PS C:\...>`면 내 PC, `$`나 `root@ip-172-31-...#`면 서버).
아래 명령은 모두 root로 실행한다.

```bash
sudo -i
```

"연결" 버튼이 비활성이면 [문제 해결](#문제-해결)을 본다.

## 3. 서버 준비

### 3-1. 스왑 2GiB (메모리 2GiB에서 이미지 빌드할 때 여유)

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h      # Swap 2.0Gi
```

### 3-2. Docker (공식 저장소)

Ubuntu 기본 패키지(`docker.io`)의 compose는 오래돼서 `docker-compose.aws.yml`의 `!override`를 못 읽는다. Docker 공식 저장소에서 설치한다.

```bash
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

docker compose version   # 2.24.4 이상이어야 한다
```

## 4. 코드 받기 (배포 키)

저장소가 비공개라서 서버가 읽을 수 있는 키가 필요하다. 이 저장소에만, **읽기 전용**으로 붙는 배포 키(deploy key)를 쓴다.

```bash
mkdir -p -m 700 /root/.ssh
ssh-keygen -t ed25519 -N "" -C "portran-ec2-deploy" -f /root/.ssh/portran_deploy
cat >> /root/.ssh/config <<'EOF'
Host github.com
  IdentityFile /root/.ssh/portran_deploy
  IdentitiesOnly yes
EOF
ssh-keyscan -t ed25519 github.com >> /root/.ssh/known_hosts
ssh-keygen -lf /root/.ssh/known_hosts
```

마지막 명령의 지문이 `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`인지 확인한다([GitHub 공식 지문](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)). 다르면 멈추고 팀에 알린다.

공개 키를 GitHub에 등록한다.

```bash
cat /root/.ssh/portran_deploy.pub
```

출력 한 줄을 복사해 **GitHub 저장소 → Settings → Deploy keys → Add deploy key**에 붙인다. 제목은 `portran-ec2`, **Allow write access는 체크하지 않는다.**

```bash
ssh -T git@github.com
# Hi portranproject/dashboard! You've successfully authenticated ... 가 나오면 성공

mkdir -p /opt/portran && cd /opt/portran
git clone git@github.com:portranproject/dashboard.git
cd dashboard
git checkout dev      # CD가 생기기 전 수동 배포는 dev
```

## 5. `.env`와 폴더

**토큰·비밀번호를 예시 값(`change-me`)으로 두지 않는다.** InfluxDB 값은 처음 기동할 때만 적용되므로 기동 **전에** 바꾼다.

```bash
cp .env.example .env
chmod 600 .env
sed -i "s/^INFLUX_TOKEN=.*/INFLUX_TOKEN=$(openssl rand -hex 32)/" .env
sed -i "s/^INFLUX_ADMIN_PASSWORD=.*/INFLUX_ADMIN_PASSWORD=$(openssl rand -hex 16)/" .env
sed -i "s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 16)/" .env
# 이 줄이 있으면 `docker compose ...`가 AWS override까지 함께 읽는다
echo "COMPOSE_FILE=docker-compose.yml:docker-compose.aws.yml" >> .env

grep GRAFANA_ADMIN_PASSWORD .env
```

Grafana 비밀번호는 팀 비밀번호 관리 도구 같은 안전한 곳에 둔다. 채팅방·이슈·커밋에 붙이지 않는다.

컨테이너는 uid 1000으로 돈다. 호스트에 마운트하는 녹화·리포트 폴더의 주인을 맞춘다.

```bash
mkdir -p reports
chown 1000:1000 recordings reports
```

## 6. 기동과 확인

```bash
docker compose up -d --build --wait
docker compose ps        # influxdb (healthy), collector (healthy), grafana 가 running
```

```bash
curl -s localhost:8086/health; echo
curl -s localhost:3000/api/health; echo
set -a; . ./.env; set +a
curl -s -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD" localhost:3000/api/datasources/uid/portran-influxdb/health; echo
docker compose logs --tail 5 collector
```

- InfluxDB: `"status":"pass"`
- Grafana: `"database":"ok"`
- datasource: `"status":"OK"`
- collector: `InfluxDB http://influxdb:8086 bucket=portran`, `입력 udp://0.0.0.0:9999`, 1초마다 `수신 … 저장 … 거부 …`

내 PC 브라우저에서 `http://<탄력적 IP>:3000`에 접속해 `admin` / 위 비밀번호로 로그인한다. **Dashboards → PortRAN** 폴더에 대시보드 2개가 있어야 한다.

## 7. 데이터 넣기 (mock · replay · evaluator)

모두 `tools` 컨테이너로 실행한다. 출력 기본값이 collector 컨테이너(`udp://collector:9999`)로 잡혀 있다. `tools`는 collector를 다시 띄우지 않으므로, 먼저 6절대로 collector가 `(healthy)`인지 확인한다.

아래는 따로따로 쓰는 명령이다. 한 번에 붙여 넣지 말고 필요한 것만 실행한다.

**mock** (10분, 1배속 실시간, 백그라운드)

```bash
docker compose run -d --rm tools python -m mock.generator --duration 600 --seed 42
docker compose logs -f --tail 3 collector     # 수신 N 저장 N 거부 0 이면 정상 (Ctrl+C로 나오기)
```

**replay**: 시각은 지금으로 옮겨 재생한다. collector가 **지금 쓰고 있는** 녹화 파일(가장 최근 `raw-*.jsonl`)을 그대로 재생하면 재생한 메시지가 같은 파일 끝에 다시 녹화되므로, 복사본을 만들어 재생한다. 아래 파일 이름은 예시라 `ls`로 확인한 실제 이름으로 바꾼다.

```bash
ls -l recordings/
cp recordings/raw-20261026-074049.jsonl recordings/mock-seed42.jsonl
docker compose run -d --rm tools python -m replay.replay recordings/mock-seed42.jsonl --speed 1 --retime now
```

실시간 관제의 "데이터 출처"가 **mock 재생**(실제 녹화면 **녹화 재생**)으로 바뀐다.

**evaluator**: mock·replay가 **끝난 뒤** 그 구간을 평가한다. 서버와 컨테이너는 UTC라서 `date`로 시간대가 붙은 시각을 만든다(예: 최근 15분).

```bash
docker compose run --rm tools python -m evaluator.evaluate --from "$(date -d '15 min ago' --iso-8601=seconds)"
ls reports/
```

직접 시각을 쓸 때는 `--from 2026-10-26T16:40:00+09:00`처럼 `+09:00`을 붙인다. `--to`를 빼면 지금까지 평가한다.

collector가 받은 메시지는 `recordings/raw-*.jsonl`로 녹화된다(로컬과 같다).

## 8. 운영

### 다시 작업하러 들어올 때

1. AWS 콘솔 오른쪽 위 리전이 **서울**인지 확인
2. **EC2 → 인스턴스 → `portran-dashboard`** 상태 확인. **중지됨**이면 **인스턴스 상태 → 인스턴스 시작**, 상태 검사 통과까지 2~3분. 탄력적 IP라 주소는 그대로이고 컨테이너는 자동으로 다시 뜬다
3. 2절대로 Session Manager 연결 → 서버 터미널에서:

```bash
sudo -i
cd /opt/portran/dashboard
docker compose ps        # influxdb·collector (healthy), grafana Up
```

### 안 쓸 때

**인스턴스 상태 → 인스턴스 중지**. 컴퓨팅 요금이 멈추고 데이터(디스크)는 남는다. 디스크와 탄력적 IP 요금은 중지해도 계속 나간다(0절). **인스턴스 종료(Terminate)는 서버와 디스크를 지우는 것**이라 누르지 않는다.

### 자주 쓰는 명령

| 할 일 | 명령 (`/opt/portran/dashboard`에서, root) |
|---|---|
| 수동 업데이트 (CD 전) | `git pull && docker compose up -d --build --wait` |
| 수동 업데이트 (CD 후) | `git fetch && git checkout --detach origin/main && bash deploy/server-deploy.sh`. CD가 커밋 단위로 checkout하므로 서버는 브랜치가 아닌 커밋(detached HEAD)에 있다. `git pull`은 쓰지 않는다 |
| 상태 | `docker compose ps` |
| 로그 | `docker compose logs -f collector` (grafana, influxdb도 같음) |
| 재시작 | `docker compose restart collector` |
| 중지 (데이터 유지) | `docker compose down` |

- **`docker compose down -v`는 쓰지 않는다.** InfluxDB 데이터가 전부 지워진다.
- 인스턴스를 재부팅하면 컨테이너는 `restart: unless-stopped`로 자동으로 다시 뜬다.

## 9. CD (자동 배포)

`main`에 push되면(= `dev` → `main` PR 병합) GitHub Actions(`.github/workflows/deploy.yml`)가 서버에 배포한다.

```
GitHub Actions (main)
  │ OIDC 임시 자격 증명 (액세스 키 없음)
  ▼
IAM 역할 portran-github-deploy  ── 할 수 있는 것: 이 인스턴스에서 SSM 문서 portran-deploy 실행, 결과 읽기
  │ ssm:SendCommand (CommitSha = 배포할 커밋)
  ▼
EC2: git fetch → 그 커밋 checkout → deploy/server-deploy.sh (빌드·기동·헬스 체크) → 결과를 Actions 로그로
```

- GitHub에 주는 권한은 "아무 셸 명령 실행"이 아니라 **배포 전용 문서 하나 실행**이다. 문서는 40자리 커밋 SHA만 받는다(`allowedPattern`).
- `portranproject/dashboard`의 **`main`에서 돈 워크플로만** 역할을 받을 수 있다(신뢰 정책의 `sub` 조건).
- 열린 포트는 그대로 Grafana 3000뿐이다. 서버는 배포 키로 GitHub에서 코드를 받는다(D104).
- 설정 JSON은 `deploy/aws/`에 있다. 콘솔에 붙여 넣는 원본이므로 콘솔에서 바꾸면 이 파일도 같이 고친다.

처음 한 번만 아래를 설정한다.

### 9-1. GitHub OIDC 공급자

**IAM → 자격 증명 공급자(Identity providers) → 공급자 추가**
- 공급자 유형: **OpenID Connect**
- 공급자 URL: `https://token.actions.githubusercontent.com`
- 대상(Audience): `sts.amazonaws.com`

### 9-2. SSM 문서 `portran-deploy`

**Systems Manager → 문서(Documents) → 문서 생성 → 명령 또는 세션(Command or Session)**
- 이름: `portran-deploy`, 문서 유형: 명령 문서
- 콘텐츠: **JSON**을 고르고 [`deploy/aws/ssm-document-portran-deploy.json`](../deploy/aws/ssm-document-portran-deploy.json) 내용을 그대로 붙여 넣는다

### 9-3. 배포용 IAM 역할 `portran-github-deploy`

**IAM → 역할 → 역할 생성**
1. 신뢰할 수 있는 엔터티 유형: **사용자 지정 신뢰 정책** → [`deploy/aws/iam-github-deploy-trust.json`](../deploy/aws/iam-github-deploy-trust.json) 붙여 넣기
2. 권한 추가 화면은 아무것도 고르지 않고 다음
3. 역할 이름 `portran-github-deploy` → 역할 생성
4. 만든 역할 → **권한 추가 → 인라인 정책 생성 → JSON** → [`deploy/aws/iam-github-deploy-policy.json`](../deploy/aws/iam-github-deploy-policy.json) 붙여 넣기 → 정책 이름 `portran-deploy-ssm`

신뢰 정책의 `sub`는 `repo:portranproject@<조직 ID>/dashboard@<저장소 ID>:ref:refs/heads/main` 형식이다. 2026-07-15 이후 만든 저장소는 GitHub가 이름 대신 ID가 들어간 형식을 쓴다(조직·저장소 이름을 다른 사람이 다시 가져가도 이 역할을 받을 수 없게). 조직 ID `337596278`, 저장소 ID는 결정 D106에 적었다.

### 9-4. GitHub 저장소 변수

**저장소 Settings → Secrets and variables → Actions → Variables 탭 → New repository variable**. 비밀이 아니므로 Secrets가 아니라 Variables에 넣는다.

| 이름 | 값 |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::409852989722:role/portran-github-deploy` |
| `AWS_REGION` | `ap-northeast-2` |
| `EC2_INSTANCE_ID` | `i-08c7915e4b02d7e3f` |

### 9-5. 배포하기와 확인

- `dev` → `main` PR을 병합하면 **Actions → Deploy**가 돈다. 수동 실행은 Actions → Deploy → Run workflow에서 브랜치 `main`으로 한다(다른 브랜치는 신뢰 정책에서 거부됨).
- 로그의 "서버 배포·헬스 체크 결과"에 서버 출력(`== 배포: <커밋>`, `ok InfluxDB` 등)과 `== 결과: Success`가 나오면 성공이다.
- 배포 뒤 서버는 그 커밋에 detached HEAD로 있다. 손으로 업데이트할 때는 8절의 "CD 후" 명령을 쓴다.

### 9-6. CD가 실패할 때

| 증상 | 확인 |
|---|---|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | 첫 단계 "OIDC 토큰의 sub 확인"에 찍힌 값과 신뢰 정책의 `sub`가 글자 그대로 같은지. `main`이 아닌 브랜치에서 실행했는지 |
| `AccessDeniedException ... ssm:SendCommand` | 인라인 정책의 리전·계정·인스턴스 ID·문서 이름 |
| `InvalidInstanceId` | 인스턴스가 중지됐거나 SSM 에이전트가 오프라인(Session Manager로 접속되는지) |
| `== 결과: Failed` | 로그의 "서버 출력"·"서버 오류 출력". 예: `.env에 COMPOSE_FILE ... 줄이 없습니다`, `실패 Grafana datasource` |

## 문제 해결

**Session Manager "연결" 버튼이 비활성이다**
인스턴스에 IAM 역할 `portran-ec2-ssm`이 붙어 있는지 확인한다(인스턴스 선택 → 작업 → 보안 → IAM 역할 수정). 붙인 직후에는 5~10분 걸릴 수 있고, 그래도 안 되면 인스턴스를 재부팅한다. 퍼블릭 IP가 없으면 SSM 에이전트가 AWS에 접속하지 못한다.

**`yaml: unknown tag !override` 또는 compose 문법 오류**
compose가 2.24.4보다 오래됐다. 3-2절대로 Docker 공식 저장소의 `docker-compose-plugin`을 설치한다.

**collector가 `PermissionError: … recordings/…`로 계속 재시작한다**
`chown 1000:1000 recordings reports`를 하지 않았다. 하고 나서 `docker compose restart collector`.

**대시보드 그래프가 No data인데 "수집 상태"는 몇 초 전에 받았다고 나온다**
노드 목록 같은 변수를 데이터가 들어오기 전에 읽어서 비어 있는 경우다. 대시보드는 새로고침마다 변수를 다시 읽도록 되어 있으니(D103) 몇 초 기다리거나 브라우저를 새로고침(F5)한다.

**브라우저에서 Grafana가 안 열린다**
서버에서 `curl -s localhost:3000/api/health`가 되면 서버는 정상이다. 보안 그룹 인바운드의 소스가 지금 내 IP인지 확인한다(IP가 바뀌었을 수 있음).

**`.env`를 바꿨더니 InfluxDB 인증이 실패한다**
InfluxDB 값은 최초 기동 때만 적용된다. 데이터를 지워도 되면 `docker compose down -v && docker compose up -d --build --wait`. 안 되면 바꾸기 전 값으로 되돌린다.
