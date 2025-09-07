Feature: Quiet mode
  Background:
    Given fake registries are enabled

  Scenario: -q suppresses stdout
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -p  | left-pad |
      | -q  | true |
    Then the process exits with code 0
    And stdout is empty or whitespace only
