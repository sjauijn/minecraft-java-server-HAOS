#!/bin/bash
set -e

DATA_DIR="${DATA_DIR:-/data}"
CONFIG_FILE="${DATA_DIR}/config/java_for_ha_config.json"
STOP_MARKER="${DATA_DIR}/run/java_server.stopped"

eula="false"
if [ -f "$CONFIG_FILE" ]; then
    eula="$(jq -r '.general.eula // false' "$CONFIG_FILE" 2>/dev/null || echo "false")"
fi

case "${eula,,}" in
    true|1|yes|on)
        if [ -f "${STOP_MARKER}" ]; then
            exit 0
        fi
        ;;
    *)
        exit 0
        ;;
esac

timeout 3s /usr/local/bin/mc-monitor status \
    --host 127.0.0.1 \
    --port "${SERVER_PORT:-25565}" >/dev/null 2>&1 || exit 1
