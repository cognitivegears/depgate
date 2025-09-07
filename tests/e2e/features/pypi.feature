Feature: PyPI single package and requirements scan
  Background:
    Given fake registries are enabled
    And a clean artifacts directory

  Scenario Outline: Analyze a single PyPI package
    When I run depgate with arguments:
      | arg | value |
      | -t  | pypi  |
      | -p  | <pkg> |
      | -a  | heur  |
      | -j  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" record for "<pkg>" has fields:
      | field            | expected |
      | exists           | <exists> |
      | risk.isMissing   | <is_missing> |
      | risk.minVersions | <min_versions> |
      | risk.isNew       | <is_new> |

    Examples:
      | pkg          | exists | is_missing | min_versions | is_new |
      | requests     | true   | false      | false        | false  |
      | pypi-new     | true   | false      | false        | true   |
      | pypi-short   | true   | false      | true         | false  |
      | pypi-missing | false  | true       |              |        |

  Scenario: Scan requirements from temp dir
    Given a temp directory with requirements.txt:
      """
      requests==2.0.0
      pypi-short==0.0.1
      """
    When I run depgate with arguments:
      | arg | value |
      | -t  | pypi  |
      | -d  | <tmp_dir> |
      | -a  | heur  |
      | -j  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" contains records for:
      | packageName |
      | requests    |
      | pypi-short  |
