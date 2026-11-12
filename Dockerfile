# syntax=docker/dockerfile:1
#
# Two flavours of signal-cli:
#   native (default) - GraalVM binary, fast start, low RAM. x86_64 only.
#   jvm              - Java build on a bundled JRE 25. Works on arm64 (Raspberry Pi etc.).
#                      docker build --target jvm -t signal-web .
#
ARG SIGNAL_CLI_VERSION=0.14.10

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --uid 1000 --create-home signal && mkdir /data && chown signal:signal /data
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM base AS jvm
ARG SIGNAL_CLI_VERSION
COPY --from=eclipse-temurin:25-jre /opt/java/openjdk /opt/java
ENV JAVA_HOME=/opt/java PATH=/opt/java/bin:$PATH
RUN curl -fsSL "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz" \
      | tar xz -C /opt \
 && ln -s "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli
USER signal

FROM base AS native
ARG SIGNAL_CLI_VERSION
RUN curl -fsSL "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux-native.tar.gz" \
      | tar xz -C /usr/local/bin \
 && chmod 755 /usr/local/bin/signal-cli
USER signal
