## 1.0.2 - 2026-06-20

### Fixed

- The `Error loading java.security file` crash persisted even after the `mc-image-helper`
  removal in 1.0.1, because the actual root cause was the apt-installed
  `openjdk-21-jre-headless` package itself: the `ca-certificates-java` postinst trigger
  intermittently corrupts the JRE's `java.security`/`cacerts` setup on the Debian Trixie
  base image, regardless of which user runs `java` or which server jar is used.
- Replaced the apt-installed JRE entirely with a JRE copied directly from the official
  `itzg/minecraft-server:java21` image via a Docker multi-stage `COPY --from`. That JRE
  is never touched by `apt`/`dpkg`, so the bug cannot occur.
- Simplified `java-entry.sh`'s `JAVA_HOME` detection to resolve from the `java` binary
  symlink rather than a hardcoded Debian package path that no longer exists.
- Reverted the now-unnecessary `dpkg`/`update-ca-certificates` self-heal logic added in
  1.0.1 and the corresponding AppArmor write rules for `/etc/ssl/certs` and
  `/var/lib/dpkg`, since the JRE is no longer apt-managed.
- Documented in the README that older server versions (e.g. Paper/Spigot 1.16.5) still
  require an older Java release than the Java 21 bundled here, and will fail to start
  for an unrelated reason (`UnsupportedClassVersionError`/JNI error) even once the jar
  installs successfully.

## 1.0.1 - 2026-06-20

### Fixed

- Removed `mc-image-helper`-based automatic software resolution/installation. It failed at
  runtime under the add-on's demoted/non-root user (`Error loading java.security file`,
  `uname: Permission denied`) because the bundled Java runtime inside the helper distribution
  could not initialize its security provider in this environment.
- Replaced it with **manual server jar installation**, mirroring the working approach used by
  the Bedrock add-on: download the jar yourself (Vanilla/Paper/Fabric/Forge/...), rename it to
  `<type>-server-<version>.jar`, and place it in `addon_configs/<slug>/java-server-software/`.
- Added an explicit **Installing/Upgrading Server** mode (`install_upgrade_server` option) that
  must be enabled to install or upgrade the jar; the Java server does not start while this mode
  is active.
- Added an **Allow Downgrade** option (`allow_downgrade`) with a 30-second cancellable countdown
  before removing the previously installed jar, matching the Bedrock add-on's safety pattern.
- The add-on Configuration UI no longer exposes a "Type/Version" selector (it implied automatic
  resolution that no longer happens); it now shows the currently installed type/version read
  directly from disk.

## 1.0.0 - 2026-06-20

### Initial release

- Minecraft Java Edition Server add-on for Home Assistant OS
- Based on [itzg/docker-minecraft-server](https://github.com/itzg/docker-minecraft-server)
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
