Feature: NPM directory scan
  Background:
    Given fake registries are enabled
    And a clean artifacts directory
    And a temp directory with package.json:
      """
      {
        "name": "tmp",
        "version": "0.0.1",
        "dependencies": { "left-pad": "^1.3.0", "shortver-pkg": "1.0.0" }
      }
      """

  Scenario: Scan npm project and export JSON
    When I run depgate with arguments:
      | arg | value |
      | -t  | npm   |
      | -d  | <tmp_dir> |
      | -a  | heur  |
      | -o  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" contains records for:
      | packageName |
      | left-pad    |
      | shortver-pkg |
