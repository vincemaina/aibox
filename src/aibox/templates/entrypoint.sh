#!/usr/bin/env bash
#
# aibox container entrypoint.
#
# When the container starts as root (no --user override), retune the `dev` user
# to match HOST_UID / HOST_GID, fix ownership on the persistent volumes, then
# drop privileges via gosu before exec'ing the user's command.
#
# Why this exists: on Linux with Docker Engine (no Docker Desktop), the
# in-container UID becomes the host-side UID on bind-mounted files. If those
# UIDs don't match the host user, you can't edit your own project files from
# the host. macOS/Windows Docker Desktop translates ownership transparently,
# so the chown here is effectively a no-op there but stays harmless.

set -euo pipefail

if [ "$(id -u)" = "0" ]; then
    HOST_UID="${HOST_UID:-1000}"
    HOST_GID="${HOST_GID:-$HOST_UID}"

    current_uid="$(id -u dev)"
    if [ "$current_uid" != "$HOST_UID" ]; then
        groupmod -o -g "$HOST_GID" dev >/dev/null 2>&1 || true
        usermod -o -u "$HOST_UID" -g "$HOST_GID" dev >/dev/null 2>&1 || true
    fi

    chown -R "$HOST_UID:$HOST_GID" /home/dev /opt >/dev/null 2>&1 || true

    exec gosu dev "$@"
fi

# Already non-root (e.g. user passed --user explicitly). Just exec.
exec "$@"
