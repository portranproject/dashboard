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

echo "== 배포: $(git log --oneline -1)"
docker compose up -d --build --wait --wait-timeout 300
docker image prune -f >/dev/null  # 다시 빌드하면서 남은 이전 이미지 정리

# check <이름> <URL> <찾을 패턴> [curl 옵션...]: 60초까지 다시 시도한다(Grafana는 healthcheck가 없어 --wait가 기다려 주지 않음)
check() {
  local name=$1 url=$2 pattern=$3
  shift 3
  for _ in $(seq 30); do
    if curl -fsS "$@" "$url" 2>/dev/null | grep -Eq "$pattern"; then
      echo "  ok   $name"
      return 0
    fi
    sleep 2
  done
  echo "  실패 $name ($url)" >&2
  return 1
}

echo "== 헬스 체크"
set -a
# shellcheck disable=SC1091
. ./.env
set +a
check "InfluxDB" "http://localhost:${INFLUX_PORT:-8086}/health" '"status": *"pass"'
check "Grafana" "http://localhost:${GRAFANA_PORT:-3000}/api/health" '"database": *"ok"'
check "Grafana datasource" "http://localhost:${GRAFANA_PORT:-3000}/api/datasources/uid/portran-influxdb/health" '"status": *"OK"' \
  -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
echo "== 완료"
