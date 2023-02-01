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

import unittest
import os
from import_release_prebuilts import *

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


if __name__ == '__main__':
    unittest.main()