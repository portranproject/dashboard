# collector·replay를 돌리는 이미지. AWS(EC2) 배포에서만 쓴다(docker-compose.aws.yml).
# 로컬 개발은 지금처럼 호스트의 venv에서 실행한다(CLAUDE.md 3절).
FROM python:3.14.8-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# 코드는 root 소유(컨테이너에서 읽기만), 실행은 일반 사용자.
# 녹화 폴더는 호스트에 마운트하므로 호스트 쪽 폴더 주인을 uid 1000으로 맞춘다(docs/deploy.md).
RUN useradd --uid 1000 --create-home app
COPY . .
USER app
