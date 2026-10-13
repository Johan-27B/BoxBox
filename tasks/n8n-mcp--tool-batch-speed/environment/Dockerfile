FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5

RUN apt-get update && apt-get install -y --no-install-recommends \
    bc \
    build-essential \
    ca-certificates \
    curl \
    linux-perf \
    python3 \
    && rm -rf /var/lib/apt/lists/*

COPY workspace/ /home/user/workspace/

WORKDIR /home/user/workspace/n8n-mcp
RUN cp /home/user/workspace/workload/package-lock.json package-lock.json \
    && HUSKY=0 npm ci --no-audit --no-fund \
    && npm run build

RUN useradd --create-home --shell /bin/bash agent \
    && chown -R agent:agent /home/user/workspace/n8n-mcp \
    && chown -R root:root /home/user/workspace/workload \
    && chmod -R a-w /home/user/workspace/workload

ENV AGENT_MCP=/home/user/workspace/n8n-mcp \
    PORT=3000

# Agent terminal tooling.
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git \
        tmux \
    && rm -rf /var/lib/apt/lists/*

USER agent
WORKDIR /home/user/workspace
