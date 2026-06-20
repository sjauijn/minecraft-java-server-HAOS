## 1.0.2 - 2026-06-20

### Fixed

- AppArmor profile still blocked execution of `mc-image-helper`'s actual installation: the rule `/usr/share/mc-image-helper*/**` only matched paths *inside* the versioned directory (e.g. `/usr/share/mc-image-helper-1.61.0/bin/...`), not the bare directory itself or the `/usr/share/mc-image-helper` symlink that `/usr/local/bin/mc-image-helper` ultimately points to. The launcher script's own symlink-resolution logic was being denied, so it printed only its name/version and exited without installing anything (`❌ No server jar found after installation step.`)
- Added missing `readlink`/`realpath` to the AppArmor profile, used by the generated launcher script to resolve its own location through the symlink chain
- `java-entry.sh` now reports `mc-image-helper`'s actual exit code on failure instead of always showing the generic "no jar found" message, to make future AppArmor/permission regressions easier to diagnose directly from the log

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
