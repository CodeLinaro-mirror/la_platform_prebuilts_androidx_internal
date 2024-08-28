#!/usr/bin/python3

"""A script to remove old alpha version prebuilts.

Script deletes all but the last two alpha versions of artifacts in this prebuilt
directory.
"""

import os
import shutil
from packaging.version import Version

SCRIPT_PATH = os.path.realpath(os.path.dirname(__file__))
directories = [x for x in os.walk(SCRIPT_PATH)]
for directory in directories:
  alphaVersionDirs = [subdir for subdir in directory[1] if "alpha" in subdir]
  if any(alphaVersionDirs):
    # Use Version to sort so we handle 1.9.0 and 1.10.0 correctly
    # Drop last two alphas as they still might be used
    everythingExceptLastTwoAlphas = sorted(alphaVersionDirs, key=Version)[:-2]
    for alphaVersion in everythingExceptLastTwoAlphas:
      shutil.rmtree(directory[0] + "/" + alphaVersion)
