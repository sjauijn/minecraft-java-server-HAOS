## 1.0.1 - 2026-06-20

### Fixed

- AppArmor profile was blocking `uname` and `echo`, breaking `mc-image-helper` at startup (`Permission denied`)
- AppArmor profile did not allow reading `/etc/java-*-openjdk/**`, where Debian's OpenJDK actually keeps `java.security`/`java.policy` (it's a symlink target outside `/usr/lib/jvm`). This caused every JVM invocation (both `mc-image-helper` and the Minecraft server itself) to crash with `InternalError: Error loading java.security file`
- Removed a dead/no-op `mc-image-helper install-from-mojang` pre-step in `java-entry.sh` that never affected behavior and only added confusing log output

## 1.0.0 - 2026-06-20

### Initial release

- Minecraft Java Edition Server add-on for Home Assistant OS
- Based on [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server)
- Automatic software installation/version resolution via `mc-image-helper` (no manual ZIP upload required, unlike the Bedrock add-on)
- Supports server types: Vanilla, Paper, Spigot, Fabric, Forge, NeoForge, Quilt, Purpur, Folia
- Full configuration UI via Home Assistant Ingress (Flask + Bootstrap)
- World management: create/select worlds, per-world seed storage in `/data/worldconfiguration.json`
- Worlds accessible via SFTP at `addon_configs/<slug>/worlds/`
- Operators (`ops.json`) and whitelist (`whitelist.json`) management from the UI, keyed by player UUID
- RCON enabled by default with auto-generated password (stored in `/data/.rcon-password`)
- `send-command` helper: sends console commands via RCON, falls back to STDIN
- Health checks via `mc-monitor`
- EULA acceptance required via configuration before the server starts
- AppArmor profile included
- Memory configuration (Xms/Xmx or percentage-based)
- Log4j RCE patch agent applied automatically for vulnerable versions
