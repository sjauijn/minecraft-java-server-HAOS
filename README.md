# Minecraft Java Server (Home Assistant Add-on)

Minecraft Java Edition Server tailored for Home Assistant OS, with full configuration
through the Ingress web UI and worlds accessible via SFTP.

Based on [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server).

## Features

- Automatic installation of the server software (Vanilla, Paper, Spigot, Fabric, Forge,
  NeoForge, Quilt, Purpur, Folia) via `mc-image-helper` — no manual jar upload needed
- Full configuration UI via Home Assistant Ingress
- World creation/selection with per-world seed storage
- Worlds accessible via SFTP at `addon_configs/minecraft_java_server/worlds/`
- Operator (`ops.json`) and whitelist (`whitelist.json`) management from the UI
- RCON enabled by default, used for graceful stop and remote commands
- AppArmor profile included
- Health checks via `mc-monitor`

## Directory layout

```
addon_configs/minecraft_java_server/
├── worlds/                  # World folders (SFTP accessible)
/data/ (persistent volume)
├── server/                  # Server jar, server.properties, ops.json, whitelist.json
├── config/java_for_ha_config.json
├── worldconfiguration.json  # Per-world seeds
├── .rcon-password
└── run/                     # PID and stop-marker files
```

## Getting started

1. Install the add-on.
2. Open the add-on Web UI (Ingress).
3. Choose the server **Type** and **Version** (or leave `LATEST`).
4. Accept the **Minecraft EULA**.
5. Save the configuration and start the add-on.

The first start downloads and installs the selected server software automatically.

## Sending commands

Commands can be sent through RCON:

```
docker exec <container> send-command say Hello from Home Assistant!
```

If RCON is disabled, `send-command` falls back to writing to the server's STDIN.

## License

MIT License, see [LICENSE](LICENSE). Underlying server runtime tooling courtesy of
[itzg](https://github.com/itzg) (easy-add, mc-image-helper, mc-server-runner, mc-monitor,
rcon-cli, set-property, restify, entrypoint-demoter).
