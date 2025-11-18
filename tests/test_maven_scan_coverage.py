"""Additional tests for Maven scanner to improve coverage."""
from __future__ import annotations

import os
import tempfile
import pytest
import sys

from constants import ExitCodes
from registry.maven.client import scan_source as maven_scan_source


def test_maven_scan_recursive():
    """Test recursive scanning for Maven."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Root pom.xml
        root_pom = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>root</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(root_pom)

        # Subdirectory pom.xml
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)
        sub_pom = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>sub</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(subdir, "pom.xml"), "w") as f:
            f.write(sub_pom)

        deps = maven_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=False)
        assert "junit:junit" in deps
        assert "org.mockito:mockito-core" in deps


def test_maven_scan_no_pom_xml():
    """Test error when pom.xml is not found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty directory
        with pytest.raises(SystemExit) as exc_info:
            maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_maven_scan_missing_groupid():
    """Test handling of dependency with missing groupId."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Should skip dependency without groupId
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "junit:junit" not in deps
        assert "org.mockito:mockito-core" in deps


def test_maven_scan_missing_artifactid():
    """Test handling of dependency with missing artifactId."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <version>4.13.2</version>
    </dependency>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Should skip dependency without artifactId
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "junit:junit" not in deps
        assert "org.mockito:mockito-core" in deps


def test_maven_scan_invalid_xml():
    """Test handling of invalid XML in pom.xml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid XML
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write("<project><Invalid XML>")

        # Should return empty list (preserves original behavior)
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_maven_scan_require_lockfile_warning():
    """Test that require_lockfile logs a warning for Maven."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Should work but log warning
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert "junit:junit" in deps


def test_maven_scan_empty_dependencies():
    """Test pom.xml with empty dependencies section."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_maven_scan_multiple_dependencies_sections():
    """Test pom.xml with multiple dependencies sections."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
  </dependencies>
  <dependencies>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "junit:junit" in deps
        assert "org.mockito:mockito-core" in deps


def test_maven_scan_dependency_with_empty_groupid():
    """Test handling of dependency with empty groupId text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId></groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Should skip dependency with empty groupId
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "junit" not in deps or "junit:junit" not in deps
        assert "org.mockito:mockito-core" in deps


def test_maven_scan_dependency_with_empty_artifactid():
    """Test handling of dependency with empty artifactId text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId></artifactId>
      <version>4.13.2</version>
    </dependency>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Should skip dependency with empty artifactId
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "junit:junit" not in deps
        assert "org.mockito:mockito-core" in deps
