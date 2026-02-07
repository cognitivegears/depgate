"""Per-manager wrapper configurations for depgate run mode.

Each supported package manager gets environment variables, extra CLI arguments,
and/or temporary config files that redirect registry traffic through the proxy.
"""

from __future__ import annotations

import logging
import os
import tempfile
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SUPPORTED_MANAGERS = [
    "npm", "pnpm", "yarn", "bun",
    "pip", "pip3", "pipx", "poetry",
    "uv",
    "mvn", "gradle", "gradlew",
    "dotnet", "nuget",
]


@dataclass
class WrapperConfig:
    """Configuration for wrapping a package manager command."""

    env_vars: Dict[str, str] = field(default_factory=dict)
    extra_args: List[str] = field(default_factory=list)
    temp_files: List[str] = field(default_factory=list)
    registry_type: str = ""


def get_wrapper(command_name: str, proxy_url: str) -> Optional[WrapperConfig]:
    """Build a WrapperConfig for the given package manager.

    Args:
        command_name: The package manager binary name (e.g. "npm", "pip").
        proxy_url: The proxy base URL (e.g. "http://127.0.0.1:12345").

    Returns:
        WrapperConfig if the manager is supported, None otherwise.
    """
    name = os.path.basename(command_name).lower()

    builders = {
        "npm": _build_npm,
        "pnpm": _build_pnpm,
        "yarn": _build_yarn,
        "bun": _build_bun,
        "pip": _build_pip,
        "pip3": _build_pip,
        "pipx": _build_pip,
        "poetry": _build_poetry,
        "uv": _build_uv,
        "mvn": _build_maven,
        "gradle": _build_gradle,
        "gradlew": _build_gradle,
        "dotnet": _build_nuget,
        "nuget": _build_nuget,
    }

    builder = builders.get(name)
    if builder is None:
        return None

    return builder(proxy_url)


# ---------- JS ecosystem ----------


def _build_npm(proxy_url: str) -> WrapperConfig:
    return WrapperConfig(
        env_vars={"npm_config_registry": proxy_url},
        registry_type="npm",
    )


def _build_pnpm(proxy_url: str) -> WrapperConfig:
    return WrapperConfig(
        env_vars={"npm_config_registry": proxy_url},
        registry_type="npm",
    )


def _build_yarn(proxy_url: str) -> WrapperConfig:
    return WrapperConfig(
        env_vars={
            "npm_config_registry": proxy_url,
            "YARN_NPM_REGISTRY_SERVER": proxy_url,
        },
        registry_type="npm",
    )


def _build_bun(proxy_url: str) -> WrapperConfig:
    return WrapperConfig(
        env_vars={"npm_config_registry": proxy_url},
        registry_type="npm",
    )


# ---------- Python ecosystem ----------


def _build_pip(proxy_url: str) -> WrapperConfig:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "127.0.0.1"
    index_url = proxy_url.rstrip("/") + "/simple"
    return WrapperConfig(
        env_vars={
            "PIP_INDEX_URL": index_url,
            "PIP_TRUSTED_HOST": host,
        },
        registry_type="pypi",
    )


def _build_poetry(proxy_url: str) -> WrapperConfig:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "127.0.0.1"
    index_url = proxy_url.rstrip("/") + "/simple"
    return WrapperConfig(
        env_vars={
            "PIP_INDEX_URL": index_url,
            "PIP_TRUSTED_HOST": host,
        },
        registry_type="pypi",
    )


def _build_uv(proxy_url: str) -> WrapperConfig:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "127.0.0.1"
    index_url = proxy_url.rstrip("/") + "/simple"
    return WrapperConfig(
        env_vars={
            "UV_INDEX_URL": index_url,
            "UV_INSECURE_HOST": host,
        },
        registry_type="pypi",
    )


# ---------- JVM ecosystem ----------


_SETTINGS_XML_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0
                                  http://maven.apache.org/xsd/settings-1.0.0.xsd">
      <mirrors>
        <mirror>
          <id>depgate-proxy</id>
          <mirrorOf>*</mirrorOf>
          <url>{proxy_url}</url>
        </mirror>
      </mirrors>
    </settings>
""")

_INIT_GRADLE_TEMPLATE = textwrap.dedent("""\
    allprojects {{
        repositories {{
            maven {{
                url "{proxy_url}"
                allowInsecureProtocol true
            }}
        }}
        buildscript {{
            repositories {{
                maven {{
                    url "{proxy_url}"
                    allowInsecureProtocol true
                }}
            }}
        }}
    }}
""")


def _build_maven(proxy_url: str) -> WrapperConfig:
    # Warn if user has an existing settings.xml
    user_settings = os.path.expanduser("~/.m2/settings.xml")
    if os.path.exists(user_settings):
        logger.warning(
            "Existing ~/.m2/settings.xml detected. "
            "The depgate proxy settings will override it via -s flag."
        )

    content = _SETTINGS_XML_TEMPLATE.format(proxy_url=proxy_url)
    fd, path = tempfile.mkstemp(suffix=".xml", prefix="depgate-mvn-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    return WrapperConfig(
        extra_args=["-s", path],
        temp_files=[path],
        registry_type="maven",
    )


def _build_gradle(proxy_url: str) -> WrapperConfig:
    content = _INIT_GRADLE_TEMPLATE.format(proxy_url=proxy_url)
    fd, path = tempfile.mkstemp(suffix=".gradle", prefix="depgate-gradle-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    return WrapperConfig(
        extra_args=["--init-script", path],
        temp_files=[path],
        registry_type="maven",
    )


# ---------- .NET ecosystem ----------


_NUGET_CONFIG_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <configuration>
      <packageSources>
        <clear />
        <add key="depgate-proxy" value="{proxy_url}" />
      </packageSources>
    </configuration>
""")


def _build_nuget(proxy_url: str) -> WrapperConfig:
    content = _NUGET_CONFIG_TEMPLATE.format(proxy_url=proxy_url)
    fd, path = tempfile.mkstemp(suffix=".config", prefix="depgate-nuget-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

    return WrapperConfig(
        env_vars={"NUGET_CONFIGFILE": path},
        temp_files=[path],
        registry_type="nuget",
    )
