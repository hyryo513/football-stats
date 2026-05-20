# Minimal MCP example-server image.
# TODO(human): pin base image to a digest at PR time, e.g.
#   FROM python:3.12-slim@sha256:<digest>
FROM python:3.12-slim

ARG VERSION=0.0.0
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="example-server" \
      org.opencontainers.image.description="Example MCP server (echo tool)." \
      org.opencontainers.image.source="https://github.com/hyryo513/football-stats" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

# MCP servers communicate over stdio.
ENTRYPOINT ["example-mcp-server"]
