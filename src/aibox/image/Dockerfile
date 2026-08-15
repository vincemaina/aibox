FROM python:3.12-slim

# Useful tooling for AI coding agents.
# git IS installed so agents can clone public repos and install plugins/marketplaces.
# The GitHub CLI (gh) is intentionally NOT installed, and no credentials are mounted,
# so the agent still cannot push to or authenticate against remote repositories.
# The host's .git directory is masked at runtime, so history stays protected.
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
      xz-utils \
      git \
      gosu \
    && rm -rf /var/lib/apt/lists/*

# Node.js from the official distribution rather than Debian's `nodejs` package,
# which is stuck on v20. Claude Code declares `engines: { node: ">=22.0.0" }`, so
# the Debian build installs with an EBADENGINE warning and runs unsupported.
ARG NODE_VERSION=24.19.0
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) node_arch='x64' ;; \
      arm64) node_arch='arm64' ;; \
      *) echo "unsupported architecture: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac; \
    tarball="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    cd /tmp; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"; \
    grep " ${tarball}\$" SHASUMS256.txt | sha256sum -c -; \
    tar -xJf "${tarball}" -C /usr/local --strip-components=1 --no-same-owner \
        --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md; \
    rm -f "${tarball}" SHASUMS256.txt; \
    node --version; \
    npm --version

# Chromium's shared libraries, so agents can drive Playwright and screenshot
# their own UI work. Only the system deps are installed here, not the browser
# binaries: the agent runs `npx playwright install chromium` itself, which needs
# no root and lands in ~/.cache/ms-playwright on the persistent home volume.
#
# This has to happen in the image. Installing the libs needs apt (root), and the
# container drops to `dev` with no sudo, so `playwright install --with-deps` from
# inside is impossible. Without them Chromium dies on launch with a misleading
# "Target page, context or browser has been closed" and the real cause
# (libglib-2.0.so.0: cannot open shared object file) buried in the browser log.
#
# Let Playwright resolve the package names rather than hardcoding them: Debian 13
# renamed most of these in the t64 ABI transition (libasound2 -> libasound2t64,
# and so on), so a hand-written apt list would rot on the next base image bump.
ARG PLAYWRIGHT_VERSION=1.56.0
RUN npx --yes "playwright@${PLAYWRIGHT_VERSION}" install-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

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

# `ENV PATH` alone is not enough: /etc/profile assigns PATH outright, so a login
# shell (`bash -l`, `su -`) drops the entries above and globally-installed tools
# like `claude` vanish. profile.d runs after that assignment, restoring them.
RUN printf '%s\n' \
      'for d in /home/dev/.npm-global/bin /home/dev/.local/bin /opt/bin; do' \
      '    case ":$PATH:" in' \
      '        *":$d:"*) ;;' \
      '        *) PATH="$d:$PATH" ;;' \
      '    esac' \
      'done' \
      'export PATH' \
    > /etc/profile.d/aibox-path.sh

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]
