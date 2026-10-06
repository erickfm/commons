# Shared services: the board (MCP over HTTP), mock websites, the egress proxy and the optional logging gateway.
FROM python:3.12-slim
RUN pip install --no-cache-dir mcp==1.30.0 starlette==1.7.0 uvicorn==0.54.0 httpx==0.28.1 \
    && mkdir -p /data && chmod 777 /data
WORKDIR /app
COPY services/ /app/
