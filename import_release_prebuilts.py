#!/usr/bin/python3

from collections import defaultdict
from distutils.dir_util import copy_tree
from shutil import rmtree
import argparse
import glob
import os, sys, zipfile
import subprocess

# cd into directory of script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# See go/fetch_artifact for details on this script.
FETCH_ARTIFACT = '/google/data/ro/projects/android/fetch_artifact'
DOCS_PUBLIC_BUILD_GRADLE_REL = './docs-public/build.gradle'
FRAMEWORKS_SUPPORT_FP = os.path.abspath(os.path.join(os.getcwd(), '..', '..', '..', 'frameworks', 'support'))
DOCS_PUBLIC_BUILD_GRADLE_FP = os.path.join(FRAMEWORKS_SUPPORT_FP, DOCS_PUBLIC_BUILD_GRADLE_REL)
GIT_TREE_ARGS = '-C ./../../../frameworks/support/'
summary_log = []
publish_docs_log = []
prebuilts_log = []


def print_e(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)

def cp(src_path, dst_path):
	if not os.path.exists(dst_path):
		os.makedirs(dst_path)
	if not os.path.exists(src_path):
		print_e('cp error: Source path %s does not exist.' % src_path)
		return None
	try:
		copy_tree(src_path, dst_path)
	except DistutilsFileError as err:
		print_e('FAIL: Unable to copy %s to destination %s')
		return None
	return dst_path

def rm(path):
	if os.path.isdir(path):
		rmtree(path)
	elif os.path.exists(path):
		os.remove(path)

def ask_yes_or_no(question):
	while(True):
	    reply = str(input(question+' (y/n): ')).lower().strip()
	    if reply:
		    if reply[0] == 'y': return True
		    if reply[0] == 'n': return False
	    print("Please respond with y/n")

def fetch_artifact(target, build_id, artifact_path):
	download_to = os.path.join('.', os.path.dirname(artifact_path))
	print('Fetching %s from %s with build ID %s ...' % (artifact_path, target, build_id))
	print("download_to: ", download_to)
	if not os.path.exists(download_to):
		os.makedirs(download_to)
	print("If this script hangs, try running glogin or gcert.")
	fetch_cmd = [FETCH_ARTIFACT, '--bid', str(build_id), '--target', target, artifact_path,
				 download_to]
	try:
		subprocess.check_call(fetch_cmd, stderr=subprocess.STDOUT)
	except subprocess.CalledProcessError:
		print_e('FAIL: Unable to retrieve %s artifact for build ID %s' % (artifact_path, build_id))
		print_e('Please make sure you are authenticated for build server access!')
		return None
	return artifact_path

def extract_artifact(artifact_path):
	# Unzip the repo archive into a separate directory.
	repo_dir = os.path.basename(artifact_path)[:-4]
	with zipfile.ZipFile(artifact_path) as zipFile:
		zipFile.extractall(repo_dir)
	return repo_dir

def get_repo_androidx_path(repo_dir):
	# Check that ${repo_path}/m2repository/androidx exists
	repo_androidx_path = os.path.join(os.getcwd(), "./%s/m2repository/androidx" % repo_dir)
	if not os.path.exists(repo_androidx_path):
		print_e("FAIL: Downloaded artifact zip %s.zip does not contain m2repository/androidx" % repo_dir)
		return None
	return repo_androidx_path

def get_group_id_sub_path(group_id):
	""" Gets the group_id filepath within the m2repository repo.

	Assumes that androidx is supplied by get_repo_androidx_path()

	Example: "androidx.compose.animation" returns "compose/animation"

	Args: group_id
	Returns: the group_id subpath
	"""
	return group_id.replace("androidx.", "").replace(".", "/")

def get_coordinates_from_artifact(artifact):
	"""Get the group from an artifact

	Artifacts will have the format: `<group_id>:<artifact_id>`

	Args:
		artifact: the artifact to obtain the group id for

	Returns:
		Tuple of (group_id, artifact_id)
	"""
	coordinates = artifact.split(':')
	return coordinates[0], coordinates[1]

def copy_and_merge_artifacts(repo_dir, dest_dir, group_ids, artifacts):
	repo_androidx_path = get_repo_androidx_path(repo_dir)
	if not repo_androidx_path: return None
	if not group_ids and not artifacts:
		return cp(repo_androidx_path, dest_dir)
	if group_ids:
		# Copy over group_ids that were specified on the command line
		for group in group_ids:
			group_id_sub_path = get_group_id_sub_path(group)
			repo_group_path = os.path.join(repo_androidx_path, group_id_sub_path)
			if not os.path.exists(repo_group_path):
				print_e("Failed to find group_id %s in the artifact zip file" % group)
				return None
			dest_group_path = os.path.join(dest_dir, group_id_sub_path)
			if not cp(repo_group_path, dest_group_path):
				print_e("Failed to find copy %s to %s" % (repo_group_path, dest_group_path))
				return None
	if artifacts:
		# Copy over artifact_ids that were specified on the command line
		for artifact in artifacts:
			group_id, artifact_id = get_coordinates_from_artifact(artifact)
			group_id_sub_path = get_group_id_sub_path(group_id)
			repo_artifact_path = os.path.join(repo_androidx_path, group_id_sub_path, artifact_id)
			if not os.path.exists(repo_artifact_path):
				print_e("Failed to find artifact %s in the artifact zip file" % artifact)
				return None
			dest_artifact_path = os.path.join(dest_dir, group_id_sub_path, artifact_id)
			if not cp(repo_artifact_path, dest_artifact_path):
				print_e("Failed to find copy %s to %s" % (repo_artifact_path, dest_artifact_path))
				return None
	return dest_dir

def fetch_and_extract(target, build_id, file, artifact_path=None):
	if not artifact_path:
		artifact_path = fetch_artifact(target, build_id, file)
	if not artifact_path:
		return None
	return extract_artifact(artifact_path)

def remove_type_aar_from_pom_files(repo_dir):
	# Only search pom files to in <repo_dir>
	print("Removing <type>aar</type> from the pom files...", end = '')
	try:
		# Comment out <type>aar</type> in our pom files
		# This is being done as a workaround for b/118385540
		# TODO: Remove this method once https://github.com/gradle/gradle/issues/7594 is fixed
		subprocess.check_call("find " + repo_dir + " -name *.pom | xargs sed 's|^      <type>aar</type>$|      <!--<type>aar</type>-->|' -i", shell=True)
	except subprocess.CalledProcessError:
		print("failed!")
		print_e("FAIL: Failed to remove <type>aar</type> from the pom files")
		summary_log.append("FAILED to remove <type>aar</type> from the pom files")
		return False
	print("Successful")
	summary_log.append("<type>aar</type> was removed from the pom files")
	return True

def remove_maven_metadata_files(repo_dir):
	# Only search for maven-metadata files to in <repo_dir>
	print("Removing maven-metadata.xml* files from the import...", end = '')
	for maven_metadata_file in glob.glob(repo_dir + "/**/maven-metadata.xml*", recursive=True):
		os.remove(maven_metadata_file)
	print("Successful")
	summary_log.append("Removed maven-metadata.xml* files from the import")
	return True

def update_new_artifacts(group_id_file_path, artifact_ver_map, group_id, groups, artifacts, source):
	# Finds each new library having group_id <group_id> under <group_id_file_path> and
	#     updates <artifact_ver_map> with this new library
	# Returns True iff at least one library was found
	success = False
	# Walk filepath to get versions for each artifact_id
	for parent_file_path, dirs, _ in os.walk(group_id_file_path):
		for dir_name in dirs:
			if dir_name[0].isnumeric():
				# Version directories have format version as dir_name, for example: 1.1.0-alpha06
				version = dir_name
				# Get artifact_id from filepath
				artifact_id = parent_file_path.strip('/').split('/')[-1]
				# We need to recompute the group_id because git diff will only show the
				# first 2 directories for new group ids, whereas group ids can have more than
				# 2 directories, such as androidx.compose.animation
				real_group_id = ".".join(parent_file_path.strip('/').split('/')[:-1])
				update_version_maps(artifact_ver_map,
									real_group_id,
									artifact_id,
									version,
									groups,
									artifacts,
									source)
				success = True
	if not success:
		print_e("Failed to find any artifact_ids in filepath: %s" % group_id_file_path)
	return success

def should_update_artifact(group_id, artifact_id, groups, artifacts):
	# If a artifact or group list was specified and if the artifact_id or group_id were NOT specified
	# in either list on the command line, return false
	should_update = False
	if (groups) or (artifacts):
		if groups:
			if group_id.replace("androidx.", "") in groups:
				should_update = True
			if group_id in groups:
				should_update = True
		if artifacts and ("%s:%s" % (group_id, artifact_id) in artifacts):
			should_update = True
	else:
		should_update = True
	return should_update

def update_version_maps(artifact_ver_map, group_id, artifact_id, version, groups, artifacts, source):
	if should_update_artifact(group_id, artifact_id, groups, artifacts):
		if group_id + ":" + artifact_id not in artifact_ver_map:
			artifact_ver_map[group_id + ":" + artifact_id] = version
			summary_log.append("Prebuilts: %s:%s --> %s" % (group_id, artifact_id, version))
			prebuilts_log.append("%s:%s:%s from %s" % (group_id, artifact_id, version, source))

def get_updated_version_map(groups, artifacts, source):
	try:
		# Run git status --porcelain to get the names of the libraries that have changed
		# (cut -c4- removes the change-type-character from git status output)
		gitdiff_ouput = subprocess.check_output('git status --porcelain | cut -c4-', shell=True)
	except subprocess.CalledProcessError:
		print_e('FAIL: No artifacts to import from build ID %s' %  build_id)
		return None
	# Iterate through the git diff output to map libraries to their new versions
	artifact_ver_map = {}
	diff = iter(gitdiff_ouput.splitlines())
	for line in diff:
		file_path_list = line.decode().split('/')
		if len(file_path_list) < 3 or file_path_list[-1] != "":
			continue
		group_id = ".".join(file_path_list[:-3])
		artifact_id = file_path_list[-3]

		# For new libraries/group_ids, git status doesn't return the directory with the version
		# So, we need to go get it if it's not there
		if len(file_path_list) == 3:
			group_id = ".".join(file_path_list[:-1])
			# New library, so we need to check full directory tree to get version(s)
			if update_new_artifacts(line.decode(), artifact_ver_map, group_id, groups, artifacts, source):
				continue
		if len(file_path_list) == 4:
			group_id = ".".join(file_path_list[:-2])
			# New library, so we need to check full directory tree to get version(s)
			if update_new_artifacts(line.decode(), artifact_ver_map, group_id, groups, artifacts, source):
				continue
		version = file_path_list[-2]
		update_version_maps(artifact_ver_map, group_id, artifact_id, version, groups, artifacts, source)
	return artifact_ver_map


def should_update_docs(new_maven_coordinates):
	"""Users heuristics to determine if new_maven_coordinates should have public docs

	If no keyword is found, we ask the user.  These are
	heuristic keywords that cover common artifacts that
	contain no user-facing code or for exoplayer, is a
	jar-jar'd artifact.

	Args:
		new_maven_coordinates: the coordinate to check for

	Returns:
		True for public docs, false for no public docs
	"""
	keywords_to_ignore = [
		"extended",
		"android-stubs",
		"manifest",
		"compiler",
		"safe-args",
		"processor",
		"exoplayer",
		"gradle",
		"debug",
	]
	for keyword in keywords_to_ignore:
		if keyword in new_maven_coordinates:
			return False
	return ask_yes_or_no(
		"Should public docs be updated for new artifact %s?" % new_maven_coordinates)


# Inserts new groupdId into docs-public/build.gradle
def insert_new_artifact_into_dpbg(dpbg_lines, num_lines, new_maven_coordinates, artifact_ver_map):
	if not should_update_docs(new_maven_coordinates):
		return
	new_group_id_insert_line = 0
	for i in range(num_lines):
		cur_line = dpbg_lines[i]
		# Skip any line that doesn't declare a version
		if 'androidx.' not in cur_line: continue
		group_id, artifact_id, outdated_ver = get_maven_coordinate_from_docs_public_build_gradle_line(cur_line)
		# Iterate through until you found the alphabetical place to insert the new artifact
		if new_maven_coordinates <= group_id + ":" + artifact_id:
			new_maven_coordinate_insert_line = i
			break
		else:
			new_maven_coordinate_insert_line = i + 1
	if "sample" in new_maven_coordinates:
		build_gradle_line_prefix = "samples"
	else:
		build_gradle_line_prefix = "docs"
	# Failed to find a spot for the new groupID, so append it to the end of the LibraryGroup list
	dpbg_lines.insert(new_maven_coordinate_insert_line,
					  "    " + build_gradle_line_prefix + "(\"" + \
					  new_maven_coordinates + ":" + \
					  artifact_ver_map[new_maven_coordinates] + "\")\n")
	summary_log.append("docs-public/build.gradle: ADDED %s with version %s" % \
					   (new_maven_coordinates, artifact_ver_map[new_maven_coordinates]))
	publish_docs_log.append(new_maven_coordinates + ':' + artifact_ver_map[new_maven_coordinates])

def convert_prerelease_type_to_num(prerelease_type):
	# Convert a prerelease suffix type to its numeric equivalent
	if prerelease_type == 'alpha':
		return 0
	if prerelease_type == 'beta':
		return 1
	if prerelease_type == 'rc':
		return 2
	# Stable defaults to 9
	return 9

def parse_version(version):
	# Accepts a SemVer androidx version string, such as "1.2.0-alpha02" and 
	# returns a list of integers representing the version in the following format: 
	# [<major>,<minor>,<bugfix>,<prerelease-suffix>,<prerelease-suffix-revision>]
	# For example 1.2.0-alpha02" returns [1,2,0,0,2]
	version_elements = version.split('-')[0].split('.')
	version_list = []
	for element in version_elements:
		version_list.append(int(element))
	# Check if version contains prerelease suffix
	version_prerelease_suffix = version.split('-')[-1]
	# Account for suffixes with only 1 suffix number, i.e. "1.1.0-alphaX"
	version_prerelease_suffix_rev = version_prerelease_suffix[-2:]
	version_prerelease_suffix_type = version_prerelease_suffix[:-2]
	if not version_prerelease_suffix_rev.isnumeric():
		version_prerelease_suffix_rev = version_prerelease_suffix[-1:]
		version_prerelease_suffix_type = version_prerelease_suffix[:-1]
	version_list.append(convert_prerelease_type_to_num(version_prerelease_suffix_type))
	if version.find("-") == -1:
		# Version contains no prerelease suffix
		version_list.append(99)
	else:
		version_list.append(int(version_prerelease_suffix_rev))
	return version_list

def get_higher_version(version_a, version_b):
	version_a_list = parse_version(version_a)
	version_b_list = parse_version(version_b)
	for i in range(len(version_a_list)):
		if version_a_list[i] > version_b_list[i]:
			return version_a
		if version_a_list[i] < version_b_list[i]:
			return version_b
	return version_a

def find_invalidly_formatted_artifact(artifacts):
	"""Validates that the artifacts are correctly written.

	Artifacts need to be written as "<group_id>:<artifact_id>"
	Valid: "androidx.core:core"
	Valid: "androidx.foo.bar:bar"
	Invalid: "foo"
	Invalid: "foo:foo-bar"

	Args:
		artifacts: the list of artifacts to validate.

	Returns:
		artifactId that fails or None
	"""
	for artifact in artifacts:
		if not artifact.startswith("androidx."):
			return artifact
		if artifact.count(":") != 1:
			return artifact
		coordinates = artifact.split(":")
		for piece in coordinates:
			if not piece.replace("androidx.", ""):
				return artifact
	return None


def get_maven_coordinate_from_docs_public_build_gradle_line(line):
	""" Gets the maven coordinate tuple from docs-public/build.grade

	Example input: `    prebuilt("androidx.core:core:1.5.0-alpha04")`
	Example ouput: ("androidx.core", "core", "1.5.0-alpha05")

	Args:
		line: the line in docs-public/build.grade to parse

	Returns:
		Tuple of (group_id, artifact_id, version)
	"""
	coordinates = line.split('"')[1].split(':')
	group_id = coordinates[0]
	artifact_id = coordinates[1]
	version = coordinates[2]
	return group_id, artifact_id, version


def generate_updated_docs_public_build_gradle(artifact_ver_map,
											  build_gradle_file):
	""" Creates an updated build_gradle_file lines.

	Iterates over the provided build_gradle_file and constructs
	the lines of an updated build.gradle with the new versions in the
	artifact version map.

	Does not write anything to disk.

	Args:
		artifact_ver_map: map of updated artifacts to their new versions.
		build_gradle_file: docs-public/build.gradle to read and update.

	Returns:
		lines up for updated file to be written to disk.
	"""
	artifact_found = {}
	for key in artifact_ver_map:
		artifact_found[key] = False
	# Open file for reading and get all lines
	with open(build_gradle_file, 'r') as f:
		dpbg_lines = f.readlines()
	num_lines = len(dpbg_lines)
	for i in range(num_lines):
		cur_line = dpbg_lines[i]
		# Skip any line that doesn't declare a version
		if 'androidx.' not in cur_line: continue
		group_id, artifact_id, outdated_ver = get_maven_coordinate_from_docs_public_build_gradle_line(cur_line)
		ver_index = cur_line.find(outdated_ver)
		artifact_coordinate = group_id + ":" + artifact_id
		### Update group_id or artifact_id ###
		if artifact_coordinate in artifact_ver_map:
			artifact_found[artifact_coordinate] = True
			# Skip version updates that would decrement to a smaller version
			if outdated_ver == get_higher_version(outdated_ver, artifact_ver_map[artifact_coordinate]): continue
			# Update version of artifact_id
			if artifact_ver_map[artifact_coordinate] != outdated_ver:
				dpbg_lines[i] = cur_line[:ver_index] \
					+ artifact_ver_map[artifact_coordinate] \
					+ cur_line[ver_index+len(outdated_ver):]
				summary_log.append("docs-public/build.gradle: " + \
								   "Updated %s from %s to %s" % \
								   (artifact_coordinate, outdated_ver, artifact_ver_map[artifact_coordinate]))
				publish_docs_log.append(artifact_coordinate + ":" + artifact_ver_map[artifact_coordinate])
	for artifact in artifact_found:
		if not artifact_found[artifact]:
			insert_new_artifact_into_dpbg(dpbg_lines, num_lines, artifact, artifact_ver_map)
	return dpbg_lines


def update_docs_public_build_gradle(artifact_ver_map, build_gradle_file=DOCS_PUBLIC_BUILD_GRADLE_FP):
	# Get build the file path of PublicDocRules.kt - this isn't great, open to a better solution
	if not os.path.exists(build_gradle_file):
		print_e("docs-public build.gradle not in expected location. Looked at: %s" % build_gradle_file)
		return None
	dpbg_lines = generate_updated_docs_public_build_gradle(artifact_ver_map, build_gradle_file)
	# Open file for writing and update all lines
	with open(build_gradle_file, 'w') as f:
		f.writelines(dpbg_lines)
	return True

def update_androidx(target, build_id, local_file, groups, artifacts, skip_public_docs):
	repo_dir = None
	try:
		if build_id:
			artifact_zip_file = 'top-of-tree-m2repository-all-%s.zip' % build_id
			repo_dir = fetch_and_extract("androidx", build_id, artifact_zip_file, None)
		else:
			repo_dir = fetch_and_extract("androidx", None, None, local_file)
		if not repo_dir:
			print_e('Failed to extract AndroidX repository')
			return False
		print("Download and extract artifacts... Successful")
		if not copy_and_merge_artifacts(repo_dir, './androidx', groups, artifacts):
			print_e('Failed to copy and merge AndroidX repository')
			return False
		print("Copy and merge artifacts... Successful")
		remove_type_aar_from_pom_files("androidx")
		remove_maven_metadata_files("androidx")
		# Now that we've merged new prebuilts, we need to update our version map
		source = "ab/%s" % build_id if build_id else local_file
		artifact_ver_map = get_updated_version_map(groups, artifacts, source)
		if not skip_public_docs:
			if not update_docs_public_build_gradle(artifact_ver_map):
				print_e('Failed to update PublicDocRules.kt')
				return False
			print("Update docs-public/build.gradle... Successful")
		return True
	finally:
		# Remove temp directories and temp files we've created
		if repo_dir is not None:
			rm(repo_dir)
			rm('%s.zip' % repo_dir)
		rm('.fetch_artifact2.dat')

def print_change_summary():
	print("\n ---  SUMMARY --- ")
	for change in summary_log:
		print(change)

# Check if build ID exists and is a number
def get_build_id(source):
	if not source: return None
	if not source.isnumeric():
		return None
	return source

# Check if file exists and is not a number
def get_file(source):
	if not source: return None
	if not source.isnumeric():
		return source
	return None

def commit_prebuilts(args):
	subprocess.check_call(['git', 'add', './androidx'])
	# ensure that we've actually made a change:
	staged_changes = subprocess.check_output('git diff --cached', stderr=subprocess.STDOUT, shell=True)
	if not staged_changes:
		print_e("There are no prebuilts changes to commit!  Check build id.")
		return False
	msg = ("Import prebuilts for:\n\n- %s\n\n"
		   "This commit was generated from the command:"
		   "\n%s\n\n%s" % ("\n- ".join(prebuilts_log), " ".join(sys.argv), 'Test: ./gradlew buildOnServer'))
	subprocess.check_call(['git', 'commit', '-m', msg])
	summary_log.append("1 Commit was made in prebuilts/androidx/internal to commit prebuilts")
	print("Create commit for prebuilts... Successful")
	return True

def commit_docs_public_build_gradle():
	git_add_cmd =  "git %s add %s"  % (GIT_TREE_ARGS, DOCS_PUBLIC_BUILD_GRADLE_REL)
	subprocess.check_call(git_add_cmd, stderr=subprocess.STDOUT, shell=True)
	git_cached_cmd = "git %s diff --cached" % GIT_TREE_ARGS
	staged_changes = subprocess.check_output(git_cached_cmd, stderr=subprocess.STDOUT, shell=True)
	if not staged_changes:
		summary_log.append("NO CHANGES were made to docs-public/build.gradle")
		return False
	pdr_msg = ("Updated docs-public/build.gradle for the following artifacts:" + \
			   "\n\n- %s \n\nThis commit was generated from the command:"
			   "\n%s\n\n%s" % ("\n- ".join(publish_docs_log), " ".join(sys.argv), 'Test: ./gradlew buildOnServer'))
	git_commit_cmd = "git %s commit -m \"%s\"" % (GIT_TREE_ARGS, pdr_msg)
	subprocess.check_call(git_commit_cmd, stderr=subprocess.STDOUT, shell=True)
	summary_log.append("1 Commit was made in frameworks/support to commmit changes to docs-public/build.gradle")
	print("Create commit for docs-public/build.gradle... Successful")


def parse_long_form(long_form, source_to_artifact):
	"""Parses the long form syntax into a list of source(buildIds) to artifacts

	This method takes a string long_form of the syntax:
	`<build id 1>/<group id>,<build id 2>/<group id>:<artifact id>`

	It reads throught the string and parses the correct builds and artifacts/groups
	into a map of build ID to groups and artifacts.

	Args:
		long_form: string to parse into a map of source to groups/artifacts
		source_to_artifact: map of type defaultdict(lambda: defaultdict(list))

	Returns:
		source_to_artifact on success, None on failure
	"""
	if '/' not in long_form:
		print_e("The long form syntax requires slashs to separate the build Id or source.")
		return None
	if '.' not in long_form:
		print_e("The long form syntax needs to include the full groupId/artifactId.")
		return None
	if 'androidx' not in long_form:
		print_e("The long form syntax needs to contain androidx.")
		return None

	import_items = long_form.split(',')

	for item in import_items:
		if item.count('/') != 1:
			print_e("The long form syntax requires the format "
					"<build Id>/<group Id> or <build Id>/<group Id>:<artifact Id>.")
			return None
		source = item.split('/')[0]
		if not source:
			print_e("The long form syntax requires a build Id or source to be "
					"specified for every artifact.")
			return None
		artifact = item.split('/')[1]
		if ':' in artifact:
			source_to_artifact[source]['artifacts'].append(artifact)
		else:
			source_to_artifact[source]['groups'].append(artifact)
	return source_to_artifact

# Set up input arguments
parser = argparse.ArgumentParser(
	description=("""Import AndroidX prebuilts from the Android Build Server
		and if necessary, update docs-public/build.gradle.  By default, uses
		top-of-tree-m2repository-all-<BUILDID>.zip to get artifacts."""))
parser.add_argument(
	'--source',
	help='Build server build ID or local Maven ZIP file')
parser.add_argument(
	'--all-prebuilts', action="store_true",
	help='If specified, updates all AndroidX prebuilts with artifacts from the build ID')
parser.add_argument(
	'--skip-public-docs', action="store_true",
	help='If specified, docs-public/build.gradle will NOT be updated')
parser.add_argument(
	'--groups', metavar='group_id', nargs='+',
	help="""If specified, only update libraries whose group_id contains the listed text.
	For example, if you specify \"--groups paging slice lifecycle\", then this
	script will import each library with group_id beginning with \"androidx.paging\", \"androidx.slice\",
	or \"androidx.lifecycle\"""")
parser.add_argument(
	'--artifacts', metavar='artifact_id', nargs='+',
	help="""If specified, only update libraries whose artifact_id contains the listed text.
	For example, if you specify \"--artifacts androidx.core:core androidx.core:slice-view
	androidx.lifecycle:lifecycle-common\", then this script will import specific artifacts
	\"androidx.core:core\", \"androidx.slice:slice-view\", and
	\"androidx.lifecycle:lifecycle-common\"""")
parser.add_argument(
	'--no-commit', action="store_true",
	help='If specified, this script will not commit the changes')
parser.add_argument(
	'--long-form',
	help=('If specified, the following argument must be a comma separated listed '
		  'of all groups and artifact.  Groups are specified as '
		  '`<build id>/<group id>` and artifacts are specified as '
		  '`<build id>/<group id>:<artifact id>`.  The full format is: '
		  '`<build id 1>/<group id>,,'
		  '<build id 2>/<group id>:<artifact id>,...`'
		 ))


def main(args):
	# Parse arguments and check for existence of build ID or file
	args = parser.parse_args()
	source_to_artifact = defaultdict(lambda: defaultdict(list))

	if args.long_form:
		if not parse_long_form(args.long_form, source_to_artifact):
			exit(1)
	else:
		if not args.source:
			parser.error("You must specify a build ID or local Maven ZIP file")
			sys.exit(1)
		# Force the user to explicity decide which set of prebuilts to import
		if args.all_prebuilts == False and args.groups == None and args.artifacts == None:
			print_e("Need to pass an argument such as --all-prebuilts or pass in group_ids or artifact_ids")
			print_e("Run `./import_release_prebuilts.py --help` for more info")
			sys.exit(1)
		source_to_artifact[args.source]['groups'] = args.groups
		source_to_artifact[args.source]['artifacts'] = args.artifacts

	for source in source_to_artifact:
		if source_to_artifact[source].get('artifacts'):
			invalid_artifact = find_invalidly_formatted_artifact(
				source_to_artifact[source].get('artifacts'))
			if invalid_artifact:
				print_e("The following artifact_id is malformed: ", invalid_artifact)
				print_e("Please format artifacts as <group_id>:<artifact_id>, such "
						"as: `androidx.foo.bar:bar`")
				sys.exit(1)

		if not update_androidx('androidx',
							   get_build_id(source),
							   get_file(source),
							   source_to_artifact[source].get('groups'),
							   source_to_artifact[source].get('artifacts'),
							   args.skip_public_docs):
			print_e('Failed to update AndroidX, aborting...')
			sys.exit(1)

	if args.no_commit:
		summary_log.append("These changes were NOT committed.")
	else:
		if not commit_prebuilts(args): sys.exit(1)
		commit_docs_public_build_gradle()

	print_change_summary()
	print("Test and check these changes before uploading to Gerrit")

if __name__ == '__main__':
    main(sys.argv)
