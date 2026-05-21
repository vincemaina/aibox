FROM python:3.12-slim

# Useful tooling for AI coding agents.
# git and gh are intentionally NOT installed — version control stays on the host.
# gosu is added for privilege dropping in the entrypoint.
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
      gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root dev user. UID/GID may be retuned at container start by entrypoint.sh
# to match the invoking host user.
RUN useradd -m -s /bin/bash dev \
    && mkdir -p /home/dev/.npm-global /home/dev/.local /opt \
    && chown -R dev:dev /home/dev /opt

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV HOME=/home/dev \
    NPM_CONFIG_PREFIX=/home/dev/.npm-global \
    PATH=/home/dev/.npm-global/bin:/home/dev/.local/bin:/opt/bin:$PATH

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]
