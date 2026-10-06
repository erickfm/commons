# Agent sandbox: one container per agent. Inspect runs the CLI inside it as the unprivileged `agent` user.
FROM node:22-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@2.1.290 @openai/codex@0.160.1 && npm cache clean --force
RUN useradd -m agent && mkdir -p /work && chown agent:agent /work
WORKDIR /work
USER agent
