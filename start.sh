#!/bin/bash
set -e

FLASK_PORT="${FLASK_PORT:-8790}"
DATA_DIR="${DATA_DIR:-/data}"
RUNTIME_DIR="${DATA_DIR}/run"
JAVA_PID_FILE="${RUNTIME_DIR}/java_server.pid"
STOP_MARKER="${RUNTIME_DIR}/java_server.stopped"
OPTIONS_FILE="${DATA_DIR}/options.json"

get_option() {
    local key="$1"
    if [ -f "${OPTIONS_FILE}" ]; then
        jq -r ".${key} // empty" "${OPTIONS_FILE}" 2>/dev/null || true
    fi
}

start_java_server() {
    echo "🎮 Starting Java server..."
    mkdir -p "${RUNTIME_DIR}"
    rm -f "${STOP_MARKER}"
    /opt/java-entry.sh "$@" &
    local java_pid=$!
    echo "${java_pid}" > "${JAVA_PID_FILE}"
    echo "🧭 Java server PID saved to ${JAVA_PID_FILE}"
}

cleanup_stale_pid() {
    if [[ -f "${JAVA_PID_FILE}" ]]; then
        local pid
        pid="$(cat "${JAVA_PID_FILE}" 2>/dev/null || true)"
        if [[ -n "${pid}" && ! -d "/proc/${pid}" ]]; then
            rm -f "${JAVA_PID_FILE}"
        fi
    fi
}

cd /opt/flask
echo "🚀 Starting Flask webserver on port ${FLASK_PORT}..."
waitress-serve --listen=0.0.0.0:${FLASK_PORT} app:app &

start_java_server "$@"

while true; do
    cleanup_stale_pid
    sleep 5
done
