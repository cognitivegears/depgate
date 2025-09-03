# DepGate (hard fork of Dependency Combobulator)
![BHEU BADGE](docs/bheu21.svg) ![python](https://img.shields.io/badge/Python-14354C) ![maintained](https://img.shields.io/badge/Maintained%3F-yes-green.svg)

DepGate is an open-source, modular and extensible framework to detect and prevent dependency confusion and related supply‑chain risks. It supports multiple sources (e.g., GitHub Packages, JFrog Artifactory) and package managers (e.g., npm, maven, PyPI).

### Intended Audiences

The framework can be used by security auditors, pentesters and even baked into an enterprise's application security program and release cycle in an automated fashion.
### Main features
* Pluggable - interject on commit level, build, release steps in SDLC.
* Expandable - easily add your own package management scheme or code source of choice
* General-purpose Heuristic-Engine - an abstract package data model provides agnostic heuristic approach
* Supporting wide range of technologies
* Flexible - decision trees can be determined upon insights or verdicts provided by the toolkit


### Easly extensible

The project is putting practicionar's ability to extend and fit the toolkit to her own specific needs. As such, it is designed to be able to extend it to other sources, public registries, package management schemes and extending the abstract model and accompnaied heuristics engine.


## Installation

Clone this repository and install dependencies with uv:

Use uv to create a local environment and install dependencies:

```
uv venv
source .venv/bin/activate
uv sync
```

## Arguments (--help)
```
  -h, --help            show this help message and exit
  -t {npm,maven,pypi}, --type {npm,maven,pypi}
                        Package Manager Type, i.e: npm, maven, pypi
  -l LIST_FROM_FILE, --load_list LIST_FROM_FILE
                        Load list of dependencies from a file
  -d FROM_SRC, --directory FROM_SRC
                        Extract dependencies from local source repository
  -p--package SINGLE    Name a single package.
  -c CSV, --csv CSV     Export packages properties onto CSV file
  -j JSON, --json JSON  Export packages properties onto JSON file
  -a {compare,comp,heuristics,heur}, --analysis {compare,comp,heuristics,heur}
                        Required analysis level - compare (comp), heuristics
                        (heur) (default: compare)
  -r, --recursive       Recursively analyze dependencies
  --loglevel LOG_LEVEL  Set the logging level (default: INFO)
  --logfile LOG_FILE    Set the logging file
  -q, --quiet           Suppress console output
  --error-on-warning    Exit with error code if warnings are found

Hard fork of Apiiro/combobulator by cognitivegears
```
Supported package types (-t, --t): npm, maven, pypi

Supported source dependency assessment:
- From file containing the dependency identifiers line-by-line. (-l, --load_list)
- By analyzing the appropriate repo's software bill-of-materials (e.g. package.json, pom.xml) (-d, --directory)
- Naming a single identifier (-p, --package)

Analysis level is customizable as you can build your own preferred analysis profile in seconds. DepGate ships with several analysis levels out-of-the-box, selected by -a, --analysis.

Supported output format:
- Screen stdout (default)
- CSV export to designated file -(-CSV)

## Usage examples

https://user-images.githubusercontent.com/90651458/140915800-c267034b-90c9-42d1-b12a-83e12f70d44e.mp4


## Credits & Attribution

DepGate is a hard fork of "Dependency Combobulator" originally developed by Apiiro and its contributors: https://github.com/apiiro/combobulator

This fork is maintained by cognitivegears. The original authors and contributors are credited in CONTRIBUTORS.md. The project continues under the Apache License 2.0, preserving the original license and attribution.
