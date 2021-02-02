set -e


destRepo="$(cd $(dirname $0)/../../.. && pwd)"
tempDir="/tmp/import-temp-work"
rm -rf $tempDir
mkdir -p $tempDir
cd $tempDir

function usage() {
  echo "Usage: $0 group:artifact:version[:classifier][@extension] [group:artifact:version[:classifier][@extension]...]

This script downloads the given artifacts and confirms that their dependencies can be resolved successfully by maven"
  exit 1
}

internalAndroidRepo=$destRepo/prebuilts/androidx/internal

# usage: downloadArtifacts "$group:$artifact:$version[:classifier][@extension]..."
function downloadArtifacts() {
  if [ "$1" == "" ]; then
    usage
  fi
  echo downloading dependencies
  while [ "$1" != "" ]; do
    echo importing $1
    IFS=@ read -r dependency extension <<< "$1"
    IFS=: read -ra FIELDS <<< "${dependency}"
    groupId="${FIELDS[0]}"
    artifactId="${FIELDS[1]}"
    version="${FIELDS[2]}"
    classifier="${FIELDS[3]}"

    # download the actual artifact
    downloadArtifact "$groupId" "$artifactId" "$version" "$classifier" "$extension"

    # go to next artifact
    shift
  done
  echo done downloading dependencies
}

# usage: downloadArtifact "$group" "$artifact" "$version" "$classifier" "$extension"
function downloadArtifact() {
  pomPath="$PWD/pom.xml"
  echo creating $pomPath
  pomPrefix='<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.google.android.build</groupId>
  <artifactId>m2repository</artifactId>
  <version>1.0</version>
  <repositories>
    <repository>
      <id>androidx-local-internal</id>
      <name>Androidx Local Internal</name>
      <url>file://'"${internalAndroidRepo}"'/</url>
    </repository>
    <repository>
      <id>jcenter</id>
      <name>JCenter</name>
      <url>https://jcenter.bintray.com</url>
    </repository>
    <repository>
      <id>gradleplugins</id>
      <name>Gradle Plugins</name>
      <url>https://plugins.gradle.org/m2/</url>
    </repository>
  </repositories>
  <dependencies>
'

  pomSuffix='
  </dependencies>
  <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>2.8</version>
                <executions>
                    <execution>
                        <id>default-cli</id>
                        <configuration>
                            <includeScope>runtime</includeScope>
                            <addParentPoms>true</addParentPoms>
                            <copyPom>true</copyPom>
                            <useRepositoryLayout>true</useRepositoryLayout>
                            <outputDirectory>m2repository</outputDirectory>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
'


  groupId="$1"
  artifactId="$2"
  version="$3"
  classifier="$4"
  extension="$5"

  dependencyText=$(echo -e "\n    <dependency>\n      <groupId>${groupId}</groupId>\n      <artifactId>${artifactId}</artifactId>\n      <version>${version}</version>")
  [ $classifier ] && dependencyText+=$(echo -e "\n      <classifier>${classifier}</classifier>")
  [ $extension ] && dependencyText+=$(echo -e "\n      <type>${extension}</type>")
  dependencyText+=$(echo -e "\n    </dependency>")


  echo "${pomPrefix}${dependencyText}${pomSuffix}" > $pomPath
  echo done creating $pomPath

  mvn -f "$pomPath" dependency:resolve
}

function confirmMavenRepoEmpty() {
  repoPath=~/.m2/repository
  if stat $repoPath >/dev/null 2>/dev/null; then
    echo "Must do:
  rm -rf $repoPath
before running this script to be sure that its results are correct"
    exit 1
  fi
}

function main() {
  confirmMavenRepoEmpty
  downloadArtifacts "$@"
}

main "$@"

