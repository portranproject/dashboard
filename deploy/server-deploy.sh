#!/usr/bin/env bash
# EC2에서 실행하는 배포 스크립트. 현재 checkout된 커밋으로 다시 빌드·기동하고 헬스 체크한다.
# CD가 SSM 문서 portran-deploy(deploy/aws/ssm-document-portran-deploy.json)로 커밋을 checkout한 뒤 부른다.
# 손으로도 실행할 수 있다: sudo bash deploy/server-deploy.sh (docs/deploy.md 8·9절)
set -euo pipefail
cd "$(dirname "$0")/.."

# 서버 .env가 AWS override를 쓰는지 확인한다(D96). 빠지면 InfluxDB 포트가 밖으로 열린 기본 구성으로 뜬다
if ! grep -qx 'COMPOSE_FILE=docker-compose.yml:docker-compose.aws.yml' .env; then
  echo ".env에 COMPOSE_FILE=docker-compose.yml:docker-compose.aws.yml 줄이 없습니다 (docs/deploy.md 5절)" >&2
  exit 1
fi

mkdir -p reports
chown 1000:1000 recordings reports

set -a
# shellcheck disable=SC1091
. ./.env
set +a

# EC2 메타데이터(IMDSv2)에서 공인 IP(탄력적 IP)를 읽는다
imds_public_ip() {
  local token
  token=$(curl -fsS -m 2 -X PUT http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 60') || return 1
  curl -fsS -m 2 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/public-ipv4
}

# /ingest TLS 인증서 (M9). 없거나 공인 IP가 바뀌었으면 만든다. 개인 키는 이 서버의 certs/에만 있다(git 제외)
ingest_ip=${INGEST_PUBLIC_IP:-}
if [ -z "$ingest_ip" ]; then
  ingest_ip=$(imds_public_ip) || {
    echo "공인 IP를 알 수 없습니다. .env에 INGEST_PUBLIC_IP=<탄력적 IP>를 넣으세요 (docs/deploy.md 10절)" >&2
    exit 1
  }
fi
echo "== /ingest 인증서"
bash deploy/ingest-cert.sh "$ingest_ip" certs

echo "== 배포: $(git log --oneline -1)"
docker compose up -d --build --wait --wait-timeout 300
docker image prune -f >/dev/null  # 다시 빌드하면서 남은 이전 이미지 정리

# check <이름> <URL> <찾을 패턴> [curl 옵션...]: 60초까지 다시 시도한다(Grafana는 healthcheck가 없어 --wait가 기다려 주지 않음)
# 하나가 실패해도 나머지를 모두 확인하고 맨 끝에서 실패로 끝낸다(어디가 문제인지 한 번에 보이도록)
failed=()
check() {
  local name=$1 url=$2 pattern=$3 status
  shift 3
  for _ in $(seq 30); do
    if curl -fsS "$@" "$url" 2>/dev/null | grep -Eq "$pattern"; then
      echo "  ok   $name"
      return 0
    fi
    sleep 2
  done
  status=$(curl -s -o /dev/null -w '%{http_code}' "$@" "$url" 2>/dev/null || true)
  if [[ -z $status || $status == 000 ]]; then status="연결 실패"; else status="마지막 응답 HTTP $status"; fi
  echo "  실패 $name ($url, $status)" >&2
  failed+=("$name")
}

echo "== 헬스 체크"
check "InfluxDB" "http://localhost:${INFLUX_PORT:-8086}/health" '"status": *"pass"'
check "Grafana" "http://localhost:${GRAFANA_PORT:-3000}/api/health" '"database": *"ok"'
# HTTP 401이면 .env의 GRAFANA_ADMIN_PASSWORD가 Grafana에 실제로 저장된 비밀번호와 다르다(docs/deploy.md 문제 해결)
check "Grafana datasource" "http://localhost:${GRAFANA_PORT:-3000}/api/datasources/uid/portran-influxdb/health" '"status": *"OK"' \
  -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"
# 공인 IP 주소로 검증하되 연결은 이 서버 안으로 보낸다(보안 그룹은 p4 CU 박스만 열어 두므로)
ingest_port=${INGEST_HTTPS_PORT:-443}
check "/ingest (nginx TLS → collector)" "https://$ingest_ip:$ingest_port/healthz" '"status": *"ok"' \
  --cacert certs/ingest.crt --connect-to "$ingest_ip:$ingest_port:127.0.0.1:$ingest_port"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
if (( ${#failed[@]} )); then
  echo "== 헬스 체크 실패: ${failed[*]}" >&2
  exit 1
fi
echo "== 완료"
