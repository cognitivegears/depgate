Feature: Network failures
  Background:
    Given fake registries are enabled
    And a clean artifacts directory

  Scenario: Timeout surfaces as connection error exit code
    Given fake registry mode "timeout"
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -p  | left-pad |
    Then the process exits with code 2

  Scenario: Generic connection error surfaces exit code
    Given fake registry mode "conn_error"
    When I run depgate with arguments:
      | arg | value |
      | -t  | pypi  |
      | -p  | requests |
    Then the process exits with code 2
