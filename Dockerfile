# Retrace 엔진 + 데모 쇼핑몰 공용 이미지 (headless Chromium)
FROM python:3.13-slim

# Chromium · 드라이버 · 한글 폰트 (미러 일시 오류 대비 재시도)
RUN apt-get update \
 && apt-get install -y --no-install-recommends -o Acquire::Retries=5 \
      chromium chromium-driver fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RETRACE_ROOT=/app \
    RETRACE_REPORTS_DIR=/app/reports \
    RETRACE_HEADLESS=1 \
    RETRACE_CHROME_BINARY=/usr/bin/chromium \
    RETRACE_CHROMEDRIVER=/usr/bin/chromedriver \
    RETRACE_CHROME_ARGS="--no-sandbox --disable-dev-shm-usage"

WORKDIR /app

# 런타임 의존성만 (빌드 전용 requirements-build.txt 제외)
COPY engine/requirements.txt engine/requirements.txt
RUN pip install -r engine/requirements.txt

COPY engine/ engine/
COPY demo-shop/ demo-shop/
COPY features/ features/
COPY docker/ docker/

# 비root 실행, 리포트 볼륨 쓰기 가능
RUN useradd --create-home --uid 1000 retrace \
 && mkdir -p /app/reports \
 && chown -R retrace:retrace /app/reports
USER retrace

WORKDIR /app/engine
EXPOSE 5100 5200
CMD ["python", "-m", "retrace.server", "--host", "0.0.0.0"]
