#!/bin/bash
set -e

FLASK_PORT="${FLASK_PORT:-8790}"
DATA_DIR="${DATA_DIR:-/data}"
RUNTIME_DIR="${DATA_DIR}/run"
JAVA_PID_FILE="${RUNTIME_DIR}/java_server.pid"
STOP_MARKER="${RUNTIME_DIR}/java_server.stopped"
OPTIONS_FILE="${DATA_DIR}/options.json"
VERSION_FILE="${DATA_DIR}/.installed-java-version"

get_option() {
    local key="$1"
    if [ -f "${OPTIONS_FILE}" ]; then
        jq -r ".${key} // empty" "${OPTIONS_FILE}" 2>/dev/null || true
    fi
}

check_java_ok() {
    command -v java >/dev/null 2>&1 || return 0
    if java -version >/dev/null 2>&1; then
        return 0
    fi
    echo ""
    echo "❌ Java failed its basic self-check (java -version). This indicates a"
    echo "   broken add-on image. Please rebuild/update the add-on and report this"
    echo "   if it persists."
    echo ""
}

check_java_ok

INSTALL_UPGRADE_MODE="$(get_option 'install_upgrade_server')"
ALLOW_DOWNGRADE="$(get_option 'allow_downgrade')"

case "${ALLOW_DOWNGRADE,,}" in
    true|1|yes|on)
        case "${INSTALL_UPGRADE_MODE,,}" in
            true|1|yes|on)
                ;;
            *)
                echo ""
                echo "╔══════════════════════════════════════════════════════════════════════╗"
                echo "║                                                                      ║"
                echo "║   🚫  CONFIGURATION ERROR — ADD-ON WILL NOT START                   ║"
                echo "║                                                                      ║"
                echo "║   'Allow Downgrade' is set to  true  but                            ║"
                echo "║   'Installing/Upgrading Server' is set to  false.                  ║"
                echo "║                                                                      ║"
                echo "║   Running the server with 'Allow Downgrade' enabled is dangerous.  ║"
                echo "║   Please disable it first:                                          ║"
                echo "║                                                                      ║"
                echo "║     ➜  In the add-on Configuration, set                            ║"
                echo "║        ┌──────────────────────┐                                     ║"
                echo "║        │  Allow Downgrade: false  │                                 ║"
                echo "║        └──────────────────────┘                                     ║"
                echo "║     ➜  Restart the add-on.                                          ║"
                echo "║                                                                      ║"
                echo "╚══════════════════════════════════════════════════════════════════════╝"
                echo ""
                exit 1
                ;;
        esac
        ;;
esac

case "${INSTALL_UPGRADE_MODE,,}" in
    true|1|yes|on)
        echo ""
        echo "═══════════════════════════════════════════════════════════════════════"
        echo "  🔧  Minecraft Java Server Software — Installing / Upgrading Mode"
        echo "═══════════════════════════════════════════════════════════════════════"
        echo ""
        echo "  The add-on is running in software installation / upgrade mode."
        echo "  The Minecraft Java Server will NOT be started in this mode."
        echo ""
        exec env ALLOW_DOWNGRADE="${ALLOW_DOWNGRADE}" /opt/install-server.sh
        ;;
esac

if [ ! -f "${VERSION_FILE}" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║  ❌  Minecraft Java Server software is not installed yet.            ║"
    echo "║                                                                      ║"
    echo "║  In the add-on Configuration, set:                                  ║"
    echo "║     Installing/Upgrading Server: true                               ║"
    echo "║  and restart the add-on to enter installation mode.                 ║"
    echo "║                                                                      ║"
    echo "║  Then upload your <type>-server-<version>.jar to:                  ║"
    echo "║     📂  addon_configs/<this-addon>/java-server-software/           ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
    tail -f /dev/null
fi

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
