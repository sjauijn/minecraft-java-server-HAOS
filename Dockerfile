ARG TARGETARCH
FROM ghcr.io/home-assistant/amd64-base-debian:trixie

ARG TARGETOS
ARG TARGETARCH
ARG TARGETPLATFORM

ARG EASY_ADD_VERSION
ARG ENTRYPOINT_DEMOTER_VERSION
ARG SET_PROPERTY_VERSION
ARG RESTIFY_VERSION
ARG MC_MONITOR_VERSION
ARG RCON_CLI_VERSION
ARG MC_SERVER_RUNNER_VERSION

# ===== Base tools =====
RUN apt-get update
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip jq dos2unix gosu openssl
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-flask python3-waitress
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/*

# ===== Java runtime =====
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN echo "🏗️ Building for platform: ${TARGETPLATFORM} (OS=${TARGETOS}, ARCH=${TARGETARCH})"

# Java server poort + RCON poort + Ingress poort (Flask Webservice)
EXPOSE 25565/tcp 25575/tcp 8790/tcp

VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["/usr/local/bin/entrypoint-demoter", "--match", "/data", "--debug", "--stdin-on-term", "stop", "/opt/start.sh"]

# Easy-add tool installeren
ADD https://github.com/itzg/easy-add/releases/download/${EASY_ADD_VERSION}/easy-add_linux_${TARGETARCH} /usr/local/bin/easy-add
RUN chmod +x /usr/local/bin/easy-add

# Extra tools installeren via easy-add
RUN easy-add --var version=${ENTRYPOINT_DEMOTER_VERSION} --var app=entrypoint-demoter --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/v{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz
RUN easy-add --var version=${SET_PROPERTY_VERSION} --var app=set-property --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz
RUN easy-add --var version=${RESTIFY_VERSION} --var app=restify --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz
RUN easy-add --var version=${MC_MONITOR_VERSION} --var app=mc-monitor --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz
RUN easy-add --var version=${RCON_CLI_VERSION} --var app=rcon-cli --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz
RUN easy-add --var version=${MC_SERVER_RUNNER_VERSION} --var app=mc-server-runner --file {{.app}} --from https://github.com/itzg/{{.app}}/releases/download/{{.version}}/{{.app}}_{{.version}}_linux_${TARGETARCH}.tar.gz

# Log4j RCE patch agent (zelfde als itzg/docker-minecraft-server)
RUN curl -fsSL -o /opt/Log4jPatcher.jar https://github.com/CreeperHost/Log4jPatcher/releases/download/v1.0.1/Log4jPatcher-1.0.1.jar

# Bestanden naar container kopiëren
COPY java-entry.sh /opt/java-entry.sh
COPY start.sh /opt/start.sh
COPY install-server.sh /opt/install-server.sh
COPY healthcheck.sh /opt/healthcheck.sh
COPY property-definitions.json /etc/mc-property-definitions.json
COPY web/app.py /opt/flask/app.py
COPY web/static /opt/flask/static
COPY bin/* /usr/local/bin/

RUN dos2unix /opt/java-entry.sh /opt/start.sh /opt/install-server.sh /opt/healthcheck.sh

RUN mkdir -p /opt/server

RUN chmod +x /opt/java-entry.sh
RUN chmod +x /opt/start.sh
RUN chmod +x /opt/install-server.sh
RUN chmod +x /opt/healthcheck.sh
RUN chmod +x /usr/local/bin/send-command

HEALTHCHECK --interval=15s --timeout=5s --retries=2 --start-period=30s CMD /opt/healthcheck.sh
