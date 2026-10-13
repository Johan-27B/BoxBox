FROM rust@sha256:a5e80efc194cfc8e7453cb27b022f07e6ed212f49fdd4055caf85f8be806538c

COPY workspace/ /home/user/workspace/

ENV PATH="/usr/local/cargo/bin:${PATH}"

WORKDIR /home/user/workspace/ccc
RUN cargo build --release \
    && ./target/release/ccc --version >/dev/null \
    && rm -rf target

RUN useradd --create-home --shell /bin/bash agent \
    && chown -R agent:agent /home/user/workspace/ccc \
    && chmod -R a-w /home/user/workspace/workload

# Agent terminal tooling.
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
        tmux \
    && update-ca-certificates \
    && mkdir -p /usr/lib/ssl \
    && ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem \
    && rm -rf /var/lib/apt/lists/*

USER agent
WORKDIR /home/user/workspace
