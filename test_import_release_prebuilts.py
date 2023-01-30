#!/usr/bin/python3
#
# Copyright (C) 2021 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from collections import defaultdict
from import_release_prebuilts import *
from unittest.mock import patch
import os
import unittest

DOCS_PUBLIC_BUILD_GRADLE_REL_TEST = './docs-public/test_build.gradle'
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
TEST_DIR_FP = os.path.abspath(os.path.join(SCRIPT_DIR, 'test_dir'))
DOCS_PUBLIC_BUILD_GRADLE_FP_TEST = os.path.join(TEST_DIR_FP, DOCS_PUBLIC_BUILD_GRADLE_REL_TEST)


class TestArtifactVerification(unittest.TestCase):

    def test_find_invalidly_formatted_artifact(self):
        invalid = find_invalidly_formatted_artifact(["androidx.foo:foo"])
        self.assertFalse(invalid)

        invalid = find_invalidly_formatted_artifact(["androidx.foo:foo-bar"])
        self.assertFalse(invalid)

        invalid = find_invalidly_formatted_artifact(["androidx.foo.bar:bar"])
        self.assertFalse(invalid)

        invalid = find_invalidly_formatted_artifact(["androidx.foo.bar:bar-qux"])
        self.assertFalse(invalid)

        invalid = find_invalidly_formatted_artifact(["androidx:foo"])
        self.assertEqual("androidx:foo", invalid)

        invalid = find_invalidly_formatted_artifact(["androidx.:foo"])
        self.assertEqual("androidx.:foo", invalid)

        invalid = find_invalidly_formatted_artifact(["foo"])
        self.assertEqual("foo", invalid)

        invalid = find_invalidly_formatted_artifact(["foo:foo", "androidx.foo.bar:bar"])
        self.assertEqual("foo:foo", invalid)

        invalid = find_invalidly_formatted_artifact(["androidx.foo:foo", "androidx.foo"])
        self.assertEqual("androidx.foo", invalid)

    def test_get_coordinates_from_artifact(self):
        group_id, artifact_id = get_coordinates_from_artifact(
            "androidx.foo:foo")
        self.assertEqual("androidx.foo", group_id)
        self.assertEqual("foo", artifact_id)

        group_id, artifact_id = get_coordinates_from_artifact(
            "androidx.foo.bar:bar")
        self.assertEqual("androidx.foo.bar", group_id)
        self.assertEqual("bar", artifact_id)

        group_id, artifact_id = get_coordinates_from_artifact(
            "androidx.foo:foo-bar")
        self.assertEqual("androidx.foo", group_id)
        self.assertEqual("foo-bar", artifact_id)

        group_id, artifact_id = get_coordinates_from_artifact(
            "androidx.foo.bar:bar-qux")
        self.assertEqual("androidx.foo.bar", group_id)
        self.assertEqual("bar-qux", artifact_id)


class TestVersionUpdates(unittest.TestCase):

    def test_should_update_artifact_returns_true(self):
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", ["androidx.foo"], ["androidx.foo:foo"]))
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", ["androidx.foo"], []))
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", ["foo"], []))
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", ["androidx.foo", "androidx.bar"],
            ["androidx.bar:bar", "androidx.qux:qux"]))
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", [], ["androidx.foo:foo"]))
        self.assertTrue(should_update_artifact(
            "androidx.foo", "foo", [],
            ["androidx.foo:foo", "androidx.bar:bar"]))

    def test_should_update_artifact_returns_false(self):
        self.assertFalse(should_update_artifact(
            "androidx.foo", "foo", ["androidx.bar"], []))
        self.assertFalse(should_update_artifact(
            "androidx.foo", "foo", ["androidx.bar"], ["androidx.foo:foo-bar"]))
        self.assertFalse(should_update_artifact(
            "androidx.foo", "foo", [],
            ["androidx.bar:bar", "androidx.qux:qux"]))
        self.assertFalse(should_update_artifact(
            "androidx.foo", "foo", [], ["foo"]))

    def test_update_docs_public_build_gradle(self):
        # Get the current state of the build.gradle file.
        with open(DOCS_PUBLIC_BUILD_GRADLE_FP_TEST, 'r') as f:
            dpbg_lines_before = f.readlines()

        artifact_ver_map = {
            "androidx.bar:bar": "1.0.0",
            "androidx.foo:foo": "1.3.0-alpha02",
            "androidx.foo:foo-bar": "1.3.0-alpha02",
            "androidx.foo:foo-samples": "1.3.0-alpha02",
            "androidx.qux:qux": "2.3.0-beta04",
        }
        # Get the updated the build.gradle file lines.
        with unittest.mock.patch('builtins.input', return_value="yes"):
            new_lines = generate_updated_docs_public_build_gradle(
                artifact_ver_map, DOCS_PUBLIC_BUILD_GRADLE_FP_TEST)
        correct_outline_lines = [
            "plugins {\n",
            "    id(\"com.android.library\")\n",
            "    id(\"AndroidXDocsPlugin\")\n",
            "}\n",
            "\n",
            "dependencies {\n",
            "    docs(\"androidx.bar:bar:1.0.0\")\n",
            "    docs(\"androidx.foo:foo:1.3.0-alpha02\")\n",
            "    docs(\"androidx.foo:foo-bar:1.3.0-alpha02\")\n",
            "    samples(\"androidx.foo:foo-samples:1.3.0-alpha02\")\n",
            "    docs(\"androidx.qux:qux:2.3.0-beta04\")\n",
            "}\n"
        ]
        self.assertEqual(new_lines, correct_outline_lines)


class TestLongFormSyntax(unittest.TestCase):

    def test_correct_syntax_is_parsed(self):
        long_form_test_str = "1111/androidx.foo"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        parse_long_form(long_form_test_str, source_to_artifact)
        self.assertTrue(source_to_artifact.get("1111"))
        self.assertTrue(source_to_artifact["1111"].get("groups"))
        self.assertFalse(source_to_artifact["1111"].get("artifacts"))
        self.assertEqual(source_to_artifact["1111"]["groups"],
                         ["androidx.foo"])

        long_form_test_str = "1111/androidx.foo:foo-bar"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        parse_long_form(long_form_test_str, source_to_artifact)
        self.assertTrue(source_to_artifact.get("1111"))
        self.assertFalse(source_to_artifact["1111"].get("groups"))
        self.assertTrue(source_to_artifact["1111"].get("artifacts"))
        self.assertEqual(source_to_artifact["1111"]["artifacts"],
                         ["androidx.foo:foo-bar"])

        long_form_test_str = "1111/androidx.foo,2222/androidx.foo:foo-bar"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        parse_long_form(long_form_test_str, source_to_artifact)
        self.assertTrue(source_to_artifact.get("1111"))
        self.assertTrue(source_to_artifact["1111"].get("groups"))
        self.assertFalse(source_to_artifact["1111"].get("artifacts"))
        self.assertEqual(source_to_artifact["1111"]["groups"],
                         ["androidx.foo"])
        self.assertTrue(source_to_artifact.get("2222"))
        self.assertFalse(source_to_artifact["2222"].get("groups"))
        self.assertTrue(source_to_artifact["2222"].get("artifacts"))
        self.assertEqual(source_to_artifact["2222"]["artifacts"],
                         ["androidx.foo:foo-bar"])

        long_form_test_str = ("1111/androidx.foo,1111/androidx.bar:bar,"
                              "2222/androidx.foo,3333/androidx.bar:bar,"
                              "3333/androidx.qux,4444/androidx.qux:qux,"
                              "4444/androidx.qux:qux-ktx")
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        parse_long_form(long_form_test_str, source_to_artifact)
        self.assertTrue(source_to_artifact.get("1111"))
        self.assertTrue(source_to_artifact["1111"].get("groups"))
        self.assertTrue(source_to_artifact["1111"].get("artifacts"))
        self.assertEqual(source_to_artifact["1111"]["groups"],
                         ["androidx.foo"])
        self.assertEqual(source_to_artifact["1111"]["artifacts"],
                         ["androidx.bar:bar"])
        self.assertTrue(source_to_artifact.get("2222"))
        self.assertTrue(source_to_artifact["2222"].get("groups"))
        self.assertFalse(source_to_artifact["2222"].get("artifacts"))
        self.assertEqual(source_to_artifact["2222"]["groups"],
                         ["androidx.foo"])
        self.assertTrue(source_to_artifact.get("3333"))
        self.assertTrue(source_to_artifact["3333"].get("groups"))
        self.assertTrue(source_to_artifact["3333"].get("artifacts"))
        self.assertEqual(source_to_artifact["3333"]["groups"],
                         ["androidx.qux"])
        self.assertEqual(source_to_artifact["3333"]["artifacts"],
                         ["androidx.bar:bar"])
        self.assertTrue(source_to_artifact.get("4444"))
        self.assertFalse(source_to_artifact["4444"].get("groups"))
        self.assertTrue(source_to_artifact["4444"].get("artifacts"))
        self.assertEqual(source_to_artifact["4444"]["artifacts"],
                         ["androidx.qux:qux", "androidx.qux:qux-ktx"])

    def test_incorrect_syntax_throws_error(self):
        long_form_test_str = "1111androidx.foo"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        result = parse_long_form(long_form_test_str, source_to_artifact)
        self.assertFalse(result)

        long_form_test_str = "1111/foo"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        result = parse_long_form(long_form_test_str, source_to_artifact)
        self.assertFalse(result)

        long_form_test_str = "1111/androidx-foo"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        result = parse_long_form(long_form_test_str, source_to_artifact)
        self.assertFalse(result)

        long_form_test_str = "1111/androidx.foo,2222/androidx.foo/foo-bar"
        source_to_artifact = defaultdict(lambda: defaultdict(list))
        result = parse_long_form(long_form_test_str, source_to_artifact)
        self.assertFalse(result)

        long_form_test_str = ("1111/androidx.foo,1111/androidx.bar:bar,"
                              "2222/androidx.foo,/androidx.bar:bar,"
                              "3333/androidx.qux,4444/androidx.qux:qux,"
                              "4444/androidx.qux:qux-ktx")
        result = parse_long_form(long_form_test_str, source_to_artifact)
        self.assertFalse(result)

class TestDocsUpdate(unittest.TestCase):

    def test_should_update_docs_returns_false(self):
        self.assertFalse(should_update_docs(
            "androidx.appsearch:appsearch-compiler"))
        self.assertFalse(should_update_docs(
            "androidx.appsearch:appsearch-debug-view"))
        self.assertFalse(should_update_docs(
            "androidx.benchmark:benchmark-gradle-plugin"))
        self.assertFalse(should_update_docs(
            "androidx.compose:compiler:compiler"))
        self.assertFalse(should_update_docs(
            "androidx.compose:compiler:compiler-hosted"))
        self.assertFalse(should_update_docs(
            "androidx.compose:material:material-icons-extended"))
        self.assertFalse(should_update_docs(
            "androidx.compose:ui:ui-android-stubs"))
        self.assertFalse(should_update_docs(
            "androidx.compose:ui:ui-test-manifest"))
        self.assertFalse(should_update_docs(
            "androidx.hilt:hilt-compiler"))
        self.assertFalse(should_update_docs(
            "androidx.inspection:inspection-gradle-plugin"))
        self.assertFalse(should_update_docs(
            "androidx.jetifier:jetifier-processor"))
        self.assertFalse(should_update_docs(
            "androidx.lifecycle:lifecycle-compiler"))
        self.assertFalse(should_update_docs(
            "androidx.media2:media2-exoplayer"))
        self.assertFalse(should_update_docs(
            "androidx.navigation:navigation-safe-args-generator"))
        self.assertFalse(should_update_docs(
            "androidx.navigation:navigation-safe-args-gradle-plugin"))
        self.assertFalse(should_update_docs(
            "androidx.remotecallback:remotecallback-processor"))
        self.assertFalse(should_update_docs(
            "androidx.resourceinspection:resourceinspection-processor"))
        self.assertFalse(should_update_docs(
            "androidx.room:room-compiler"))
        self.assertFalse(should_update_docs(
            "androidx.room:room-compiler-processing"))
        self.assertFalse(should_update_docs(
            "androidx.room:room-compiler-processing-testing"))
        self.assertFalse(should_update_docs(
            "androidx.versionedparcelable:versionedparcelable-compiler"))
        self.assertFalse(should_update_docs(
            "androidx.compose.animation:animation-tooling-internal"))

    def test_should_update_docs_returns_true(self):
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.foo:foo-bar"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.camera:camera-video"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.collection:collection"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.compose:material:material:material-samples"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.compose:ui:ui-graphics"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.dynamicanimation:dynamicanimation-ktx"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.emoji2:emoji2-views-helper"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.glance:glance-appwidget"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.lifecycle:lifecycle-common-java8"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.media2:media2-session"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.paging:paging-samples"))
        with unittest.mock.patch('builtins.input', return_value="yes"):
            self.assertTrue(should_update_docs(
                "androidx.remotecallback:remotecallback"))

if __name__ == '__main__':
    unittest.main()
