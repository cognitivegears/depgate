"""CLI classification helpers.

Provides:
- build_dependency_classification(args) -> dict[str, dict[str, str]]
- apply_classification(args, instances) -> None

These functions were extracted from the original src/depgate.py to reduce complexity.
"""

# pylint: disable=too-many-locals, too-many-branches, too-many-statements, too-many-nested-blocks, import-outside-toplevel, line-too-long
from __future__ import annotations

import json as _json
import os as _os
from typing import Dict, List

from constants import Constants
from cli_build import to_ecosystem

# Fallback-friendly imports for versioning models and parsers
try:
    from src.versioning.models import Ecosystem  # type: ignore
except ImportError:  # pragma: no cover
    from versioning.models import Ecosystem  # type: ignore


def build_dependency_classification(args) -> Dict[str, Dict[str, str]]:
    """Build mapping from identifier to classification strings for source scans.

    Returns a mapping: name_or_coordinate -> {"relation": str, "requirement": str, "scope": str}
    """
    try:
        eco = to_ecosystem(args.package_type)
        result: Dict[str, Dict[str, str]] = {}
        if not getattr(args, "FROM_SRC", None):
            return result
        base_dir = args.FROM_SRC[0]

        def _merge(name, rel, req, scope):
            # Convert enum-like values to strings
            rel_s = rel.value if hasattr(rel, "value") else str(rel)
            req_s = req.value if hasattr(req, "value") else str(req)
            scope_s = scope.value if hasattr(scope, "value") else str(scope)
            existing = result.get(name)
            if not existing:
                result[name] = {"relation": rel_s, "requirement": req_s, "scope": scope_s}
                return
            # Prefer stronger requirement and scope; and direct over transitive
            prio_req = {"required": 2, "optional": 1}
            prio_scope = {"normal": 3, "development": 2, "testing": 1}
            if prio_req.get(req_s, 0) > prio_req.get(str(existing.get("requirement") or ""), 0):
                existing["requirement"] = req_s
            if prio_scope.get(scope_s, 0) > prio_scope.get(str(existing.get("scope") or ""), 0):
                existing["scope"] = scope_s
            if existing.get("relation") != "direct" and rel_s == "direct":
                existing["relation"] = "direct"

        if eco == Ecosystem.NPM:
            pkg_files: List[str] = []
            if args.RECURSIVE:
                for root, _, files in _os.walk(base_dir):
                    if Constants.PACKAGE_JSON_FILE in files:
                        pkg_files.append(_os.path.join(root, Constants.PACKAGE_JSON_FILE))
            else:
                path = _os.path.join(base_dir, Constants.PACKAGE_JSON_FILE)
                if _os.path.isfile(path):
                    pkg_files.append(path)

            def _extract_npm_name_from_path(p: str) -> str:
                try:
                    # Normalize separators
                    p = str(p).replace("\\", "/")
                    # Find last occurrence of node_modules
                    if "node_modules/" in p:
                        segs = p.split("node_modules/")
                        tail = segs[-1]
                        parts = [s for s in tail.split("/") if s]
                        if not parts:
                            return ""
                        if parts[0].startswith("@") and len(parts) >= 2:
                            return f"{parts[0]}/{parts[1]}"
                        return parts[0]
                    return ""
                except Exception:
                    return ""

            def _scan_npm_lock_obj(obj: dict) -> dict[str, bool]:
                names_dev: dict[str, bool] = {}
                try:
                    pkgs = obj.get("packages")
                    if isinstance(pkgs, dict):
                        for path, meta in pkgs.items():
                            if not isinstance(meta, dict):
                                continue
                            name = meta.get("name") or _extract_npm_name_from_path(path or "")
                            if not name:
                                continue
                            dev = bool(meta.get("dev", False))
                            names_dev[name] = names_dev.get(name, False) or dev
                    elif isinstance(obj.get("dependencies"), dict):
                        def _rec(depmap: dict):
                            for nm, meta in depmap.items():
                                if not isinstance(meta, dict):
                                    continue
                                dev = bool(meta.get("dev", False))
                                names_dev[nm] = names_dev.get(nm, False) or dev
                                sub = meta.get("dependencies")
                                if isinstance(sub, dict):
                                    _rec(sub)
                        _rec(obj["dependencies"])
                except Exception:
                    pass
                return names_dev

            # Collect direct declarations and parse lockfiles for transitives
            for pkg_path in pkg_files:
                try:
                    with open(pkg_path, "r", encoding="utf-8") as fh:
                        pj = _json.load(fh) or {}
                    deps = pj.get("dependencies", {}) or {}
                    dev = pj.get("devDependencies", {}) or {}
                    opt = pj.get("optionalDependencies", {}) or {}
                    for name in deps.keys():
                        _merge(name, "direct", "required", "normal")
                    for name in dev.keys():
                        _merge(name, "direct", "required", "development")
                    for name in opt.keys():
                        _merge(name, "direct", "optional", "normal")

                    # Lockfile-based transitives (package-lock.json or npm-shrinkwrap.json)
                    root_dir = _os.path.dirname(pkg_path)
                    for lock_name in ("package-lock.json", "npm-shrinkwrap.json"):
                        lock_path = _os.path.join(root_dir, lock_name)
                        if _os.path.isfile(lock_path):
                            try:
                                with open(lock_path, "r", encoding="utf-8") as lf:
                                    lock_obj = _json.load(lf) or {}
                                names_dev = _scan_npm_lock_obj(lock_obj)
                                for nm, is_dev in names_dev.items():
                                    # do not override direct mapping; mark others as transitive
                                    _merge(nm, "transitive", "required", "development" if is_dev else "normal")
                            except Exception:
                                # best-effort
                                pass
                except Exception:
                    continue
            return result

        if eco == Ecosystem.PYPI:
            py_files: List[str] = []
            req_files: List[str] = []
            lock_files: List[str] = []
            for root, _, files in _os.walk(base_dir):
                if Constants.PYPROJECT_TOML_FILE in files:
                    py_files.append(_os.path.join(root, Constants.PYPROJECT_TOML_FILE))
                if Constants.REQUIREMENTS_FILE in files:
                    req_files.append(_os.path.join(root, Constants.REQUIREMENTS_FILE))
                if Constants.UV_LOCK_FILE in files:
                    lock_files.append(_os.path.join(root, Constants.UV_LOCK_FILE))
                if Constants.POETRY_LOCK_FILE in files:
                    lock_files.append(_os.path.join(root, Constants.POETRY_LOCK_FILE))
            try:
                from versioning.parser import parse_pyproject_for_direct_pypi, parse_requirements_txt  # type: ignore
            except Exception:
                from src.versioning.parser import parse_pyproject_for_direct_pypi, parse_requirements_txt  # type: ignore
            # Direct dependencies from manifests
            for path in py_files:
                try:
                    recs = parse_pyproject_for_direct_pypi(path) or {}
                    for name, rec in recs.items():
                        _merge(
                            name.lower().replace("_", "-"),
                            getattr(rec, "relation", "direct"),
                            getattr(rec, "requirement", "required"),
                            getattr(rec, "scope", "normal"),
                        )
                except Exception:
                    continue
            for path in req_files:
                try:
                    recs = parse_requirements_txt(path) or {}
                    for name, rec in recs.items():
                        _merge(
                            name.lower().replace("_", "-"),
                            getattr(rec, "relation", "direct"),
                            getattr(rec, "requirement", "required"),
                            getattr(rec, "scope", "normal"),
                        )
                except Exception:
                    continue

            # Lockfile-derived transitives (uv.lock / poetry.lock)
            def _scan_pypi_lock(lock_path: str) -> list[tuple[str, bool]]:
                names: list[tuple[str, bool]] = []
                try:
                    try:
                        import tomllib as _toml  # type: ignore
                    except Exception:
                        import tomli as _toml  # type: ignore
                    with open(lock_path, "rb") as fh:
                        data = _toml.load(fh) or {}
                    pkgs = data.get("package")
                    if isinstance(pkgs, list):
                        for rec in pkgs:
                            if isinstance(rec, dict):
                                nm = rec.get("name")
                                if isinstance(nm, str) and nm.strip():
                                    name = nm.strip().lower().replace("_", "-")
                                    cat = str(rec.get("category", "")).strip().lower()
                                    grp = str(rec.get("group", "")).strip().lower()
                                    is_dev = cat in ("dev", "test") or grp in ("dev", "test")
                                    names.append((name, is_dev))
                    else:
                        # Fallback: best-effort regex scan
                        try:
                            import re as _re
                            with open(lock_path, "r", encoding="utf-8") as fh2:
                                text = fh2.read()
                            for m in _re.finditer(r'\bname\s*=\s*"(.*?)"', text):
                                nm = m.group(1)
                                if nm:
                                    names.append((nm.strip().lower().replace("_", "-"), False))
                        except Exception:
                            pass
                except Exception:
                    pass
                return names

            for lock in lock_files:
                for nm, is_dev in _scan_pypi_lock(lock):
                    _merge(nm, "transitive", "required", "development" if is_dev else "normal")

            return result

        if eco == Ecosystem.MAVEN:
            pom_files: List[str] = []
            if args.RECURSIVE:
                for root, _, files in _os.walk(base_dir):
                    if Constants.POM_XML_FILE in files:
                        pom_files.append(_os.path.join(root, Constants.POM_XML_FILE))
            else:
                path = _os.path.join(base_dir, Constants.POM_XML_FILE)
                if _os.path.isfile(path):
                    pom_files.append(path)
            import xml.etree.ElementTree as _ET
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for pom_path in pom_files:
                try:
                    tree = _ET.parse(pom_path)
                    pom = tree.getroot()
                    for dependencies in pom.findall(f"{ns}dependencies"):
                        for dependency in dependencies.findall(f"{ns}dependency"):
                            gid = dependency.find(f"{ns}groupId")
                            aid = dependency.find(f"{ns}artifactId")
                            if gid is None or gid.text is None or aid is None or aid.text is None:
                                continue
                            scope_node = dependency.find(f"{ns}scope")
                            scope = (scope_node.text.strip().lower() if scope_node is not None and scope_node.text else "")
                            scope_val = "testing" if scope == "test" else "normal"
                            opt_node = dependency.find(f"{ns}optional")
                            req_val = "optional" if (opt_node is not None and (opt_node.text or "").strip().lower() == "true") else "required"
                            coordinate = f"{gid.text}:{aid.text}"
                            # Coordinate and artifactId fallback
                            _merge(coordinate, "direct", req_val, scope_val)
                            _merge(aid.text, "direct", req_val, scope_val)
                except Exception:
                    continue
            return result

        return result
    except Exception:
        return {}


def apply_classification(args, instances) -> None:
    """Apply classification mapping onto the provided package instances."""
    try:
        _class_map = build_dependency_classification(args)
        if not isinstance(_class_map, dict):
            return
        eco = to_ecosystem(args.package_type)
        for mp in instances:
            keys = []
            if eco == Ecosystem.MAVEN and getattr(mp, "org_id", None):
                keys.append(f"{mp.org_id}:{mp.pkg_name}")
                keys.append(mp.pkg_name)  # artifactId fallback
            elif eco == Ecosystem.PYPI:
                keys.append(mp.pkg_name.lower().replace("_", "-"))
            else:
                keys.append(mp.pkg_name)
            for k in keys:
                hit = _class_map.get(k)
                if hit:
                    try:
                        mp.dependency_relation = hit.get("relation")
                        mp.dependency_requirement = hit.get("requirement")
                        mp.dependency_scope = hit.get("scope")
                    except Exception:
                        pass
                    break
    except Exception:
        # best-effort; never fail CLI on classification
        pass
