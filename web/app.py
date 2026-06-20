import json
import os
import signal
import subprocess
import time
from copy import deepcopy

from flask import Flask, request, render_template_string, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", "/data")


def _configure_paths(data_dir: str) -> None:
    """Update derived path constants based on the provided data directory."""

    global DATA_DIR, CONFIG_DIR, CONFIG_FILE, WORLDS_DIR, WORLD_CONFIG_FILE
    global RUNTIME_DIR, JAVA_PID_FILE, JAVA_STOP_MARKER, RCON_PASSWORD_FILE

    DATA_DIR = data_dir
    CONFIG_DIR = os.path.join(DATA_DIR, "config")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "java_for_ha_config.json")
    WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
    WORLD_CONFIG_FILE = os.path.join(DATA_DIR, "worldconfiguration.json")
    RUNTIME_DIR = os.path.join(DATA_DIR, "run")
    JAVA_PID_FILE = os.path.join(RUNTIME_DIR, "java_server.pid")
    JAVA_STOP_MARKER = os.path.join(RUNTIME_DIR, "java_server.stopped")
    RCON_PASSWORD_FILE = os.path.join(DATA_DIR, ".rcon-password")


def configure_data_dir(data_dir: str) -> None:
    """Public helper to point runtime paths at a custom data directory.

    Useful for tests where writing to the default ``/data`` path is not
    permitted.
    """

    _configure_paths(data_dir)


_configure_paths(DATA_DIR)

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static",
)
SESSION_COOKIE_NAME = "mcjava_ha_session"

OPS_FILE = "/data/server/ops.json"
WHITELIST_FILE = "/data/server/whitelist.json"
JAVA_ENTRYPOINT = "/opt/java-entry.sh"
JAVA_WORKDIR = "/data/server"
SEND_COMMAND_BIN = "/usr/local/bin/send-command"
JAVA_DEFAULT_PORT = 25565

# ---- Default config (same structure as 'options' in config.yaml) ----
DEFAULT_CONFIG = {
    "general": {
        "server_name": "HomeAssistantJavaServer",
        "motd": "A Minecraft Server powered by Home Assistant",
        "server_port": 25565,
        "online_mode": True,
        "enable_query": False,
        "query_port": 25565,
        "eula": False,
    },
    "software": {
        "type": "VANILLA",
        "version": "LATEST",
    },
    "world": {
        "level_name": "world",
        "level_seed": "",
        "level_type": "minecraft:normal",
        "gamemode": "survival",
        "difficulty": "normal",
        "hardcore": False,
        "allow_nether": True,
        "generate_structures": True,
        "spawn_protection": 16,
    },
    "players": {
        "max_players": 20,
        "pvp": True,
        "op_permission_level": 4,
        "enable_whitelist": False,
        "player_idle_timeout": 0,
        "role_assignments": [],
    },
    "performance": {
        "view_distance": 10,
        "simulation_distance": 10,
        "max_tick_time": 60000,
        "sync_chunk_writes": True,
        "memory": "1G",
    },
    "rcon": {
        "enable_rcon": True,
        "rcon_port": 25575,
        "rcon_password": "",
    },
}

# ---- Helpers ----


def deep_merge(defaults, overrides):
    """Recursively merge two dicts: overrides op defaults."""
    result = deepcopy(defaults)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(WORLDS_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)


def ensure_config_file():
    ensure_dirs()
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, sort_keys=True)


def load_config():
    ensure_config_file()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    return deep_merge(DEFAULT_CONFIG, data)


def save_config(config):
    ensure_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=True)


def list_worlds():
    ensure_dirs()
    worlds = []
    for name in os.listdir(WORLDS_DIR):
        full = os.path.join(WORLDS_DIR, name)
        if os.path.isdir(full) and not name.startswith("."):
            worlds.append(name)
    return sorted(worlds)


def to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ("true", "1", "on", "yes")


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_world_configs():
    """Load world configurations from /data/worldconfiguration.json"""
    if not os.path.exists(WORLD_CONFIG_FILE):
        return {}
    try:
        with open(WORLD_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_world_configs(world_configs):
    ensure_dirs()
    with open(WORLD_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(world_configs, f, indent=2, sort_keys=True)


def get_world_config(world_name):
    world_configs = load_world_configs()
    return world_configs.get(world_name)


def save_world_config(world_name, seed):
    """Save configuration for a specific world.

    A world always stores exactly one seed. If the world already exists but
    does not have a seed yet, the provided seed will be written. Existing
    non-empty seeds are left untouched.
    """
    world_configs = load_world_configs()
    existing = world_configs.get(world_name)
    normalized_seed = seed if seed is not None else ""

    if existing is None:
        world_configs[world_name] = {"name": world_name, "seed": normalized_seed}
        save_world_configs(world_configs)
        app.logger.info(f"World created: name='{world_name}', seed='{normalized_seed}'")
        return True

    current_seed = (existing.get("seed") or "").strip()
    if current_seed:
        return False

    existing["name"] = existing.get("name") or world_name
    existing["seed"] = normalized_seed
    save_world_configs(world_configs)
    app.logger.info(
        "World seed filled: name='%s', seed='%s'", world_name, normalized_seed
    )
    return True


def _read_java_pid():
    try:
        with open(JAVA_PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_java_pid(pid: int):
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(JAVA_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError:
        pass


def _write_stop_marker():
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(JAVA_STOP_MARKER, "w", encoding="utf-8") as f:
            f.write("stopped")
    except OSError:
        pass


def _clear_stop_marker():
    try:
        os.remove(JAVA_STOP_MARKER)
    except FileNotFoundError:
        pass


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cleanup_pid_file() -> "int | None":
    pid = _read_java_pid()
    if pid is not None and not _pid_is_running(pid):
        try:
            os.remove(JAVA_PID_FILE)
        except FileNotFoundError:
            pass
        return None
    return pid


def get_server_status() -> str:
    if os.path.exists(JAVA_STOP_MARKER):
        return "stopped"

    pid = _cleanup_pid_file()
    if pid is not None and _pid_is_running(pid):
        return "running"

    try:
        result = subprocess.run(
            [
                "mc-monitor",
                "status",
                "--host",
                "127.0.0.1",
                "--port",
                str(JAVA_DEFAULT_PORT),
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return "running"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return "stopped"


def start_java_server() -> bool:
    if get_server_status() == "running":
        return False

    try:
        _clear_stop_marker()
        env = os.environ.copy()
        env.setdefault("DATA_DIR", DATA_DIR)
        process = subprocess.Popen(
            [JAVA_ENTRYPOINT],
            cwd=JAVA_WORKDIR if os.path.isdir(JAVA_WORKDIR) else DATA_DIR,
            env=env,
        )
        _write_java_pid(process.pid)
        return True
    except OSError:
        return False


def stop_java_server(timeout_seconds: int = 30) -> bool:
    pid = _cleanup_pid_file()
    if pid is None:
        return False

    try:
        subprocess.run([SEND_COMMAND_BIN, "stop"], check=False)
    except FileNotFoundError:
        pass

    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        if not _pid_is_running(pid):
            _cleanup_pid_file()
            return True
        time.sleep(0.5)

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    time.sleep(1)
    stopped = not _pid_is_running(pid)
    if stopped:
        _cleanup_pid_file()
        _write_stop_marker()
    return stopped


def restart_java_server() -> bool:
    stop_java_server()
    return start_java_server()

# ---- Routes ----
@app.route("/api/server/status", methods=["GET"])
def api_server_status():
    return jsonify({"status": get_server_status()})


@app.route("/api/server/start", methods=["POST"])
def api_server_start():
    started = start_java_server()
    status = get_server_status()
    if started or status == "running":
        return jsonify({"message": "Server started", "status": status})
    return (
        jsonify({"message": "Unable to start server", "status": status}),
        500,
    )


@app.route("/api/server/stop", methods=["POST"])
def api_server_stop():
    stopped = stop_java_server()
    status = get_server_status()
    if stopped or status == "stopped":
        return jsonify({"message": "Server stopped", "status": status})
    return (
        jsonify({"message": "Unable to stop server", "status": status}),
        500,
    )


@app.route("/api/server/restart", methods=["POST"])
def api_server_restart():
    restarted = restart_java_server()
    status = get_server_status()
    if restarted or status == "running":
        return jsonify({"message": "Server restarted", "status": status})
    return (
        jsonify({"message": "Unable to restart server", "status": status}),
        500,
    )


@app.route("/api/ops", methods=["GET"])
def api_ops():
    """
    Read-only endpoint: returns the current contents of ops.json
    as JSON (or [] if missing/invalid), wrapped in an object.
    """
    paths = [OPS_FILE, os.path.join(DATA_DIR, "server", "ops.json")]
    data = []
    error = None
    used_path = None

    try:
        for p in paths:
            if os.path.exists(p):
                used_path = p
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read().strip()

                if not raw:
                    data = []
                else:
                    try:
                        data = json.loads(raw)
                    except Exception as e:
                        error = f"Invalid JSON in {p}: {e}"
                        data = []
                break

        if used_path is None:
            data = []
            error = None

    except Exception as e:
        error = f"Unexpected error reading ops.json: {e}"
        data = []

    return jsonify({
        "ok": error is None,
        "path": used_path,
        "error": error,
        "data": data,
    })


@app.route("/api/whitelist", methods=["GET"])
def api_whitelist():
    """Read-only endpoint: returns the current contents of whitelist.json"""
    paths = [WHITELIST_FILE, os.path.join(DATA_DIR, "server", "whitelist.json")]
    data = []
    error = None
    used_path = None

    try:
        for p in paths:
            if os.path.exists(p):
                used_path = p
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                data = json.loads(raw) if raw else []
                break
    except Exception as e:
        error = f"Unexpected error reading whitelist.json: {e}"
        data = []

    return jsonify({
        "ok": error is None,
        "path": used_path,
        "error": error,
        "data": data,
    })


@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    worlds = list_worlds()
    world_configs = load_world_configs()
    error = None
    message = None

    if request.method == "POST":
        form = request.form
        try:
            # GENERAL
            config["general"]["server_name"] = form.get("server_name", "").strip()
            config["general"]["motd"] = form.get("motd", "").strip()
            config["general"]["server_port"] = to_int(
                form.get("server_port"), DEFAULT_CONFIG["general"]["server_port"]
            )
            config["general"]["online_mode"] = to_bool(form.get("online_mode"))
            config["general"]["enable_query"] = to_bool(form.get("enable_query"))
            config["general"]["query_port"] = to_int(
                form.get("query_port"), DEFAULT_CONFIG["general"]["query_port"]
            )
            config["general"]["eula"] = to_bool(form.get("eula"))

            # SOFTWARE
            config["software"]["type"] = form.get(
                "software_type", DEFAULT_CONFIG["software"]["type"]
            ).strip().upper()
            config["software"]["version"] = form.get(
                "software_version", DEFAULT_CONFIG["software"]["version"]
            ).strip()

            # WORLD
            selected_world = form.get("selected_world", "").strip()
            new_world_name = form.get("new_world_name", "").strip()

            level_seed_input = form.get("level_seed", "").strip()
            config["world"]["level_type"] = form.get(
                "level_type", DEFAULT_CONFIG["world"]["level_type"]
            )
            config["world"]["gamemode"] = form.get(
                "gamemode", DEFAULT_CONFIG["world"]["gamemode"]
            )
            config["world"]["difficulty"] = form.get(
                "difficulty", DEFAULT_CONFIG["world"]["difficulty"]
            )
            config["world"]["hardcore"] = to_bool(form.get("hardcore"))
            config["world"]["allow_nether"] = to_bool(form.get("allow_nether"))
            config["world"]["generate_structures"] = to_bool(
                form.get("generate_structures")
            )
            config["world"]["spawn_protection"] = to_int(
                form.get("spawn_protection"),
                DEFAULT_CONFIG["world"]["spawn_protection"],
            )

            if new_world_name:
                world_dir = os.path.join(WORLDS_DIR, new_world_name)
                world_exists = os.path.exists(world_dir)
                if world_exists:
                    raise ValueError(
                        f"World '{new_world_name}' already exists. Choose a unique name or select it from the list."
                    )

                os.makedirs(world_dir, exist_ok=True)
                save_world_config(new_world_name, level_seed_input)
                world_configs[new_world_name] = {"name": new_world_name, "seed": level_seed_input}
                if new_world_name not in worlds:
                    worlds.append(new_world_name)
                    worlds.sort()

                config["world"]["level_name"] = new_world_name
                config["world"]["level_seed"] = level_seed_input
            elif selected_world:
                config["world"]["level_name"] = selected_world
                world_cfg = world_configs.get(selected_world)
                existing_seed = ""
                if world_cfg:
                    existing_seed = world_cfg.get("seed", "") or ""

                filled_seed_input = form.get("existing_world_seed", "").strip()
                seed_to_use = existing_seed or filled_seed_input or config["world"].get("level_seed", "")

                if seed_to_use or existing_seed:
                    if save_world_config(selected_world, seed_to_use):
                        world_configs[selected_world] = {"name": selected_world, "seed": seed_to_use}
                config["world"]["level_seed"] = seed_to_use
            else:
                if not config["world"].get("level_name"):
                    config["world"]["level_name"] = DEFAULT_CONFIG["world"]["level_name"]
                if not config["world"].get("level_seed"):
                    config["world"]["level_seed"] = DEFAULT_CONFIG["world"]["level_seed"]

            # PLAYERS
            config["players"]["max_players"] = to_int(
                form.get("max_players"), DEFAULT_CONFIG["players"]["max_players"]
            )
            config["players"]["pvp"] = to_bool(form.get("pvp"))
            config["players"]["op_permission_level"] = to_int(
                form.get("op_permission_level"),
                DEFAULT_CONFIG["players"]["op_permission_level"],
            )
            config["players"]["enable_whitelist"] = to_bool(
                form.get("enable_whitelist")
            )
            config["players"]["player_idle_timeout"] = to_int(
                form.get("player_idle_timeout"),
                DEFAULT_CONFIG["players"]["player_idle_timeout"],
            )

            ra_raw = form.get("role_assignments_json", "").strip()
            if ra_raw:
                config["players"]["role_assignments"] = json.loads(ra_raw)
            else:
                config["players"]["role_assignments"] = []

            # PERFORMANCE
            config["performance"]["view_distance"] = to_int(
                form.get("view_distance"),
                DEFAULT_CONFIG["performance"]["view_distance"],
            )
            config["performance"]["simulation_distance"] = to_int(
                form.get("simulation_distance"),
                DEFAULT_CONFIG["performance"]["simulation_distance"],
            )
            config["performance"]["max_tick_time"] = to_int(
                form.get("max_tick_time"),
                DEFAULT_CONFIG["performance"]["max_tick_time"],
            )
            config["performance"]["sync_chunk_writes"] = to_bool(
                form.get("sync_chunk_writes")
            )
            config["performance"]["memory"] = form.get(
                "memory", DEFAULT_CONFIG["performance"]["memory"]
            ).strip()

            # RCON
            config["rcon"]["enable_rcon"] = to_bool(form.get("enable_rcon"))
            config["rcon"]["rcon_port"] = to_int(
                form.get("rcon_port"), DEFAULT_CONFIG["rcon"]["rcon_port"]
            )
            rcon_password_input = form.get("rcon_password", "").strip()
            if rcon_password_input:
                config["rcon"]["rcon_password"] = rcon_password_input

            save_config(config)
            message = "Configuration saved. Restart the add-on to apply changes."

        except Exception as exc:
            error = f"Error while saving configuration: {exc}"

    role_assignments_json = json.dumps(
        config["players"].get("role_assignments", []), indent=2
    )
    role_assignments_list = config["players"].get("role_assignments", [])

    current_world = config["world"].get("level_name") or DEFAULT_CONFIG["world"][
        "level_name"
    ]
    if current_world and current_world not in worlds:
        worlds.append(current_world)
        worlds.sort()

    current_world_exists = current_world and os.path.exists(os.path.join(WORLDS_DIR, current_world))

    if current_world_exists and current_world not in world_configs:
        current_seed = config["world"].get("level_seed", "")
        if save_world_config(current_world, current_seed):
            world_configs[current_world] = {"name": current_world, "seed": current_seed}

    return render_template_string(
        TEMPLATE,
        config=config,
        worlds=worlds,
        current_world=current_world,
        current_world_exists=current_world_exists,
        world_configs=world_configs,
        role_assignments_json=role_assignments_json,
        role_assignments=role_assignments_list,
        message=message,
        error=error,
    )


# ---- Template met Bootstrap 5.2.3 ----

TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Minecraft Java Server for HA</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="static/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light">
<nav class="navbar navbar-dark bg-dark border-bottom border-secondary mb-3">
  <div class="container-fluid">
    <div class="d-flex flex-column flex-lg-row align-items-lg-center gap-1 gap-lg-3">
      <span class="navbar-brand mb-0 h1">Minecraft Java Server for Home Assistant</span>
      <span class="text-muted small">Configure Java server settings via Ingress</span>
    </div>
    <div class="d-flex align-items-center gap-2 flex-wrap">
      <span id="server_status_badge" class="badge bg-secondary text-uppercase">Loading...</span>
      <small id="server_status_text" class="text-muted"></small>
    </div>
  </div>
</nav>

<div class="container pb-5">
    {% if message %}
        <div class="alert alert-success alert-sm" role="alert">
          {{ message }}
        </div>
    {% endif %}
    {% if error %}
        <div class="alert alert-danger alert-sm" role="alert">
          {{ error }}
        </div>
    {% endif %}
    {% if not config.general.eula %}
        <div class="alert alert-warning alert-sm" role="alert">
          <strong>EULA not accepted.</strong>
          The Java server will <strong>not</strong> start until you accept the
          <a href="https://www.minecraft.net/eula" target="_blank" class="alert-link">
            Minecraft EULA
          </a>
          and restart the add-on.
        </div>
    {% endif %}

  <form method="post" class="row g-3">
    <!-- General -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>General</strong>
        </div>
        <div class="card-body">
          <div class="mb-3">
            <label for="server_name" class="form-label">Server name</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="server_name" name="server_name"
                   value="{{ config.general.server_name }}">
          </div>
          <div class="mb-3">
            <label for="motd" class="form-label">MOTD</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="motd" name="motd"
                   value="{{ config.general.motd }}">
          </div>
          <div class="mb-3">
            <label for="server_port" class="form-label">Server port</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="server_port" name="server_port"
                   value="{{ config.general.server_port }}">
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="online_mode" name="online_mode"
                   {% if config.general.online_mode %}checked{% endif %}>
            <label class="form-check-label" for="online_mode">Online mode (Mojang authentication)</label>
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="enable_query" name="enable_query"
                   {% if config.general.enable_query %}checked{% endif %}>
            <label class="form-check-label" for="enable_query">Enable query protocol</label>
          </div>
          <div class="mb-3">
            <label for="query_port" class="form-label">Query port</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="query_port" name="query_port"
                   value="{{ config.general.query_port }}">
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="eula" name="eula"
                  {% if config.general.eula %}checked{% endif %}>
            <label class="form-check-label" for="eula">
              I agree to the Minecraft EULA
              <a href="https://www.minecraft.net/eula" target="_blank" rel="noreferrer" class="link-light">
                (view EULA)
              </a>
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- Software -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>Server software</strong>
        </div>
        <div class="card-body">
          <div class="mb-3">
            <label for="software_type" class="form-label">Type</label>
            <select class="form-select form-select-sm bg-black text-light" id="software_type" name="software_type">
              {% for val,label in [("VANILLA","Vanilla"),("PAPER","Paper"),("SPIGOT","Spigot"),("FABRIC","Fabric"),("FORGE","Forge"),("NEOFORGE","NeoForge"),("QUILT","Quilt"),("PURPUR","Purpur"),("FOLIA","Folia")] %}
                <option value="{{ val }}" {% if config.software.type == val %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="mb-3">
            <label for="software_version" class="form-label">Version</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="software_version" name="software_version"
                   value="{{ config.software.version }}" placeholder="e.g. 1.21.4 or LATEST">
            <div class="form-text text-muted">Use "LATEST" for the newest stable release.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- World -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>World</strong>
        </div>
        <div class="card-body">
          <div class="d-flex align-items-end gap-3 mb-3">
            <div class="flex-grow-1">
              <label for="selected_world" class="form-label">Existing world</label>
              <select class="form-select form-select-sm bg-black text-light" id="selected_world" name="selected_world">
                <option value="">-- Select world --</option>
                {% for w in worlds %}
                  <option value="{{ w }}" {% if current_world == w %}selected{% endif %}>{{ w }}</option>
                {% endfor %}
              </select>
              <div class="form-text text-muted">Select an existing world folder from /data/worlds.</div>
            </div>
            <div class="text-end">
              <button type="button" class="btn btn-outline-light btn-sm" data-bs-toggle="modal" data-bs-target="#newWorldModal">
                Create new world
              </button>
              <div class="form-text text-muted">Choose name &amp; seed in popup.</div>
            </div>
          </div>

          <div id="new_world_summary" class="alert alert-info py-2 px-3 small d-none"></div>

          {% set current_world_has_seed = world_configs.get(current_world, {}).get('seed') or config.world.level_seed %}
          <div class="mb-3">
            <label for="current_world_seed" class="form-label">Current world seed</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="current_world_seed" name="existing_world_seed" value="{{ config.world.level_seed }}" data-default-seed="{{ config.world.level_seed }}" {% if current_world_has_seed %}readonly{% endif %}>
            <div id="current_world_seed_help" class="form-text {% if current_world_has_seed %}text-muted{% else %}text-warning{% endif %}">
              {% if current_world_has_seed %}
                Seed is stored for this world and cannot be changed. Create a new world to use a different seed.
              {% else %}
                No seed stored yet. Enter a seed to save it for this world (one seed per world).
              {% endif %}
            </div>
          </div>

          <input type="hidden" id="new_world_name" name="new_world_name" value="">
          <input type="hidden" id="level_seed" name="level_seed" value="">
          <div class="mb-3">
            <label for="level_type" class="form-label">Level type</label>
            <select class="form-select form-select-sm bg-black text-light" id="level_type" name="level_type">
              {% for val,label in [("minecraft:normal","Default"),("minecraft:flat","Flat (Superflat)"),("minecraft:large_biomes","Large biomes"),("minecraft:amplified","Amplified")] %}
                <option value="{{ val }}" {% if config.world.level_type == val %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="mb-3">
            <label for="gamemode" class="form-label">Gamemode</label>
            <select class="form-select form-select-sm bg-black text-light" id="gamemode" name="gamemode">
              {% for val,label in [("survival","Survival"),("creative","Creative"),("adventure","Adventure"),("spectator","Spectator")] %}
                <option value="{{ val }}" {% if config.world.gamemode == val %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="mb-3">
            <label for="difficulty" class="form-label">Difficulty</label>
            <select class="form-select form-select-sm bg-black text-light" id="difficulty" name="difficulty">
              {% for val,label in [("peaceful","Peaceful"),("easy","Easy"),("normal","Normal"),("hard","Hard")] %}
                <option value="{{ val }}" {% if config.world.difficulty == val %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="hardcore" name="hardcore"
                   {% if config.world.hardcore %}checked{% endif %}>
            <label class="form-check-label" for="hardcore">Hardcore mode</label>
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="allow_nether" name="allow_nether"
                   {% if config.world.allow_nether %}checked{% endif %}>
            <label class="form-check-label" for="allow_nether">Allow Nether</label>
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="generate_structures" name="generate_structures"
                   {% if config.world.generate_structures %}checked{% endif %}>
            <label class="form-check-label" for="generate_structures">Generate structures</label>
          </div>
          <div class="mb-3">
            <label for="spawn_protection" class="form-label">Spawn protection radius</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="spawn_protection" name="spawn_protection"
                   value="{{ config.world.spawn_protection }}">
          </div>
        </div>
      </div>
    </div>

    <!-- Players -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>Players</strong>
        </div>
        <div class="card-body">
          <div class="mb-3">
            <label for="max_players" class="form-label">Max players</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="max_players" name="max_players"
                   value="{{ config.players.max_players }}">
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="pvp" name="pvp"
                   {% if config.players.pvp %}checked{% endif %}>
            <label class="form-check-label" for="pvp">Enable PvP</label>
          </div>
          <div class="mb-3">
            <label for="op_permission_level" class="form-label">Operator permission level</label>
            <select class="form-select form-select-sm bg-black text-light" id="op_permission_level" name="op_permission_level">
              {% for val in [1,2,3,4] %}
                <option value="{{ val }}" {% if config.players.op_permission_level == val %}selected{% endif %}>{{ val }}</option>
              {% endfor %}
            </select>
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="enable_whitelist" name="enable_whitelist"
                   {% if config.players.enable_whitelist %}checked{% endif %}>
            <label class="form-check-label" for="enable_whitelist">Enable whitelist</label>
          </div>
          <div class="mb-3">
            <label for="player_idle_timeout" class="form-label">Idle timeout (minutes)</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="player_idle_timeout" name="player_idle_timeout"
                   value="{{ config.players.player_idle_timeout }}">
          </div>

          <input type="hidden"
                id="role_assignments_json"
                name="role_assignments_json"
                value="{{ role_assignments_json|e }}">

          <div class="mb-3">
            <div class="d-flex justify-content-between align-items-center">
              <label class="form-label mb-0">Configured operators / whitelist</label>
              <button type="button"
                      class="btn btn-sm btn-success"
                      onclick="openAddModal()">
                + Add player
              </button>
            </div>
            <div class="form-text text-muted">
              Use "+ Add player" to add entries. Role "Operator" grants admin rights via <code>ops.json</code>;
              any entry here is also written to <code>whitelist.json</code> when the whitelist is enabled.
            </div>

            <table class="table table-sm table-dark table-striped mt-2 mb-0" id="ra_table">
              <thead>
                <tr>
                  <th style="width: 60%;">Player</th>
                  <th style="width: 20%;">Role</th>
                  <th style="width: 20%;"></th>
                </tr>
              </thead>
              <tbody>
              </tbody>
            </table>
          </div>

          <div class="mb-3">
            <label class="form-label">Runtime operators (ops.json)</label>
            <div class="form-text text-muted mb-1">
              This shows how the Java server currently sees operators. It may diverge from the configured list during play.
            </div>

            <table class="table table-sm table-dark table-striped mb-0" id="runtime_ops_table">
              <thead>
                <tr>
                  <th style="width: 40%;">Name</th>
                  <th style="width: 30%;">UUID</th>
                  <th style="width: 30%;">Level</th>
                </tr>
              </thead>
              <tbody>
              </tbody>
            </table>
          </div>

        </div>
      </div>
    </div>

    <!-- Performance -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>Performance</strong>
        </div>
        <div class="card-body">
          <div class="mb-3">
            <label for="view_distance" class="form-label">View distance</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="view_distance" name="view_distance"
                   value="{{ config.performance.view_distance }}">
          </div>
          <div class="mb-3">
            <label for="simulation_distance" class="form-label">Simulation distance</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="simulation_distance" name="simulation_distance"
                   value="{{ config.performance.simulation_distance }}">
          </div>
          <div class="mb-3">
            <label for="max_tick_time" class="form-label">Max tick time (ms)</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="max_tick_time" name="max_tick_time"
                   value="{{ config.performance.max_tick_time }}">
          </div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="sync_chunk_writes" name="sync_chunk_writes"
                   {% if config.performance.sync_chunk_writes %}checked{% endif %}>
            <label class="form-check-label" for="sync_chunk_writes">Sync chunk writes</label>
          </div>
          <div class="mb-3">
            <label for="memory" class="form-label">Memory (e.g. 1G, 2048M)</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="memory" name="memory"
                   value="{{ config.performance.memory }}">
          </div>
        </div>
      </div>
    </div>

    <!-- RCON -->
    <div class="col-12 col-lg-6">
      <div class="card bg-dark border-secondary">
        <div class="card-header border-secondary">
          <strong>RCON</strong>
        </div>
        <div class="card-body">
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="enable_rcon" name="enable_rcon"
                   {% if config.rcon.enable_rcon %}checked{% endif %}>
            <label class="form-check-label" for="enable_rcon">Enable RCON</label>
          </div>
          <div class="mb-3">
            <label for="rcon_port" class="form-label">RCON port</label>
            <input type="number" class="form-control form-control-sm bg-black text-light" id="rcon_port" name="rcon_port"
                   value="{{ config.rcon.rcon_port }}">
          </div>
          <div class="mb-3">
            <label for="rcon_password" class="form-label">RCON password (leave blank to keep current)</label>
            <input type="password" class="form-control form-control-sm bg-black text-light" id="rcon_password" name="rcon_password"
                   placeholder="••••••••" autocomplete="new-password">
            <div class="form-text text-muted">If left blank, a password is generated automatically on first start.</div>
          </div>
        </div>
      </div>
    </div>

    <div class="col-12 d-flex justify-content-end mt-2">
      <button type="submit" class="btn btn-success btn-sm px-4">Save configuration</button>
    </div>
  </form>
</div>

<!-- Modal: create new world -->
<div class="modal fade" id="newWorldModal" tabindex="-1" aria-labelledby="newWorldModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content bg-dark text-light border-secondary">
      <div class="modal-header border-secondary">
        <h5 class="modal-title" id="newWorldModalLabel">Create new world</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3">
          <label for="new_world_name_modal" class="form-label">World name</label>
          <input type="text" class="form-control form-control-sm bg-black text-light" id="new_world_name_modal" placeholder="e.g. MyNewWorld">
          <div class="form-text text-muted">A folder will be created under <code>/data/worlds/&lt;name&gt;</code>.</div>
        </div>
        <div class="mb-3">
          <label for="level_seed_modal" class="form-label">Seed (optional)</label>
          <input type="text" class="form-control form-control-sm bg-black text-light" id="level_seed_modal" placeholder="Leave empty for a random seed">
          <div class="form-text text-muted">Seed is stored when the world is created and cannot be changed later.</div>
        </div>
      </div>
      <div class="modal-footer border-secondary">
        <button type="button" class="btn btn-outline-light btn-sm" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-success btn-sm" onclick="saveNewWorldFromModal()">Create world</button>
      </div>
    </div>
  </div>
</div>

<!-- Modal voor toevoegen/bewerken van players -->
<div class="modal fade" id="permissionsModal" tabindex="-1" aria-labelledby="permissionsModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content bg-dark text-light border-secondary">
      <div class="modal-header border-secondary">
        <h5 class="modal-title" id="permissionsModalLabel">Manage operators / whitelist</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <form id="permissionsForm" onsubmit="return false;">
          <input type="hidden" id="edit_index" value="-1">

          <div class="mb-3">
            <label for="perm_name" class="form-label">Player name</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="perm_name" placeholder="Player name">
          </div>

          <div class="mb-3">
            <label for="perm_uuid" class="form-label">UUID</label>
            <input type="text" class="form-control form-control-sm bg-black text-light" id="perm_uuid" placeholder="e.g. 069a79f4-44e9-4726-a5be-fca90e38aaf5">
          </div>

          <div class="mb-3">
            <label for="perm_role" class="form-label">Role</label>
            <select class="form-select form-select-sm bg-black text-light" id="perm_role">
              <option value="member">Member (whitelist only)</option>
              <option value="operator">Operator</option>
            </select>
          </div>
        </form>
      </div>
      <div class="modal-footer border-secondary">
        <button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-sm btn-success" onclick="savePermissionFromModal()">Save</button>
      </div>
    </div>
  </div>
</div>

<!-- Bootstrap JS -->
<script src="static/bootstrap.bundle.min.js"></script>
<script>
  let roleAssignments = {{ role_assignments|tojson }};
  const worldConfigs = {{ world_configs|tojson }};

  const serverStatusBadge = document.getElementById('server_status_badge');
  const serverStatusText = document.getElementById('server_status_text');

  function setServerStatus(status, message = '') {
    const normalized = (status || '').toLowerCase();
    const isRunning = normalized === 'running';
    if (serverStatusBadge) {
      serverStatusBadge.textContent = isRunning ? 'Running' : 'Stopped';
      serverStatusBadge.className = `badge text-uppercase ${isRunning ? 'bg-success' : 'bg-secondary'}`;
    }

    if (serverStatusText) {
      serverStatusText.textContent = message;
    }
  }

  async function fetchServerStatus() {
    try {
      const response = await fetch('api/server/status');
      const data = await response.json();
      setServerStatus(data.status, '');
    } catch (err) {
      console.error('Failed to load server status', err);
      setServerStatus('stopped', 'Unable to load server status');
    }
  }

  document.addEventListener('DOMContentLoaded', fetchServerStatus);

  function clearNewWorldSelection() {
    const summary = document.getElementById('new_world_summary');
    const nameField = document.getElementById('new_world_name');
    const seedField = document.getElementById('level_seed');
    nameField.value = '';
    seedField.value = '';
    if (summary) {
      summary.classList.add('d-none');
      summary.textContent = '';
    }
  }

  function updateCurrentSeedDisplay(worldName) {
    const seedDisplay = document.getElementById('current_world_seed');
    const seedHelp = document.getElementById('current_world_seed_help');
    if (!seedDisplay) return;
    const worldInfo = worldConfigs[worldName] || {};
    const seedValue = worldInfo.seed || '';
    const hasSeed = seedValue.length > 0;

    if (hasSeed) {
      seedDisplay.value = seedValue;
      seedDisplay.readOnly = true;
      seedDisplay.classList.remove('text-warning');
      if (seedHelp) {
        seedHelp.textContent = 'Seed is stored for this world and cannot be changed. Create a new world to use a different seed.';
        seedHelp.classList.remove('text-warning');
        seedHelp.classList.add('text-muted');
      }
      return;
    }

    seedDisplay.readOnly = false;
    seedDisplay.value = '';
    if (seedHelp) {
      seedHelp.textContent = 'No seed stored yet. Enter a seed to save it for this world (one seed per world).';
      seedHelp.classList.add('text-warning');
      seedHelp.classList.remove('text-muted');
    }
  }

  function saveNewWorldFromModal() {
    const nameInput = document.getElementById('new_world_name_modal');
    const seedInput = document.getElementById('level_seed_modal');
    const summary = document.getElementById('new_world_summary');
    const hiddenName = document.getElementById('new_world_name');
    const hiddenSeed = document.getElementById('level_seed');
    const select = document.getElementById('selected_world');

    const newName = (nameInput.value || '').trim();
    const newSeed = (seedInput.value || '').trim();

    if (!newName) {
      alert('Please provide a world name.');
      return;
    }

    if (select) {
      select.value = '';
    }

    if (hiddenName) hiddenName.value = newName;
    if (hiddenSeed) hiddenSeed.value = newSeed;

    if (summary) {
      summary.textContent = `New world: "${newName}"${newSeed ? ` with seed "${newSeed}"` : ''}.`;
      summary.classList.remove('d-none');
    }

    const modalEl = document.getElementById('newWorldModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  function syncHiddenField() {
    const hidden = document.getElementById('role_assignments_json');
    if (!hidden) return;
    hidden.value = JSON.stringify(roleAssignments, null, 2);
  }

  function renderRoleAssignmentsTable() {
    const tbody = document.querySelector('#ra_table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!Array.isArray(roleAssignments) || roleAssignments.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 3;
      td.className = 'text-muted small';
      td.textContent = 'No explicit player entries configured yet.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    roleAssignments.forEach((item, idx) => {
      const tr = document.createElement('tr');

      const nameTd = document.createElement('td');

      const nameDiv = document.createElement('div');
      nameDiv.className = 'fw-semibold';
      const displayName =
        item.name && item.name.trim().length > 0 ? item.name.trim() : '(no name)';
      nameDiv.textContent = displayName;

      const uuidDiv = document.createElement('div');
      uuidDiv.className = 'small text-muted';
      uuidDiv.innerHTML = '<code>' + (item.uuid || '') + '</code>';

      nameTd.appendChild(nameDiv);
      nameTd.appendChild(uuidDiv);
      tr.appendChild(nameTd);

      const roleTd = document.createElement('td');
      roleTd.className = 'align-middle';
      const roleSpan = document.createElement('span');
      const role = item.role || 'member';
      roleSpan.textContent = role;
      roleSpan.className = 'badge text-uppercase';
      if (role === 'operator') roleSpan.className += ' bg-danger';
      else roleSpan.className += ' bg-secondary';
      roleTd.appendChild(roleSpan);
      tr.appendChild(roleTd);

      const actionsTd = document.createElement('td');
      actionsTd.className = 'text-end align-middle';

      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'btn btn-sm btn-outline-light me-1';
      editBtn.textContent = 'Edit';
      editBtn.onclick = () => openEditModal(idx);
      actionsTd.appendChild(editBtn);

      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'btn btn-sm btn-outline-danger';
      delBtn.textContent = '✕';
      delBtn.onclick = () => deleteAssignment(idx);
      actionsTd.appendChild(delBtn);

      tr.appendChild(actionsTd);

      tbody.appendChild(tr);
    });
  }

  function openEditModal(index) {
    const item = roleAssignments[index] || {};
    document.getElementById('edit_index').value = index;
    document.getElementById('perm_name').value = item.name || '';
    document.getElementById('perm_uuid').value = item.uuid || '';
    document.getElementById('perm_role').value = item.role || 'member';

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('permissionsModal'));
    modal.show();
  }

  function openAddModal() {
    document.getElementById('edit_index').value = -1;
    document.getElementById('perm_name').value = '';
    document.getElementById('perm_uuid').value = '';
    document.getElementById('perm_role').value = 'member';
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('permissionsModal'));
    modal.show();
  }

  function savePermissionFromModal() {
    const idx = parseInt(document.getElementById('edit_index').value, 10);
    const name = document.getElementById('perm_name').value.trim();
    const uuid = document.getElementById('perm_uuid').value.trim();
    const role = document.getElementById('perm_role').value;

    if (!uuid) {
      alert('UUID is required.');
      return;
    }

    const item = { uuid: uuid, role: role };
    if (name) item.name = name;

    if (!Array.isArray(roleAssignments)) {
      roleAssignments = [];
    }

    if (idx >= 0 && idx < roleAssignments.length) {
      roleAssignments[idx] = item;
    } else {
      const existingIndex = roleAssignments.findIndex(r => r.uuid === uuid);
      if (existingIndex >= 0) {
        roleAssignments[existingIndex] = item;
      } else {
        roleAssignments.push(item);
      }
    }

    syncHiddenField();
    renderRoleAssignmentsTable();

    const modalEl = document.getElementById('permissionsModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  function deleteAssignment(index) {
    if (!Array.isArray(roleAssignments)) return;
    roleAssignments.splice(index, 1);
    syncHiddenField();
    renderRoleAssignmentsTable();
  }

  function renderRuntimeOps() {
    const tbody = document.querySelector('#runtime_ops_table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    fetch('api/ops')
      .then(resp => resp.json())
      .then(payload => {
        if (!payload || !payload.data || !Array.isArray(payload.data) || payload.data.length === 0) {
          const tr = document.createElement('tr');
          const td = document.createElement('td');
          td.colSpan = 3;
          td.className = 'text-muted small';
          td.textContent = 'ops.json is currently empty or unavailable.';
          tr.appendChild(td);
          tbody.appendChild(tr);
          return;
        }

        payload.data.forEach(entry => {
          const tr = document.createElement('tr');
          const name = entry.name || '';
          const uuid = entry.uuid || '';
          const level = entry.level || '';

          const nameTd = document.createElement('td');
          nameTd.textContent = name;
          tr.appendChild(nameTd);

          const uuidTd = document.createElement('td');
          uuidTd.innerHTML = '<code>' + uuid + '</code>';
          tr.appendChild(uuidTd);

          const levelTd = document.createElement('td');
          levelTd.textContent = level;
          tr.appendChild(levelTd);

          tbody.appendChild(tr);
        });
      })
      .catch(err => {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 3;
        td.className = 'text-danger small';
        td.textContent = 'Error reading ops.json: ' + err;
        tr.appendChild(td);
        tbody.appendChild(tr);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!Array.isArray(roleAssignments)) {
      roleAssignments = [];
    }
    syncHiddenField();
    renderRoleAssignmentsTable();
    renderRuntimeOps();

    const select = document.getElementById('selected_world');
    if (select) {
      select.addEventListener('change', () => {
        clearNewWorldSelection();
        updateCurrentSeedDisplay(select.value);
      });
      updateCurrentSeedDisplay(select.value);
    }

    const newWorldModalEl = document.getElementById('newWorldModal');
    if (newWorldModalEl) {
      newWorldModalEl.addEventListener('show.bs.modal', () => {
        const nameInput = document.getElementById('new_world_name_modal');
        const seedInput = document.getElementById('level_seed_modal');
        if (nameInput) nameInput.value = '';
        if (seedInput) seedInput.value = '';
      });
    }
  });
</script>

</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8790, debug=True)
