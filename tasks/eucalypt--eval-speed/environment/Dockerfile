FROM rust:1.96-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    bc \
    python3 \
    git \
    linux-perf \
    valgrind \
    && rm -rf /var/lib/apt/lists/*

RUN cargo install samply flamegraph rustfilt cargo-show-asm

COPY workspace/ /home/user/workspace/

WORKDIR /home/user/workspace/eucalypt
RUN cargo build --release

RUN useradd --create-home --shell /bin/bash agent \
    && chown -R agent:agent /home/user/workspace/eucalypt \
    && chmod -R a-w /home/user/workspace/workload

# Agent terminal tooling.
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        tmux \
    && rm -rf /var/lib/apt/lists/*

USER agent
WORKDIR /home/user/workspace
