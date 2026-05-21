FROM python:3.12-slim

# Useful tooling for AI coding agents.
# git and gh are intentionally NOT installed — version control stays on the host.
RUN apt-get update && apt-get install -y --no-install-recommends \
      bash \
      curl \
      ca-certificates \
      build-essential \
      vim \
      nano \
      jq \
      ripgrep \
      fd-find \
      unzip \
      nodejs \
      npm \
    && rm -rf /var/lib/apt/lists/*

# Non-root dev user. Owns its home and /opt so tools installed at runtime persist
# via the named volumes mounted at /home/dev and /opt.
RUN useradd -m -s /bin/bash dev \
    && mkdir -p /home/dev/.npm-global /home/dev/.local /opt \
    && chown -R dev:dev /home/dev /opt

ENV HOME=/home/dev \
    NPM_CONFIG_PREFIX=/home/dev/.npm-global \
    PATH=/home/dev/.npm-global/bin:/home/dev/.local/bin:/opt/bin:$PATH

USER dev
WORKDIR /workspace
CMD ["/bin/bash"]
