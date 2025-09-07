Feature: Maven single and pom scan
  Background:
    Given fake registries are enabled
    And a clean artifacts directory

  Scenario Outline: Analyze Maven coordinate
    Given a package list file containing "<artifact>"
    When I run depgate with arguments:
      | arg | value |
      | -t  | maven |
      | -l  | <list_file> |
      | -a  | heur  |
      | -j  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" contains 1 record for "<artifact>" with:
      | field            | expected |
      | exists           | <exists> |
      | risk.minVersions | <min_versions> |

    Examples:
      | artifact     | exists | min_versions |
      | present-art  | true   | false        |
      | missing-art  | false  |              |

  Scenario: Scan pom.xml in temp dir
    Given a temp directory with pom.xml:
      """
      <project xmlns="http://maven.apache.org/POM/4.0.0"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
        <modelVersion>4.0.0</modelVersion>
        <groupId>example</groupId>
        <artifactId>demo</artifactId>
        <version>1.0.0</version>
        <dependencies>
          <dependency><groupId>com.example</groupId><artifactId>present-art</artifactId><version>1.0.0</version></dependency>
        </dependencies>
      </project>
      """
    When I run depgate with arguments:
      | arg | value |
      | -t  | maven |
      | -d  | <tmp_dir> |
      | -a  | heur  |
      | -j  | <json_path> |
    Then the process exits with code 0
    And the JSON output at "<json_path>" contains records for:
      | packageName |
      | present-art |
