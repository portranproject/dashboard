"""AWS 배포 구성 중 /ingest 앞단(M9) — 인증서 스크립트, compose·nginx 설정.

nginx·compose를 실제로 띄워 보는 확인은 CI의 aws-compose 작업이 한다(.github/workflows/ci.yml).
여기서는 Docker 없이 확인할 수 있는 것만 본다.
"""
import re
import shutil
import socket
import ssl
import subprocess
import threading
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CERT_SCRIPT = REPO_ROOT / "deploy" / "ingest-cert.sh"
NGINX_TEMPLATE = REPO_ROOT / "deploy" / "nginx" / "ingest.conf.template"

needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None or shutil.which("bash") is None,
                                   reason="openssl·bash 없음")


def make_cert(ip, out_dir):
    return subprocess.run(["bash", str(CERT_SCRIPT), ip, str(out_dir)], capture_output=True, text=True, check=False)


def tls_handshake(cert_dir, connect_ip, verify_name, strict=True):
    """cert_dir의 인증서로 TLS 서버를 띄우고, 그 인증서를 ca_file로 쓰는 클라이언트(전송기와 같은 방식)로 접속한다."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert_dir / "ingest.crt", cert_dir / "ingest.key")
    listener = socket.create_server((connect_ip, 0))
    port = listener.getsockname()[1]

    def serve():
        conn, _ = listener.accept()
        try:
            with server_ctx.wrap_socket(conn, server_side=True) as tls:
                tls.recv(1)
        except (ssl.SSLError, OSError):
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    client_ctx = ssl.create_default_context(cafile=str(cert_dir / "ingest.crt"))
    client_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if strict:  # 파이썬 3.13+ 기본값. 전송기가 어느 판이든 통과해야 한다
        client_ctx.verify_flags |= ssl.VERIFY_X509_STRICT
    try:
        with socket.create_connection((connect_ip, port), timeout=5) as raw:
            with client_ctx.wrap_socket(raw, server_hostname=verify_name) as tls:
                tls.sendall(b"x")
                return tls.version()
    finally:
        listener.close()
        t.join(timeout=5)


@needs_openssl
def test_cert_is_accepted_by_strict_python_client(tmp_path):
    result = make_cert("127.0.0.1", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "-----BEGIN CERTIFICATE-----" in result.stdout  # 탐지 쪽에 보낼 PEM을 보여 준다
    assert (tmp_path / "ingest.key").stat().st_mode & 0o077 == 0  # 개인 키는 주인만
    assert tls_handshake(tmp_path, "127.0.0.1", "127.0.0.1") in ("TLSv1.2", "TLSv1.3")


@needs_openssl
def test_cert_for_other_ip_is_rejected(tmp_path):
    assert make_cert("127.0.0.2", tmp_path).returncode == 0
    with pytest.raises(ssl.SSLCertVerificationError):
        tls_handshake(tmp_path, "127.0.0.1", "127.0.0.1")  # 인증서 이름(SAN)의 IP와 접속 주소가 다름


@needs_openssl
def test_cert_is_kept_for_same_ip_and_rotated_for_new_ip(tmp_path):
    assert make_cert("10.0.0.1", tmp_path).returncode == 0
    first = (tmp_path / "ingest.crt").read_bytes()
    again = make_cert("10.0.0.1", tmp_path)
    assert again.returncode == 0 and "그대로 사용" in again.stdout
    assert (tmp_path / "ingest.crt").read_bytes() == first

    changed = make_cert("10.0.0.10", tmp_path)  # 10.0.0.1이 앞부분으로 들어 있어도 다른 IP로 본다
    assert changed.returncode == 0 and "이전 인증서" in changed.stdout
    [old] = tmp_path.glob("old-*")
    assert (old / "ingest.crt").read_bytes() == first
    assert (tmp_path / "ingest.crt").read_bytes() != first


@needs_openssl
@pytest.mark.parametrize("ip", ["", "1.2.3", "example.com", "1.2.3.4; rm -rf /"])
def test_cert_script_rejects_bad_ip(tmp_path, ip):
    result = make_cert(ip, tmp_path)
    assert result.returncode != 0
    assert not (tmp_path / "ingest.crt").exists()


# --------------------------------------------------------------------------- compose·nginx 설정

class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor("!override", lambda loader, node: loader.construct_sequence(node))


@pytest.fixture(scope="module")
def aws_compose():
    return yaml.load((REPO_ROOT / "docker-compose.aws.yml").read_text(encoding="utf-8"), Loader=_ComposeLoader)


def test_ingest_service(aws_compose):
    ingest = aws_compose["services"]["ingest"]
    assert re.fullmatch(r"nginx:\d+\.\d+\.\d+-alpine", ingest["image"])  # 고정 버전 태그 (CLAUDE.md 3절)
    assert ingest["ports"] == ["${INGEST_HTTPS_PORT:-443}:443"]
    assert ingest["depends_on"]["collector"]["condition"] == "service_healthy"
    assert any(v.startswith("./certs:") and v.endswith(":ro") for v in ingest["volumes"])
    # 템플릿이 쓰는 환경변수는 모두 넘기고, .env 전체(토큰 등)는 넘기지 않는다
    used = set(re.findall(r"\$\{([A-Z_]+)\}", NGINX_TEMPLATE.read_text(encoding="utf-8")))
    assert used == set(ingest["environment"])
    assert "env_file" not in ingest


def test_collector_http_port_is_not_published(aws_compose):
    collector = aws_compose["services"]["collector"]
    assert "http://0.0.0.0:${COLLECTOR_HTTP_PORT:-8088}" in collector["command"]
    assert "udp://0.0.0.0:${COLLECTOR_UDP_PORT:-9999}" in collector["command"]
    assert all("COLLECTOR_HTTP_PORT" not in p and "8088" not in p for p in collector["ports"])
    assert all(p.startswith("127.0.0.1:") for p in collector["ports"])


def test_nginx_template_keeps_the_sender_contract():
    conf = NGINX_TEMPLATE.read_text(encoding="utf-8")
    assert "ssl_protocols       TLSv1.2 TLSv1.3;" in conf                 # TLS 1.2 이상 (27_ §3)
    assert "client_max_body_size    ${COLLECTOR_HTTP_MAX_BYTES};" in conf  # 넘으면 413 → 전송기가 나눠 다시
    assert "error_page 502 504 =503 @unavailable;" in conf               # 502·504면 전송기가 멈추므로 503으로
    assert "location = /ingest" in conf and "location = /healthz" in conf
    assert "return 404" in conf                                          # 그 밖의 경로는 막음
    assert "proxy_set_header X-Real-IP $remote_addr;" in conf
    assert "resolver 127.0.0.11" in conf                                 # collector 재생성 뒤 IP 변경 따라감


def test_deploy_scripts_parse():
    if shutil.which("bash") is None:
        pytest.skip("bash 없음")
    for script in (CERT_SCRIPT, REPO_ROOT / "deploy" / "server-deploy.sh"):
        subprocess.run(["bash", "-n", str(script)], check=True)
