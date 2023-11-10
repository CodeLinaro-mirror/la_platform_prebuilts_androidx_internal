#!/usr/bin/python3

"""A script to remove old alpha/beta version prebuilts.

Script deletes all alpha/beta unless they are the last two released versions
of the artifacts.
"""

import os
import shutil
import re
from packaging.version import Version

versionPattern = re.compile("^[0-9]+\.[0-9]+\..*$")
SCRIPT_PATH = os.path.realpath(os.path.dirname(__file__))
directories = [x for x in os.walk(SCRIPT_PATH)]
for directory in directories:
  # Use Version to sort so we handle 1.9.0 and 1.10.0 correctly
  # Drop last two alphas as they still might be used
  # fixeddocs is excluded due to androidx/concurrent/concurrent-futures/1.0.0-fixeddocs01
  versionDirs = sorted([subdir
                        for subdir in directory[1]
                        if versionPattern.match(subdir) and "fixeddocs" not in subdir
                        ], key=Version)[:-2]
  alphaBetaVersionDirs = [subdir for subdir in versionDirs if "alpha" in subdir or "beta" in subdir]
  if any(alphaBetaVersionDirs):
    for version in alphaBetaVersionDirs:
      shutil.rmtree(directory[0] + "/" + version)
