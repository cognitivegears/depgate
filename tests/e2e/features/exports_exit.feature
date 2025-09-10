Feature: Exports and exit codes
  Background:
    Given fake registries are enabled
    And a clean artifacts directory

  Scenario: JSON export with warnings gated to non-zero
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -p  | shortver-pkg |
      | -a  | heur  |
      | -o  | <json_path> |
      | --error-on-warnings | true |
    Then the process exits with code 3
    And the JSON output at "<json_path>" record for "shortver-pkg" has risk flags:
      | field            | expected |
      | risk.minVersions | true     |
