#!/bin/bash
set -eo pipefail

DATA_DIR="${DATA_DIR:-/data}"

readonly CONFIG_DIR="/config"
WORLDS_DIR="${CONFIG_DIR}/worlds"

if [ ! -d "${DATA_DIR}/server" ]; then
  mkdir -p "${DATA_DIR}/server"
  chmod 0755 "${DATA_DIR}/server"
fi

LINKS=(
  "${DATA_DIR}/server/world:${WORLDS_DIR}"
)

echo "🔗 Checking Java symlinks..."

for entry in "${LINKS[@]}"; do
  target="${entry%%:*}"
  source="${entry##*:}"
  mkdir -p "$(dirname "$target")"
  ln -sfn "$source" "$target"
  echo "  - $target → $source"
done

echo "✨ Symlink check and update complete..."

if [ ! -d "${WORLDS_DIR}" ]; then
  echo "📁 Creating ${WORLDS_DIR}..."
  mkdir -p "${WORLDS_DIR}"
  chmod 0777 "${WORLDS_DIR}"
fi

isTrue() { case "${1,,}" in true|on|1|yes) return 0 ;; *) return 1 ;; esac; }
lower_bool() { case "${1,,}" in true|1|on|yes) echo "true" ;; *) echo "false" ;; esac; }

OPT_FILE="${DATA_DIR}/config/java_for_ha_config.json"
optn() { jq -r "$1 // empty" "$OPT_FILE" 2>/dev/null; }
first_nonempty() { for v in "$@"; do [[ -n "$v" ]] && { echo "$v"; return; }; done; echo ""; }

if [[ ${DEBUG^^} = TRUE ]]; then
  set -x
  echo "DEBUG: running as $(id -a) in $(pwd)"
fi

cd "${DATA_DIR}/server"

export EULA="$(lower_bool "${EULA:-$(optn '.general.eula')}")"
export TYPE="${TYPE:-$(first_nonempty "$(optn '.software.type')" VANILLA)}"
export VERSION="${VERSION:-$(first_nonempty "$(optn '.software.version')" LATEST)}"

export SERVER_NAME="${SERVER_NAME:-$(optn '.general.server_name')}"
export MOTD="${MOTD:-$(first_nonempty "$(optn '.general.motd')" "$SERVER_NAME")}"
export SERVER_PORT="${SERVER_PORT:-$(optn '.general.server_port')}"
export ONLINE_MODE="$(lower_bool "${ONLINE_MODE:-$(optn '.general.online_mode')}")"
export ENABLE_QUERY="$(lower_bool "${ENABLE_QUERY:-$(optn '.general.enable_query')}")"
export QUERY_PORT="${QUERY_PORT:-$(optn '.general.query_port')}"

export LEVEL="${LEVEL:-$(first_nonempty "$(optn '.world.level_name')" world)}"

WORLD_CONFIG_FILE="${DATA_DIR}/worldconfiguration.json"
WORLD_SEED=""
if [[ -f "$WORLD_CONFIG_FILE" ]] && [[ -n "$LEVEL" ]]; then
  if ! WORLD_SEED=$(jq -r --arg world "$LEVEL" '.[$world].seed // empty' "$WORLD_CONFIG_FILE" 2>&1); then
    echo "⚠️ Warning: Failed to parse $WORLD_CONFIG_FILE: $WORLD_SEED"
    WORLD_SEED=""
  fi
fi

if [[ -n "$WORLD_SEED" ]]; then
  export SEED="$WORLD_SEED"
  echo "🌍 Using world-specific seed for '$LEVEL': $SEED"
else
  export SEED="${SEED:-$(optn '.world.level_seed')}"
fi

export LEVEL_TYPE="${LEVEL_TYPE:-$(optn '.world.level_type')}"
export MODE="${MODE:-$(optn '.world.gamemode')}"
export DIFFICULTY="${DIFFICULTY:-$(optn '.world.difficulty')}"
export HARDCORE="$(lower_bool "${HARDCORE:-$(optn '.world.hardcore')}")"
export ALLOW_NETHER="$(lower_bool "${ALLOW_NETHER:-$(first_nonempty "$(optn '.world.allow_nether')" true)}")"
export GENERATE_STRUCTURES="$(lower_bool "${GENERATE_STRUCTURES:-$(first_nonempty "$(optn '.world.generate_structures')" true)}")"
export SPAWN_PROTECTION="${SPAWN_PROTECTION:-$(optn '.world.spawn_protection')}"

export MAX_PLAYERS="${MAX_PLAYERS:-$(optn '.players.max_players')}"
export PVP="$(lower_bool "${PVP:-$(first_nonempty "$(optn '.players.pvp')" true)}")"
export OP_PERMISSION_LEVEL="${OP_PERMISSION_LEVEL:-$(optn '.players.op_permission_level')}"
export ENABLE_WHITELIST="$(lower_bool "${ENABLE_WHITELIST:-$(optn '.players.enable_whitelist')}")"
export PLAYER_IDLE_TIMEOUT="${PLAYER_IDLE_TIMEOUT:-$(optn '.players.player_idle_timeout')}"

export VIEW_DISTANCE="${VIEW_DISTANCE:-$(optn '.performance.view_distance')}"
export SIMULATION_DISTANCE="${SIMULATION_DISTANCE:-$(optn '.performance.simulation_distance')}"
export MAX_TICK_TIME="${MAX_TICK_TIME:-$(optn '.performance.max_tick_time')}"
export SYNC_CHUNK_WRITES="$(lower_bool "${SYNC_CHUNK_WRITES:-$(first_nonempty "$(optn '.performance.sync_chunk_writes')" true)}")"
export MEMORY="${MEMORY:-$(first_nonempty "$(optn '.performance.memory')" 1G)}"
export INIT_MEMORY="${INIT_MEMORY:-$MEMORY}"
export MAX_MEMORY="${MAX_MEMORY:-$MEMORY}"

export ENABLE_RCON="$(lower_bool "${ENABLE_RCON:-$(first_nonempty "$(optn '.rcon.enable_rcon')" true)}")"
export RCON_PORT="${RCON_PORT:-$(first_nonempty "$(optn '.rcon.rcon_port')" 25575)}"
if [[ -z "${RCON_PASSWORD:-}" ]]; then
  RCON_PASSWORD="$(optn '.rcon.rcon_password')"
fi
if [[ -z "${RCON_PASSWORD:-}" ]]; then
  RCON_PASSWORD_FILE_PATH="${DATA_DIR}/.rcon-password"
  if [[ -f "${RCON_PASSWORD_FILE_PATH}" ]]; then
    RCON_PASSWORD="$(cat "${RCON_PASSWORD_FILE_PATH}")"
  else
    RCON_PASSWORD="$(openssl rand -hex 12)"
    echo "${RCON_PASSWORD}" > "${RCON_PASSWORD_FILE_PATH}"
    chmod 600 "${RCON_PASSWORD_FILE_PATH}"
  fi
fi
export RCON_PASSWORD

# ---- ops.json (operators) regenereren vanuit config.players.role_assignments ----

OPS_FILE="${DATA_DIR}/server/ops.json"
WHITELIST_FILE="${DATA_DIR}/server/whitelist.json"

if [[ -f "$OPT_FILE" ]]; then
  tmp_ops="$(mktemp)"
  jq -c '
    .players.role_assignments // [] |
    map(select(.role == "operator")) |
    map({
      uuid: (.uuid // ""),
      name: (.name // ""),
      level: (.op_level // 4),
      bypassesPlayerLimit: (.bypasses_player_limit // false)
    })
  ' "$OPT_FILE" > "$tmp_ops" && mv "$tmp_ops" "$OPS_FILE"
  echo "✅ ops.json regenerated from config.players.role_assignments"

  tmp_wl="$(mktemp)"
  jq -c '
    .players.role_assignments // [] |
    map({
      uuid: (.uuid // ""),
      name: (.name // "")
    })
  ' "$OPT_FILE" > "$tmp_wl" && mv "$tmp_wl" "$WHITELIST_FILE"
  echo "✅ whitelist.json regenerated from config.players.role_assignments"
else
  echo "⚠️ $OPT_FILE not found, skipping ops.json/whitelist.json generation"
fi

PROP_FILE="${DATA_DIR}/server/server.properties"
touch "$PROP_FILE"

if [ -f /etc/mc-property-definitions.json ]; then
  set-property --file "$PROP_FILE" --bulk /etc/mc-property-definitions.json
else
  echo "WARN: /etc/mc-property-definitions.json missing; skipping bulk apply"
fi

echo "🌍 World Configuration:"
echo "   - Name: ${LEVEL:-<not set>}"
echo "   - Seed: ${SEED:-<not set>}"
echo "-------------------------------------------"
echo "📜 server.properties (excerpt):"
echo "-------------------------------------------"
if [ -f "$PROP_FILE" ]; then
  grep -E '^(motd|gamemode|difficulty|level-name|online-mode|server-port|max-players|pvp|hardcore)' "$PROP_FILE" || echo "⚠️ Geen properties gevonden"
else
  echo "⚠️ $PROP_FILE bestaat nog niet!"
fi
echo "-------------------------------------------"

if ! isTrue "${EULA}"; then
  echo
  echo "⚠️ EULA is not accepted (EULA=${EULA:-unset})."
  echo "   Java server will NOT be started."
  echo "   Accept the Minecraft EULA in the add-on UI and restart."
  echo "   See https://www.minecraft.net/eula"
  echo
  tail -f /dev/null
fi

echo "🚀 Resolving and installing Minecraft Java Server (TYPE=${TYPE}, VERSION=${VERSION})..."

export REPLACE_ENV_IN_PLACE=false
export SKIP_DOWNLOAD_DEFAULTS=true
export OVERRIDE_SERVER_PROPERTIES=false
export SKIP_SERVER_PROPERTIES=true

resolve_vanilla() {
  local want="$1"
  local manifest version_id server_url
  manifest="$(curl -fsSL https://launchermeta.mojang.com/mc/game/version_manifest_v2.json)" || return 1

  if [[ "${want^^}" == "LATEST" || -z "$want" ]]; then
    version_id="$(echo "$manifest" | jq -r '.latest.release')"
  elif [[ "${want^^}" == "SNAPSHOT" ]]; then
    version_id="$(echo "$manifest" | jq -r '.latest.snapshot')"
  else
    version_id="$want"
  fi

  local version_url
  version_url="$(echo "$manifest" | jq -r --arg v "$version_id" '.versions[] | select(.id == $v) | .url')"
  if [[ -z "$version_url" || "$version_url" == "null" ]]; then
    echo "❌ Could not find Minecraft version '${version_id}' in Mojang's manifest."
    return 1
  fi

  server_url="$(curl -fsSL "$version_url" | jq -r '.downloads.server.url')"
  if [[ -z "$server_url" || "$server_url" == "null" ]]; then
    echo "❌ No server download available for Minecraft version '${version_id}'."
    return 1
  fi

  curl -fsSL -o "vanilla-server-${version_id}.jar" "$server_url"
}

RESULTS_FILE="$(pwd)/.install-results"
rm -f "$RESULTS_FILE"

run_via_mc_helper() {
  case "${TYPE^^}" in
    VANILLA)
      resolve_vanilla "${VERSION}"
      ;;
    PAPER)
      mc-image-helper install-paper --version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    FABRIC)
      mc-image-helper install-fabric-loader --minecraft-version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    FORGE)
      mc-image-helper install-forge --minecraft-version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    NEOFORGE)
      mc-image-helper install-neoforge --minecraft-version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    QUILT)
      mc-image-helper install-quilt --minecraft-version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    PURPUR)
      mc-image-helper install-purpur --version "${VERSION}" --output-directory . --results-file "${RESULTS_FILE}"
      ;;
    *)
      echo "❌ Unsupported TYPE=${TYPE}. Supported: VANILLA, PAPER, FABRIC, FORGE, NEOFORGE, QUILT, PURPUR."
      return 1
      ;;
  esac
}

if ! run_via_mc_helper; then
  helper_exit=$?
  echo "❌ Failed to install/resolve Minecraft server software for TYPE=${TYPE} VERSION=${VERSION} (exit code ${helper_exit})"
  echo "   Check the Type/Version configuration in the add-on UI."
  tail -f /dev/null
fi

SERVER_JAR=""
if [[ -f "$RESULTS_FILE" ]]; then
  SERVER_JAR="$(grep -E '^SERVER=' "$RESULTS_FILE" | head -n1 | cut -d= -f2-)"
fi
if [[ -z "$SERVER_JAR" ]]; then
  SERVER_JAR="$(find . -maxdepth 1 -iname '*.jar' ! -iname '*installer*' | head -n1)"
fi
if [[ -z "$SERVER_JAR" || ! -e "$SERVER_JAR" ]]; then
  echo "❌ No server jar found after installation step."
  tail -f /dev/null
fi
echo "📦 Using server jar: ${SERVER_JAR}"

JVM_OPTS=""
if [[ "${INIT_MEMORY}" =~ %$ ]]; then
  JVM_OPTS="-XX:InitialRAMPercentage=${INIT_MEMORY%\%} ${JVM_OPTS}"
else
  JVM_OPTS="-Xms${INIT_MEMORY} ${JVM_OPTS}"
fi
if [[ "${MAX_MEMORY}" =~ %$ ]]; then
  JVM_OPTS="-XX:MaxRAMPercentage=${MAX_MEMORY%\%} ${JVM_OPTS}"
else
  JVM_OPTS="-Xmx${MAX_MEMORY} ${JVM_OPTS}"
fi

if [[ -f /opt/Log4jPatcher.jar ]]; then
  JVM_OPTS="-javaagent:/opt/Log4jPatcher.jar ${JVM_OPTS}"
fi

echo "🚀 Starting Java server ${TYPE} ${VERSION}"
echo "   JVM opts: ${JVM_OPTS}"
echo "   Entry point: ${SERVER_JAR}"

if [[ "${SERVER_JAR}" == *.sh ]]; then
  chmod +x "${SERVER_JAR}" 2>/dev/null || true
  export JAVA_OPTS="${JVM_OPTS}"
  exec mc-server-runner --stop-duration 60s "${SERVER_JAR}" nogui
else
  exec mc-server-runner --stop-duration 60s java ${JVM_OPTS} -jar "${SERVER_JAR}" nogui
fi
