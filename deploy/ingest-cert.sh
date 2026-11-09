#!/usr/bin/env bash
# 탐지 엔진 전송기용 /ingest TLS 인증서(자체 서명, 이름 = 대시보드 공인 IP)를 만든다 (M9, docs/deploy.md 10절).
#
#   bash deploy/ingest-cert.sh <공인 IP> [폴더, 기본 certs]
#
# - 개인 키(ingest.key)는 이 서버에만 둔다. 공개 인증서(ingest.crt, PEM)만 탐지 쪽에 보내 전송기 ca_file로 쓴다.
# - 전송기는 인증서 이름(SAN)의 IP와 접속 주소를 늘 검증한다(27_ §3). 그래서 SAN에 공인 IP를 넣는다.
# - 그 IP로 만든 인증서가 이미 있으면 그대로 둔다(배포마다 불러도 됨). IP가 다르면 옛 것을 old-<시각>/으로 옮기고 새로 만든다
#   — 이때는 새 인증서를 탐지 쪽에 다시 보내야 한다.
# - 유효 기간은 INGEST_CERT_DAYS(기본 730일).
set -euo pipefail

ip=${1:?"사용: bash deploy/ingest-cert.sh <공인 IP> [폴더]"}
dir=${2:-certs}
days=${INGEST_CERT_DAYS:-730}

if ! [[ $ip =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "IPv4 주소가 아닙니다: $ip" >&2
  exit 1
fi

crt="$dir/ingest.crt"
key="$dir/ingest.key"

fingerprint() {
  openssl x509 -in "$crt" -noout -fingerprint -sha256 | cut -d= -f2
}

if [[ -f $crt && -f $key ]] && openssl x509 -in "$crt" -noout -text | grep -Eq "IP Address:${ip//./\\.}(,|$)"; then
  echo "  인증서 그대로 사용: $crt (IP $ip, 만료 $(openssl x509 -in "$crt" -noout -enddate | cut -d= -f2), SHA-256 $(fingerprint))"
  exit 0
fi

mkdir -p "$dir"
if [[ -f $crt || -f $key ]]; then
  old="$dir/old-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$old"
  mv -f "$crt" "$key" "$old"/ 2>/dev/null || true
  echo "  이전 인증서를 $old/로 옮겼습니다 (IP가 바뀜)"
fi

# 자체 서명 인증서가 곧 신뢰 기준(CA)이다. 파이썬 3.13+의 엄격한 검증(VERIFY_X509_STRICT)도 통과하도록
# basicConstraints는 critical, keyUsage에 keyCertSign을 넣는다.
umask 077
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -sha256 -nodes -days "$days" \
  -keyout "$key" -out "$crt" -subj "/CN=$ip" \
  -addext "subjectAltName=IP:$ip" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,digitalSignature,keyCertSign" \
  -addext "extendedKeyUsage=serverAuth" 2>/dev/null
chmod 600 "$key"
chmod 644 "$crt"

echo "  새 인증서: $crt (IP $ip, ${days}일, SHA-256 $(fingerprint))"
echo "  아래 PEM을 탐지 쪽에 보낸다(전송기 ca_file). 개인 키 $key는 보내지 않는다."
cat "$crt"
