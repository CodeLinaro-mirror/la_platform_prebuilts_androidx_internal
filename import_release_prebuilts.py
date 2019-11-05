#!/usr/bin/python3

import os, sys, zipfile
import argparse
import subprocess
from shutil import rmtree
from distutils.dir_util import copy_tree

# cd into directory of script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# See go/fetch_artifact for details on this script.
FETCH_ARTIFACT = '/google/data/ro/projects/android/fetch_artifact'
PUBLISHDOCSRULES_REL = './buildSrc/src/main/kotlin/androidx/build/PublishDocsRules.kt'
FRAMEWORKS_SUPPORT_FP = os.path.abspath(os.path.join(os.getcwd(), '..', '..', '..', 'frameworks', 'support'))
PUBLISHDOCSRULES_FP = os.path.join(FRAMEWORKS_SUPPORT_FP, PUBLISHDOCSRULES_REL)
GIT_TREE_ARGS = '--git-dir=./../../../frameworks/support/.git/ --work-tree=./../../../frameworks/support/'
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
		subprocess.check_output(fetch_cmd, stderr=subprocess.STDOUT)
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

def get_groupId_from_artifactId(artifactId):
	# By convention, androidx namespace is declared as:
	# androidx.${groupId}:${groupId}-${optionalArtifactIdSuffix}:${version}
	# Here, artifactId == "${groupId}-${optionalArtifactIdSuffix}"
	return artifactId.split('-')[0]

def copy_and_merge_artifacts(repo_dir, dest_dir, groupIds, artifactIds):
	repo_androidx_path = get_repo_androidx_path(repo_dir)
	if not repo_androidx_path: return None
	if not groupIds and not artifactIds:
		return cp(repo_androidx_path, dest_dir)
	if groupIds:
		# Copy over groupIds that were specified on the command line
		for group in groupIds:
			repo_group_path = os.path.join(repo_androidx_path, group)
			if not os.path.exists(repo_group_path):
				print_e("Failed to find groupId %s in the artifact zip file" % group)
				return None
			dest_group_path = os.path.join(dest_dir, group)
			if not cp(repo_group_path, dest_group_path):
				print_e("Failed to find copy %s to %s" % (repo_group_path, dest_group_path))
				return None
	if artifactIds:
		# Copy over artifactIds that were specified on the command line
		for artifact in artifactIds:
			# Get the groupId from the artifactId (in AndroidX, the groupId must be based on the artifactId)
			artifact_groupId = get_groupId_from_artifactId(artifact)
			repo_artifact_path = os.path.join(repo_androidx_path, artifact_groupId, artifact)
			if not os.path.exists(repo_artifact_path):
				print_e("Failed to find artifactId %s in the artifact zip file" % artifact)
				return None
			dest_artifact_path = os.path.join(dest_dir, artifact_groupId, artifact)
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
		subprocess.check_output("find " + repo_dir + " -name *.pom | xargs sed 's|^      <type>aar</type>$|      <!--<type>aar</type>-->|' -i", shell=True)
	except subprocess.CalledProcessError:
		print("failed!")
		print_e("FAIL: Failed to remove <type>aar</type> from the pom files")
		summary_log.append("FAILED to remove <type>aar</type> from the pom files")
		return False
	print("Successful")
	summary_log.append("<type>aar</type> was removed from the pom files")
	return True

def update_new_artifacts(group_id_file_path, groupId_ver_map, artifactId_ver_map, groupId):
	# Finds each new library having groupId <groupId> under <group_id_file_path> and
	# updates <groupId_ver_map> and <artifactId_ver_map> with this new library
	success = False
	# Walk filepath to get versions for each artifactId
	for parent_file_path, dirs, _ in os.walk(group_id_file_path):
		for dir_name in dirs:
			if dir_name[0].isnumeric():
				# Version directories have format version as dir_name, for example: 1.1.0-alpha06
				version = dir_name
				# Get artifactId from filepath
				artifactId = parent_file_path.strip('/').split('/')[-1]
				update_version_maps(groupId_ver_map, artifactId_ver_map, groupId, artifactId, version)
				success = True
	if not success:
		print_e("Failed to find any artifactIds in filepath: %s" % group_id_file_path)
	return success

def should_update_artifact(groupId, artifactId):
	# If a artifact or group list was specified and if the artifactId or groupId were NOT specified 
	# in either list on the command line, return false
	should_update = False
	if (args.groups) or (args.artifacts):
		if args.groups:
			if groupId.replace("androidx.", "") in args.groups:
				should_update = True
			if groupId in args.groups:
				should_update = True
		if (args.artifacts) and (artifactId in args.artifacts):
			should_update = True
	else:
		should_update = True
	return should_update

def update_version_maps(groupId_ver_map, artifactId_ver_map, groupId, artifactId, version):
	if should_update_artifact(groupId, artifactId):
		if groupId not in groupId_ver_map:
			groupId_ver_map[groupId] = version
		if artifactId not in artifactId_ver_map:
			artifactId_ver_map[artifactId] = version
			summary_log.append("Prebuilts: %s --> %s" % (artifactId, version))
			prebuilts_log.append(artifactId+'-'+version)

def get_updated_version_maps():
	try:
		# Run git status --porcelain to get the names of the libraries that have changed
		# (cut -c4- removes the change-type-character from git status output)
		gitdiff_ouput = subprocess.check_output('git status --porcelain | cut -c4-', shell=True)
	except subprocess.CalledProcessError:
		print_e('FAIL: No artifacts to import from build ID %s' %  build_id)
		return None
	# Iterate through the git diff output to map libraries to their new versions
	artifactId_ver_map = {}
	groupId_ver_map = {}
	diff = iter(gitdiff_ouput.splitlines())
	for line in diff:
		file_path_list = line.decode().split('/')
		if len(file_path_list) < 3 or file_path_list[-1] != "":
			continue
		groupId = ".".join(file_path_list[:-3])
		artifactId = file_path_list[-3]

		# For new libraries/groupIds, git status doesn't return the directory with the version
		# So, we need to go get it if it's not there
		if len(file_path_list) == 3:
			groupId = ".".join(file_path_list[:-1])
			# New library, so we need to check full directory tree to get version(s)
			if not update_new_artifacts(line.decode(), groupId_ver_map, artifactId_ver_map, groupId):
				continue
		if len(file_path_list) == 4:
			groupId = ".".join(file_path_list[:-2])
			# New library, so we need to check full directory tree to get version(s)
			if not update_new_artifacts(line.decode(), groupId_ver_map, artifactId_ver_map, groupId):
				continue
		version = file_path_list[-2]
		update_version_maps(groupId_ver_map, artifactId_ver_map, groupId, artifactId, version)
	return groupId_ver_map, artifactId_ver_map

# Inserts new groupdId into PublishDocsRules.kt
def insert_new_groupId_into_pdr(pdr_lines, num_lines, new_groupId, groupId_ver_map):
	new_groupId_insert_line = 0
	new_groupId_variable_name = new_groupId.replace("androidx.","").replace(".","_").upper()
	for i in range(num_lines):
		cur_line = pdr_lines[i]
		# Skip any line that doesn't declare a version
		if 'LibraryGroups' not in cur_line: continue
		groupId_variable_name = cur_line.split('LibraryGroups.')[1].split(',')[0]
		# Skip any line that does contain a version
		cur_line_split = cur_line.split('\"')
		if len(cur_line_split) < 2: continue
		# Iterate through until you found the alphabetical place to insert the new groupId
		if new_groupId_variable_name <= groupId_variable_name:
			new_groupId_insert_line = i
			break
		else:
			new_groupId_insert_line = i + 1
	# Failed to find a spot for the new groupID, so append it to the end of the LibraryGroup list
	pdr_lines.insert(new_groupId_insert_line, "    prebuilts(LibraryGroups." \
				+ new_groupId_variable_name + ", \"" \
				+ groupId_ver_map[new_groupId] + "\")\n")
	summary_log.append("PublishDocsRules.kt: ADDED %s with version %s" %(new_groupId, groupId_ver_map[new_groupId]))
	publish_docs_log.append(new_groupId.lower()+'-'+groupId_ver_map[new_groupId])

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

def update_publish_doc_rules(groupId_ver_map, artifactId_ver_map):
	groupId_found = {}
	for key in groupId_ver_map:
		groupId_found[key] = False
	# Get build the file path of PublicDocRules.kt - this isn't great, open to a better solution
	if not os.path.exists(PUBLISHDOCSRULES_FP):
		print_e("PublishDocsRules.kt not in expected location.")
		return None
	# Open file for reading and get all lines
	with open(PUBLISHDOCSRULES_FP, 'r') as f:
		pdr_lines = f.readlines()
	num_lines = len(pdr_lines)
	for i in range(num_lines):
		cur_line = pdr_lines[i]
		# Skip any line that doesn't declare a version
		if 'LibraryGroups' not in cur_line: continue
		groupId_variable_name = cur_line.split('LibraryGroups.')[1].split(',')[0]
		groupId = "androidx." + groupId_variable_name.replace(".group", "").replace("_", ".").lower()
		# Get the artifactId (if it exists)
		cur_line_split = cur_line.split('\"')
		# Skip any line that does contain a version
		if len(cur_line_split) < 2: continue
		artifactId = ""
		if len(cur_line_split) >= 4:
			artifactId = cur_line_split[-4]
		# Split lines based on quotes and get second to last string - this will be the version
		outdated_ver = cur_line.split('\"')[-2]
		ver_index = cur_line.find(outdated_ver)
		# Skip any line that does contain a version
		if not outdated_ver[0].isnumeric():	continue
		### Update groupId or artifactId ###
		if artifactId in artifactId_ver_map:
			groupId_found[groupId] = True
			# Skip version updates that would decrement to a smaller version
			if outdated_ver == get_higher_version(outdated_ver, artifactId_ver_map[artifactId]): continue
			# Update version of artifactId
			if artifactId_ver_map[artifactId] != outdated_ver:
				pdr_lines[i] = cur_line[:ver_index] \
					+ artifactId_ver_map[artifactId] \
					+ cur_line[ver_index+len(outdated_ver):]
				summary_log.append("PublishDocsRules.kt: Updated %s from %s to %s" %(artifactId, outdated_ver, artifactId_ver_map[artifactId]))
				publish_docs_log.append(artifactId+'-'+artifactId_ver_map[artifactId])
		if not artifactId and groupId in groupId_ver_map:
			groupId_found[groupId] = True
			# Skip version updates that would decrement to a smaller version
			if outdated_ver == get_higher_version(outdated_ver, groupId_ver_map[groupId]): continue
			# Update version of groupId
			if groupId_ver_map[groupId] != outdated_ver:
				pdr_lines[i] = cur_line[:ver_index] \
					+ groupId_ver_map[groupId] \
					+ cur_line[ver_index+len(outdated_ver):]
				summary_log.append("PublishDocsRules.kt: Updated %s from %s to %s" %(groupId.lower(), outdated_ver, groupId_ver_map[groupId]))
				publish_docs_log.append(groupId.lower()+'-'+groupId_ver_map[groupId])
	for groupId in groupId_found:
		if not groupId_found[groupId]:
			insert_new_groupId_into_pdr(pdr_lines, num_lines, groupId, groupId_ver_map)
	# Open file for writing and update all lines
	with open(PUBLISHDOCSRULES_FP, 'w') as f:
		f.writelines(pdr_lines)
	return True

def update_androidx(target, build_id, local_file, update_all_prebuilts, import_compose):
	try:
		if build_id:
			if update_all_prebuilts:
				artifact_zip_file = ('ui/top-of-tree-m2repository-all-%s.zip' % build_id if import_compose
					else 'top-of-tree-m2repository-all-%s.zip' % build_id)
			else:
				artifact_zip_file = ('ui/gmaven-diff-all-%s.zip' % build_id if import_compose
					else 'gmaven-diff-all-%s.zip' % build_id)
			repo_dir = fetch_and_extract("androidx", build_id, artifact_zip_file, None)
		else:
			repo_dir = fetch_and_extract("androidx", None, None, local_file)
		if not repo_dir:
			print_e('Failed to extract AndroidX repository')
			return False
		print("Download and extract artifacts... Successful")
		if not copy_and_merge_artifacts(repo_dir, './androidx', args.groups, args.artifacts):
			print_e('Failed to copy and merge AndroidX repository')
			return False
		print("Copy and merge artifacts... Successful")
		remove_type_aar_from_pom_files("androidx")
		# Now that we've merged new prebuilts, we need to update our version map
		groupId_ver_map, artifactId_ver_map = get_updated_version_maps()
		if not args.skip_publishdocrules:
			if not update_publish_doc_rules(groupId_ver_map, artifactId_ver_map):
				print_e('Failed to update PublicDocRules.kt')
				return False
			print("Update PublishDocsRules.kt... Successful")
		return True
	finally:
		# Remove temp directories and temp files we've created 
		rm(repo_dir)
		rm('%s.zip' % repo_dir)
		if import_compose: rm('ui')
		rm('.fetch_artifact2.dat')

def print_change_summary():
	print("\n ---  SUMMARY --- ")
	for change in summary_log:
		print(change)

# Check if build ID exists and is a number
def get_build_id(args):
	source = args.source
	number_text = source[:]
	if not number_text.isnumeric():
		return None
	args.file = False
	return source

# Check if file exists and is not a number
def get_file(args):
	source = args.source
	if not source.isnumeric():
		return args.source
	return None

# Check that the --compose argument was passed correctly
# For example:
# 	Fails: ./import_release_prebuilts.py <BUILDID> --groups compose
#	Fails: ./import_release_prebuilts.py <BUILDID> --groups compose navigation --compose
#	Fails: ./import_release_prebuilts.py <BUILDID> --groups navigation --compose
#	Succeeds: ./import_release_prebuilts.py <BUILDID> --groups compose --compose
def used_compose_flag_correctly():
	if args.groups:
		for group in args.groups:
			if (group not in ["ui", "compose"]) and (args.compose):
				print_e("Compose artifacts need to be imported separately from other androidx " +
					"artifacts.  Please import the compose artifacts separately with the `--compose` " +
					"argument")
				return False
			if (group in ["ui", "compose"]) and (not args.compose):
				print_e("To import compose artifacts (like androidx.ui or androidx.compose), " +
					"you need to pass the `--compose` argument")
				return False
	if args.artifacts:
		for artifact in args.artifacts:
			if ("ui" not in artifact and "compose" not in artifact) and (args.compose):
				print_e("Compose artifacts need to be imported separately from other androidx " +
					"artifacts.  Please import the compose artifacts separately with the `--compose` " +
					"argument")
				return False
			if ("ui" in artifact or "compose" in artifact) and (not args.compose):
				print_e("To import compose artifacts (like androidx.ui or androidx.compose), " +
					"you need to pass the `--compose` argument")
				return False
	return True

def commit_prebuilts():
	subprocess.check_call(['git', 'add', './androidx'])
	# ensure that we've actually made a change:
	staged_changes = subprocess.check_output('git diff --cached', stderr=subprocess.STDOUT, shell=True)
	if not staged_changes:
		print_e("There are no prebuilts changes to commit!  Check build id.")
		return False
	if not args.source.isnumeric():
		src_msg = "local Maven ZIP %s" % get_file(args)
	else:
		src_msg = "build %s" % (get_build_id(args))
	msg = "Import prebuilts %s from %s\n\nThis commit was generated from the command:\n%s\n\n%s" % (", ".join(prebuilts_log), src_msg, " ".join(sys.argv), 'Test: ./gradlew buildOnServer')
	subprocess.check_call(['git', 'commit', '-m', msg])
	summary_log.append("1 Commit was made in prebuilts/androidx/internal to commit prebuilts")
	print("Create commit for prebuilts... Successful")
	return True

def commit_publish_docs_rules():
	git_add_cmd =  "git %s add %s"  % (GIT_TREE_ARGS, PUBLISHDOCSRULES_REL)
	subprocess.check_output(git_add_cmd, stderr=subprocess.STDOUT, shell=True)
	git_cached_cmd = "git %s diff --cached" % GIT_TREE_ARGS
	staged_changes = subprocess.check_output(git_cached_cmd, stderr=subprocess.STDOUT, shell=True)
	if not staged_changes:
		summary_log.append("NO CHANGES were made to PublishDocsRules.kt")
		return False
	pdr_msg = "Updated PublishDocsRules.kt for %s \n\nThis commit was generated from the command:\n%s\n\n%s" % (", ".join(publish_docs_log), " ".join(sys.argv), 'Test: ./gradlew buildOnServer')
	git_commit_cmd = "git %s commit -m \"%s\"" % (GIT_TREE_ARGS, pdr_msg)
	subprocess.check_output(git_commit_cmd, stderr=subprocess.STDOUT, shell=True)
	summary_log.append("1 Commit was made in frameworks/support to commmit changes to PublishDocsRules.kt")
	print("Create commit for PublishDocsRules.kt... Successful")


# Set up input arguments
parser = argparse.ArgumentParser(
	description=('Import AndroidX prebuilts from the Android Build Server and if necessary, update PublishDocsRules.kt.  By default, uses gmaven-diff-all-<BUILDID>.zip to get artifacts.'))
parser.add_argument(
	'source',
	help='Build server build ID or local Maven ZIP file')
parser.add_argument(
	'--all-prebuilts', action="store_true",
	help='If specified, updates all AndroidX prebuilts with artifacts from the build ID')
parser.add_argument(
	'--skip-publishdocrules', action="store_true",
	help='If specified, PublishDocsRules.kt will NOT be updated')
parser.add_argument(
	'--groups', metavar='groupId', nargs='+',
	help="""If specified, only update libraries whose groupId contains the listed text.
	For example, if you specify \"--groups paging slice lifecycle\", then this
	script will import each library with groupId beginning with \"androidx.paging\", \"androidx.slice\",
	or \"androidx.lifecycle\"""")
parser.add_argument(
	'--artifacts', metavar='artifactId', nargs='+',
	help="""If specified, only update libraries whose artifactId contains the listed text.
	For example, if you specify \"--artifacts core slice-view lifecycle-common\", then this
	script will import specific artifacts \"androidx.core:core\", \"androidx.slice:slice-view\",
	and \"androidx.lifecycle:lifecycle-common\"""")
parser.add_argument(
	'--no-commit', action="store_true",
	help='If specified, this script will not commit the changes')
parser.add_argument(
	'--compose', action="store_true",
	help='If specified, this script will look for compose artifacts under the ui/ directory')

# Parse arguments and check for existence of build ID or file
args = parser.parse_args()
args.file = True
if not args.source:
	parser.error("You must specify a build ID or local Maven ZIP file")
	sys.exit(1)

# Check that user is only trying to get compose with the compose argument
if not used_compose_flag_correctly():
	sys.exit(1)

# Force the user to explicity decide which set of prebuilts to import
if args.all_prebuilts == False and args.groups == None and args.artifacts == None:
	print_e("Need to pass an argument such as --all-prebuilts or pass in groupIds or artifactIds")
	print_e("Run `./import_release_prebuilts.py --help` for more info")
	sys.exit(1)

if not update_androidx('androidx', get_build_id(args), get_file(args), args.all_prebuilts, args.compose):
	print_e('Failed to update AndroidX, aborting...')
	sys.exit(1)

if args.no_commit:
	summary_log.append("These changes were NOT committed.")
else:
	if not commit_prebuilts(): sys.exit(1)
	commit_publish_docs_rules()

print_change_summary()
print("Test and check these changes before uploading to Gerrit")