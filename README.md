# Minecraft Java Server (Home Assistant Add-on)

Minecraft Java Edition Server tailored for Home Assistant OS, with full configuration
through the Ingress web UI and worlds accessible via SFTP.

Based on [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server),
but with **manual server-jar installation** (same approach as the companion
[minecraft-bedrock-server-HAOS](https://github.com/sjauijn/minecraft-bedrock-server-HAOS)
add-on) instead of automatic resolution via `mc-image-helper`.

## Features

- Manual installation of the server software (Vanilla, Paper, Spigot, Fabric, Forge,
  NeoForge, Quilt, Purpur, Folia, or any custom jar) — you download the jar, the add-on
  installs and tracks it
- Built-in **Installing/Upgrading Server** mode with version/type tracking and a
  cancellable downgrade safety countdown
- Full configuration UI via Home Assistant Ingress
- World creation/selection with per-world seed storage
- Worlds accessible via SFTP at `addon_configs/minecraft_java_server/worlds/`
- Operator (`ops.json`) and whitelist (`whitelist.json`) management from the UI
- RCON enabled by default, used for graceful stop and remote commands
- AppArmor profile included
- Health checks via `mc-monitor`

## Why manual installation?

`mc-image-helper` is normally used to auto-resolve and download the server jar for a
given type/version. Inside this add-on's container, it failed at runtime with errors like:

```
Exception in thread "main" java.lang.InternalError: Error loading java.security file
/usr/local/bin/mc-image-helper: 110: uname: Permission denied
```

This happens because the add-on runs the actual server process as a demoted, non-root
user (via `entrypoint-demoter`), and the bundled JRE inside the `mc-image-helper`
distribution could not initialize its security provider under that user/permission
context. Rather than fight that, this add-on uses the same manual-installation pattern
as the Bedrock add-on: you supply the jar, the add-on just runs it.

## Directory layout

```
addon_configs/minecraft_java_server/
├── worlds/                       # World folders (SFTP accessible)
└── java-server-software/         # Upload <type>-server-<version>.jar here
/data/ (persistent volume)
├── server/                       # server.jar symlink, server.properties, ops.json, whitelist.json
├── server-<version>.jar          # Installed server jar(s)
├── .installed-java-version       # Tracks currently installed version
├── .installed-java-type          # Tracks currently installed type (vanilla/paper/fabric/...)
├── config/java_for_ha_config.json
├── worldconfiguration.json       # Per-world seeds
├── .rcon-password
└── run/                          # PID and stop-marker files
```

## Getting started

1. Install the add-on.
2. In the add-on **Configuration** tab, make sure **Installing/Upgrading Server** is
   enabled (it is `true` by default) and start the add-on. It will tell you no jar was
   found yet.
3. Download the server jar you want, e.g.:
   - Vanilla: https://www.minecraft.net/download/server
   - Paper: https://papermc.io/downloads/paper
   - Fabric: https://fabricmc.net/use/server/
4. Rename it to `<type>-server-<version>.jar`, for example:
   - `vanilla-server-1.21.4.jar`
   - `paper-server-1.21.4.jar`
   - `fabric-server-1.21.4.jar`
5. Upload it to `addon_configs/minecraft_java_server/java-server-software/` (via Samba/SFTP).
6. Restart the add-on. It will detect the jar, install it, and report success.
7. Set **Installing/Upgrading Server** to `false`.
8. Open the add-on Web UI (Ingress), accept the **Minecraft EULA**, save the configuration.
9. Restart the add-on — the Java server will now start.

### Upgrading

Repeat steps 3–6 with a jar of a higher version. The add-on detects the version difference
and performs an upgrade automatically while **Installing/Upgrading Server** is `true`.

### Downgrading

Downgrading is blocked by default to avoid world corruption. To allow it, enable
**Allow Downgrade** *together with* **Installing/Upgrading Server**. A 30-second countdown
gives you a chance to cancel by stopping the add-on before the currently installed jar is
removed. Worlds and configuration are preserved; only the jar itself is replaced.

## Sending commands

Commands can be sent through RCON:

```
docker exec <container> send-command say Hello from Home Assistant!
```

If RCON is disabled, `send-command` falls back to writing to the server's STDIN.

## License

MIT License, see [LICENSE](LICENSE). Underlying server runtime tooling courtesy of
[itzg](https://github.com/itzg) (easy-add, mc-server-runner, mc-monitor, rcon-cli,
set-property, restify, entrypoint-demoter).
