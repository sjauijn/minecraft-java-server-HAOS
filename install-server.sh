#!/bin/bash

set -eo pipefail

readonly DATA_DIR="${DATA_DIR:-/data}"
readonly CONFIG_DIR="/config"
readonly SOFTWARE_DIR="${CONFIG_DIR}/java-server-software"
readonly BIN_DIR="${DATA_DIR}/server"
readonly VERSION_FILE="${DATA_DIR}/.installed-java-version"
readonly TYPE_FILE="${DATA_DIR}/.installed-java-type"

log()      { echo "$*"; }
log_info() { echo "  ℹ️  $*"; }
log_ok()   { echo "  ✅ $*"; }
log_warn() { echo "  ⚠️  $*"; }
log_err()  { echo "  ❌ $*"; }

version_gt() {
    [[ "$1" == "$2" ]] && return 1
    local IFS=.
    local i ver1=($1) ver2=($2)
    for (( i=0; i<${#ver1[@]} || i<${#ver2[@]}; i++ )); do
        local a="${ver1[i]:-0}" b="${ver2[i]:-0}"
        (( 10#$a > 10#$b )) && return 0
        (( 10#$a < 10#$b )) && return 2
    done
    return 1
}

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║   ☕  Minecraft Java Server — Software Install / Upgrade Mode        ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

if [ ! -d "${SOFTWARE_DIR}" ]; then
    log "📁 Creating software directory: ${SOFTWARE_DIR}"
    mkdir -p "${SOFTWARE_DIR}"
    chmod 0777 "${SOFTWARE_DIR}"
    log_ok "Directory created: ${SOFTWARE_DIR}"
fi

if [ ! -d "${BIN_DIR}" ]; then
    log "📁 Creating server binary directory: ${BIN_DIR}"
    mkdir -p "${BIN_DIR}"
    chmod 0755 "${BIN_DIR}"
    log_ok "Directory created: ${BIN_DIR}"
fi

if [ -f "${VERSION_FILE}" ]; then
    INSTALLED_VERSION="$(cat "${VERSION_FILE}" | tr -d '[:space:]')"
else
    INSTALLED_VERSION=""
fi

if [ -f "${TYPE_FILE}" ]; then
    INSTALLED_TYPE="$(cat "${TYPE_FILE}" | tr -d '[:space:]')"
else
    INSTALLED_TYPE=""
fi

if [ -z "${INSTALLED_VERSION}" ]; then
    log_info "Installed Minecraft Java Version: none"
else
    log_info "Installed Minecraft Java Version: ${INSTALLED_VERSION} (${INSTALLED_TYPE:-unknown})"
fi

# Looking for: <type>-server-<version>.jar
# Examples: vanilla-server-1.21.4.jar, paper-server-1.21.4.jar,
#           fabric-server-1.21.4.jar, forge-server-1.21.4.jar
JAR_FILE=""
JAR_VERSION=""
JAR_TYPE=""

shopt -s nullglob
for f in "${SOFTWARE_DIR}"/*-server-*.jar; do
    [ -f "$f" ] || continue
    fname="$(basename "$f")"
    rest="${fname%.jar}"
    type_part="${rest%%-server-*}"
    ver_part="${rest#*-server-}"
    if [[ "$ver_part" =~ ^[0-9]+(\.[0-9]+){1,4}([A-Za-z0-9._-]*)?$ ]]; then
        JAR_FILE="$f"
        JAR_TYPE="${type_part,,}"
        JAR_VERSION="$ver_part"
        break
    fi
done
shopt -u nullglob

# Fallback: plain server.jar with no version info — treat as "custom"
if [ -z "${JAR_FILE}" ]; then
    for f in "${SOFTWARE_DIR}"/server.jar "${SOFTWARE_DIR}"/*.jar; do
        [ -f "$f" ] || continue
        JAR_FILE="$f"
        JAR_TYPE="custom"
        JAR_VERSION="$(date +%Y%m%d%H%M%S)"
        log_warn "Using unversioned jar '$(basename "$f")' — treating as type 'custom', version '${JAR_VERSION}'."
        log_warn "Rename to e.g. vanilla-server-1.21.4.jar to enable proper version tracking."
        break
    done
fi

if [ -z "${JAR_FILE}" ]; then
    echo ""
    echo "┌──────────────────────────────────────────────────────────────────────┐"
    echo "│  📦  No server .jar found in the software directory.                 │"
    echo "│                                                                        │"
    echo "│  Download the Minecraft Java Server jar you want (Vanilla, Paper,     │"
    echo "│  Fabric, Forge, NeoForge, Purpur, Spigot, Quilt, ...) from its        │"
    echo "│  official source, e.g.:                                               │"
    echo "│                                                                        │"
    echo "│     👉  https://www.minecraft.net/download/server  (Vanilla)         │"
    echo "│     👉  https://papermc.io/downloads/paper           (Paper)          │"
    echo "│     👉  https://fabricmc.net/use/server/             (Fabric)         │"
    echo "│                                                                        │"
    echo "│  Rename it to:  <type>-server-<version>.jar                          │"
    echo "│     e.g.  vanilla-server-1.21.4.jar                                  │"
    echo "│     e.g.  paper-server-1.21.4.jar                                    │"
    echo "│                                                                        │"
    echo "│  Upload the .jar file to:                                            │"
    echo "│                                                                        │"
    echo "│     📂  addon_configs/<this-addon>/java-server-software/             │"
    echo "│                                                                        │"
    echo "│  Then restart the add-on to perform the installation.                 │"
    echo "└──────────────────────────────────────────────────────────────────────┘"
    echo ""
    exit 1
fi

log ""
log "🔍 Found package: $(basename "${JAR_FILE}")  (type=${JAR_TYPE}, version=${JAR_VERSION})"

INSTALL_ACTION="none"

if [ -z "${INSTALLED_VERSION}" ]; then
    log "📥 No previous installation detected — performing fresh install…"
    INSTALL_ACTION="install"
elif [ "${JAR_TYPE}" != "${INSTALLED_TYPE}" ]; then
    log "🔁 Server type changed: ${INSTALLED_TYPE:-unknown} → ${JAR_TYPE}"
    INSTALL_ACTION="install"
elif [ "${JAR_TYPE}" = "custom" ]; then
    log "🔁 Custom jar detected — reinstalling unconditionally."
    INSTALL_ACTION="install"
elif version_gt "${JAR_VERSION}" "${INSTALLED_VERSION}"; then
    log "🔼 Upgrade available: ${INSTALLED_VERSION} → ${JAR_VERSION}"
    INSTALL_ACTION="upgrade"
elif version_gt "${INSTALLED_VERSION}" "${JAR_VERSION}"; then
    case "${ALLOW_DOWNGRADE,,}" in
        true|1|yes|on)
            echo ""
            echo "╔══════════════════════════════════════════════════════════════════════╗"
            echo "║                                                                      ║"
            echo "║   ⚠️⚠️⚠️  D O W N G R A D E   W A R N I N G  ⚠️⚠️⚠️                    ║"
            echo "║                                                                      ║"
            echo "║   YOU ARE ABOUT TO DOWNGRADE THE MINECRAFT JAVA SERVER!             ║"
            echo "║                                                                      ║"
            printf  "║   Current version  :  %-47s║\n" "${INSTALLED_VERSION} (${INSTALLED_TYPE})"
            printf  "║   Target version   :  %-47s║\n" "${JAR_VERSION} (${JAR_TYPE})"
            echo "║                                                                      ║"
            echo "║   ⛔  THE INSTALLED SERVER JAR WILL BE REMOVED AND REPLACED.        ║"
            echo "║       Your worlds and configuration will be preserved.               ║"
            echo "║                                                                      ║"
            echo "║   To CANCEL: stop the add-on within the next 30 seconds.            ║"
            echo "║                                                                      ║"
            echo "╚══════════════════════════════════════════════════════════════════════╝"
            echo ""

            for i in 30 29 28 27 26 25 24 23 22 21 20 19 18 17 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1; do
                echo "  ⏳  Downgrade starts in ${i} second(s) — stop the add-on now to cancel..."
                sleep 1
            done

            echo ""
            echo "  🗑️  Countdown complete. Beginning downgrade procedure..."
            echo ""

            log "🗑️  Removing installed server jar: ${BIN_DIR}/server-${INSTALLED_VERSION}.jar"
            rm -f "${BIN_DIR}/server-${INSTALLED_VERSION}.jar" "${BIN_DIR}/server.jar"
            rm -f "${VERSION_FILE}" "${TYPE_FILE}"
            INSTALLED_VERSION=""
            INSTALLED_TYPE=""

            echo ""
            echo "  ✅  Server jar removed. Worlds and config preserved. Proceeding with installation of ${JAR_VERSION}..."
            echo ""

            INSTALL_ACTION="install"
            ;;
        *)
            echo ""
            echo "┌──────────────────────────────────────────────────────────────────────┐"
            echo "│  ⬇️  Downgrade Detected — operation aborted.                          │"
            echo "│                                                                        │"
            printf  "│     Installed : %-55s│\n" "${INSTALLED_VERSION} (${INSTALLED_TYPE})"
            printf  "│     Package   : %-55s│\n" "${JAR_VERSION} (${JAR_TYPE})"
            echo "│                                                                        │"
            echo "│  Downgrading may corrupt worlds. To allow downgrade, enable:          │"
            echo "│     ➜  Allow Downgrade: true   (in add-on Configuration)             │"
            echo "│  WARNING: enabling downgrade will delete the installed server jar!    │"
            echo "└──────────────────────────────────────────────────────────────────────┘"
            echo ""
            exit 1
            ;;
    esac
else
    echo ""
    echo "┌──────────────────────────────────────────────────────────────────────┐"
    echo "│  ✅  Version ${JAR_VERSION} (${JAR_TYPE}) is already installed.       "
    echo "│      No changes have been made to the Java Server software.          │"
    echo "└──────────────────────────────────────────────────────────────────────┘"
    echo ""
    INSTALL_ACTION="skip"
fi

if [ "${INSTALL_ACTION}" = "install" ] || [ "${INSTALL_ACTION}" = "upgrade" ]; then
    echo ""
    if [ "${INSTALL_ACTION}" = "install" ]; then
        echo "┌──────────────────────────────────────────────────────────────────────┐"
        printf "│  📥  Installing Minecraft Java Server %-34s│\n" "${JAR_TYPE} ${JAR_VERSION}"
        echo "└──────────────────────────────────────────────────────────────────────┘"
    else
        echo "┌──────────────────────────────────────────────────────────────────────┐"
        printf "│  🔼  Upgrading: %-55s│\n" "${INSTALLED_VERSION} → ${JAR_VERSION}"
        echo "└──────────────────────────────────────────────────────────────────────┘"
    fi
    echo ""

    if [ "${INSTALL_ACTION}" = "upgrade" ] && [ -n "${INSTALLED_VERSION}" ]; then
        OLD_JAR="${BIN_DIR}/server-${INSTALLED_VERSION}.jar"
        if [ -f "${OLD_JAR}" ]; then
            log_info "Removing old jar: $(basename "${OLD_JAR}")"
            rm -f "${OLD_JAR}"
        fi
    fi

    log "📂 Installing jar to ${BIN_DIR} …"
    cp -a "${JAR_FILE}" "${BIN_DIR}/server-${JAR_VERSION}.jar"
    ln -sfn "${BIN_DIR}/server-${JAR_VERSION}.jar" "${BIN_DIR}/server.jar"
    log_ok "Jar installed as: server-${JAR_VERSION}.jar (symlinked as server.jar)"

    echo "${JAR_VERSION}" > "${VERSION_FILE}"
    echo "${JAR_TYPE}" > "${TYPE_FILE}"

    echo ""
    log_ok "Minecraft Java Server ${JAR_TYPE} ${JAR_VERSION} installed successfully."
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║   🏁  Software Installation / Upgrade process complete.              ║"
echo "║                                                                      ║"
echo "║   To start the Minecraft Java Server:                                ║"
echo "║                                                                      ║"
echo "║     1️⃣   In the add-on Configuration, set                            ║"
echo "║          ┌──────────────────────────────────────┐                    ║"
echo "║          │  Installing/Upgrading Server: false  │                    ║"
echo "║          └──────────────────────────────────────┘                    ║"
echo "║     2️⃣   Restart the add-on.                                         ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
