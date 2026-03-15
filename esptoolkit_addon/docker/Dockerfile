ARG BUILD_VERSION=dev
# Use debian base so PlatformIO/tool-cmake works (alpine fails with tool-cmake FileNotFoundError)
ARG BUILD_OS=debian
ARG BUILD_BASE_VERSION=2025.04.0
# Use ha-addon base so platformio/esphome layout matches official add-on
ARG BUILD_TYPE=ha-addon

FROM ghcr.io/esphome/docker-base:${BUILD_OS}-${BUILD_BASE_VERSION} AS base-source-docker
FROM ghcr.io/esphome/docker-base:${BUILD_OS}-ha-addon-${BUILD_BASE_VERSION} AS base-source-ha-addon

ARG BUILD_TYPE
FROM base-source-${BUILD_TYPE} AS base

RUN git config --system --add safe.directory "*" \
    && git config --system advice.detachedHead false

# Install build tools for Python packages that require compilation
# (e.g., ruamel.yaml.clibz used by ESP-IDF's idf-component-manager)
RUN if command -v apk > /dev/null; then \
        apk add --no-cache build-base; \
    else \
        apt-get update \
        && apt-get install -y --no-install-recommends build-essential \
        && rm -rf /var/lib/apt/lists/*; \
    fi

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir -U pip uv==0.10.1

COPY requirements.txt /

RUN \
    uv pip install --no-cache-dir \
    -r /requirements.txt

RUN \
    platformio settings set enable_telemetry No \
    && platformio settings set check_platformio_interval 1000000 \
    && mkdir -p /piolibs

COPY script/platformio_install_deps.py platformio.ini /
RUN python3 /platformio_install_deps.py /platformio.ini --libraries

# Pre-install espressif32 platform + tool-cmake so runtime compiles (esp-idf) work without /data warmup.
# Install into image path; run script seeds /data/cache/platformio from here when missing.
RUN mkdir -p /opt/platformio-preinstalled/platforms /opt/platformio-preinstalled/packages /opt/platformio-preinstalled/cache \
    && export PLATFORMIO_PLATFORMS_DIR=/opt/platformio-preinstalled/platforms \
        PLATFORMIO_PACKAGES_DIR=/opt/platformio-preinstalled/packages \
        PLATFORMIO_CACHE_DIR=/opt/platformio-preinstalled/cache \
        PLATFORMIO_GLOBALLIB_DIR=/piolibs \
    && platformio pkg install -g -p "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip"

ARG BUILD_VERSION

LABEL \
    org.opencontainers.image.authors="The ESPHome Authors" \
    org.opencontainers.image.title="ESPHome" \
    org.opencontainers.image.description="ESPHome is a system to configure your microcontrollers by simple yet powerful configuration files and control them remotely through Home Automation systems" \
    org.opencontainers.image.url="https://esphome.io/" \
    org.opencontainers.image.documentation="https://esphome.io/" \
    org.opencontainers.image.source="https://github.com/esphome/esphome" \
    org.opencontainers.image.licenses="ESPHome" \
    org.opencontainers.image.version=${BUILD_VERSION}


# ======================= docker-type image =======================
FROM base AS base-docker

# Expose the dashboard to Docker
EXPOSE 6052

# Run healthcheck (heartbeat)
HEALTHCHECK --interval=30s --timeout=30s \
    CMD curl --fail http://localhost:6052/version -A "HealthCheck" || exit 1

COPY docker/docker_entrypoint.sh /entrypoint.sh

# The directory the user should mount their configuration files to
VOLUME /config
WORKDIR /config
# Set entrypoint to esphome (via a script) so that the user doesn't have to type 'esphome'
# in every docker command twice
ENTRYPOINT ["/entrypoint.sh"]
# When no arguments given, start the dashboard in the workdir
CMD ["dashboard", "/config"]


# ======================= ha-addon-type image =======================
FROM base AS base-ha-addon

# Copy root filesystem
COPY docker/ha-addon-rootfs/ /

ARG BUILD_VERSION
LABEL \
    io.hass.name="ESPHome" \
    io.hass.description="ESPHome is a system to configure your microcontrollers by simple yet powerful configuration files and control them remotely through Home Automation systems" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}"
    # io.hass.arch is inherited from addon-debian-base

ARG BUILD_TYPE
FROM base-${BUILD_TYPE} AS final

# Fetch ESPHome source at build time (same as official add-on; not in repo to keep push small)
ARG ESPHOME_REF=dev
RUN curl -fsSL -o /tmp/esphome.tar.gz "https://github.com/esphome/esphome/archive/refs/heads/${ESPHOME_REF}.tar.gz" \
    && mkdir -p /esphome && tar -xzf /tmp/esphome.tar.gz -C /esphome --strip-components=1 \
    && rm /tmp/esphome.tar.gz
RUN uv pip install --no-cache-dir -e /esphome

# Run a minimal esp-idf compile so tool-cmake (and other tools) get installed. idf_tools.py
# installs to the default PlatformIO dir (/root/.platformio), so we use defaults then copy to /opt.
COPY docker/minimal_espidf.yaml /tmp/minimal_espidf.yaml
RUN ESPHOME_IS_HA_ADDON=true esphome compile /tmp/minimal_espidf.yaml \
    && cp -a /root/.platformio/platforms/* /opt/platformio-preinstalled/platforms/ \
    && cp -a /root/.platformio/packages/* /opt/platformio-preinstalled/packages/ \
    && cp -a /root/.platformio/cache/* /opt/platformio-preinstalled/cache/ 2>/dev/null || true \
    && rm -rf /tmp/build /tmp/.esphome /tmp/minimal_espidf.yaml /root/.platformio

# --- This add-on: API server; s6 (base image entrypoint) runs esphome-api service ---
FROM final AS production
WORKDIR /app
COPY app/ ./app/
COPY custom_components/ ./custom_components/
EXPOSE 8098
# No ENTRYPOINT: use base image entrypoint so s6 starts and runs esphome-api service

FROM production AS test
RUN uv pip install --no-cache-dir -q pytest pytest-asyncio
