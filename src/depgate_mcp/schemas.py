from __future__ import annotations

# Draft-07 JSON Schemas for MCP tools (stable contracts)

LOOKUP_LATEST_VERSION_INPUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "ecosystem": {"type": ["string", "null"], "enum": ["npm", "pypi", "maven", None]},
        "versionRange": {"type": ["string", "null"]},
        "registryUrl": {"type": ["string", "null"]},
        "projectDir": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}

LOOKUP_LATEST_VERSION_OUTPUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["name", "ecosystem"],
    "properties": {
        "name": {"type": "string"},
        "ecosystem": {"type": "string"},
        "latestVersion": {"type": ["string", "null"]},
        "satisfiesRange": {"type": ["boolean", "null"]},
        "publishedAt": {"type": ["string", "null"]},
        "deprecated": {"type": ["boolean", "null"]},
        "yanked": {"type": ["boolean", "null"]},
        "license": {"type": ["string", "null"]},
        "registryUrl": {"type": ["string", "null"]},
        "repositoryUrl": {"type": ["string", "null"]},
        "cache": {"type": "object"},
        "candidates": {"type": ["integer", "null"]},
    },
    "additionalProperties": False,
}

SCAN_PROJECT_INPUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["projectDir"],
    "properties": {
        "projectDir": {"type": "string", "minLength": 1},
        "includeDevDependencies": {"type": ["boolean", "null"]},
        "includeTransitive": {"type": ["boolean", "null"]},
        "respectLockfiles": {"type": ["boolean", "null"]},
        "offline": {"type": ["boolean", "null"]},
        "strictProvenance": {"type": ["boolean", "null"]},
        "paths": {"type": ["array", "null"], "items": {"type": "string"}},
        "analysisLevel": {"type": ["string", "null"], "enum": ["compare", "comp", "heuristics", "heur", "policy", "pol", "linked"]},
        "ecosystem": {"type": ["string", "null"], "enum": ["npm", "pypi", "maven", None]},
    },
    "additionalProperties": False,
}

SCAN_DEPENDENCY_INPUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["name", "version", "ecosystem"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "ecosystem": {"type": "string", "enum": ["npm", "pypi", "maven"]},
        "registryUrl": {"type": ["string", "null"]},
        "offline": {"type": ["boolean", "null"]},
    },
    "additionalProperties": False,
}

SCAN_RESULTS_OUTPUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["packages", "summary", "findings"],
    "properties": {
        "packages": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "object",
                "required": ["name", "ecosystem"],
                "properties": {
                    "name": {"type": "string"},
                    "ecosystem": {"type": "string", "enum": ["npm", "pypi", "maven"]},
                    "version": {"type": ["string", "null"]},
                    "repositoryUrl": {"type": ["string", "null"]},
                    "license": {"type": ["string", "null"]},
                    "linked": {"type": ["boolean", "null"]},
                    "repoVersionMatch": {"type": ["object", "null"]},
                    "policyDecision": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "findings": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
        },
        "summary": {
            "type": "object",
            "required": ["count"],
            "properties": {"count": {"type": "integer", "minimum": 0}},
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}
