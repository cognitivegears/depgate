Feature: NPM single package (compare and heuristics)
  Background:
    Given fake registries are enabled
    And a clean artifacts directory

  Scenario Outline: Analyze a single npm package with JSON export
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -p  | <pkg> |
      | -a  | <level> |
      | -o  | <json_path> |
    Then the process exits with code <exit_code>
    And the JSON output at "<json_path>" contains 1 record for "<pkg>" with:
      | field         | expected |
      | exists        | <exists> |
      | risk.hasRisk  | <has_risk> |

    Examples:
      | pkg         | level   | exists | has_risk | exit_code |
      | left-pad    | compare | true   | false    | 0         |
      | missing-pkg | compare | false  | true     | 0         |

  Scenario Outline: NPM heuristics risk flags
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -p  | <pkg> |
      | -a  | heur  |
      | -o  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" record for "<pkg>" has risk flags:
      | field            | expected |
      | risk.isMissing   | <is_missing> |
      | risk.hasLowScore | <low_score> |
      | risk.minVersions | <min_versions> |
      | risk.isNew       | <is_new> |

    Examples:
      | pkg          | is_missing | low_score | min_versions | is_new |
      | left-pad     | false      | false     | false        | false  |
      | badscore-pkg | false      | true      | false        | false  |
      | shortver-pkg | false      | false     | true         | false  |
      | newpkg       | false      | false     | false        | true   |
      | missing-pkg  | true       |           |              |        |
