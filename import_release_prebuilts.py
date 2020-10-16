#!/usr/bin/python3

import os, sys, zipfile
import argparse
import subprocess
from shutil import rmtree
from distutils.dir_util import copy_tree
import glob

# cd into directory of script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# See go/fetch_artifact for details on this script.
FETCH_ARTIFACT = '/google/data/ro/projects/android/fetch_artifact'
PUBLISHDOCSRULES_REL = './buildSrc/src/main/kotlin/androidx/build/PublishDocsRules.kt'
FRAMEWORKS_SUPPORT_FP = os.path.abspath(os.path.join(os.getcwd(), '..', '..', '..', 'frameworks', 'support'))
PUBLISHDOCSRULES_FP = os.path.join(FRAMEWORKS_SUPPORT_FP, PUBLISHDOCSRULES_REL)
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

def get_group_id_sub_path(group_id):
	""" Gets the group_id filepath within the m2repository repo.

	Assumes that androidx is supplied by get_repo_androidx_path()

	Example: "androidx.compose.animation" returns "compose/animation"

	Args: group_id
	Returns: the group_id subpath
	"""
	return group_id.replace("androidx.", "").replace(".", "/")

def get_group_id_from_artifact_id(artifact_id):
	# By convention, androidx namespace is declared as:
	# androidx.${group_id}:${group_id}-${optionalArtifactIdSuffix}:${version}
	# Here, artifact_id == "${group_id}-${optionalArtifactIdSuffix}"
	return artifact_id.split('-')[0]

def copy_and_merge_artifacts(repo_dir, dest_dir, group_ids, artifact_ids):
	repo_androidx_path = get_repo_androidx_path(repo_dir)
	if not repo_androidx_path: return None
	if not group_ids and not artifact_ids:
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
	if artifact_ids:
		# Copy over artifact_ids that were specified on the command line
		for artifact in artifact_ids:
			# Get the group_id from the artifact_id (in AndroidX, the group_id must be based on the artifact_id)
			artifact_group_id = get_group_id_from_artifact_id(artifact)
			repo_artifact_path = os.path.join(repo_androidx_path, artifact_group_id, artifact)
			if not os.path.exists(repo_artifact_path):
				print_e("Failed to find artifact_id %s in the artifact zip file" % artifact)
				return None
			dest_artifact_path = os.path.join(dest_dir, artifact_group_id, artifact)
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

def remove_maven_metadata_files(repo_dir):
	# Only search for maven-metadata files to in <repo_dir>
	print("Removing maven-metadata.xml* files from the import...", end = '')
	for maven_metadata_file in glob.glob(repo_dir + "/**/maven-metadata.xml*", recursive=True):
		os.remove(maven_metadata_file)
	print("Successful")
	summary_log.append("Removed maven-metadata.xml* files from the import")
	return True

def update_new_artifacts(group_id_file_path, group_id_ver_map, artifact_id_ver_map, group_id):
	# Finds each new library having group_id <group_id> under <group_id_file_path> and
	#     updates <group_id_ver_map> and <artifact_id_ver_map> with this new library
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
				update_version_maps(group_id_ver_map, artifact_id_ver_map, real_group_id, artifact_id, version)
				success = True
	if not success:
		print_e("Failed to find any artifact_ids in filepath: %s" % group_id_file_path)
	return success

def should_update_artifact(group_id, artifact_id):
	# If a artifact or group list was specified and if the artifact_id or group_id were NOT specified
	# in either list on the command line, return false
	should_update = False
	if (args.groups) or (args.artifacts):
		if args.groups:
			if group_id.replace("androidx.", "") in args.groups:
				should_update = True
			if group_id in args.groups:
				should_update = True
		if (args.artifacts) and (artifact_id in args.artifacts):
			should_update = True
	else:
		should_update = True
	return should_update

def update_version_maps(group_id_ver_map, artifact_id_ver_map, group_id, artifact_id, version):
	if should_update_artifact(group_id, artifact_id):
		if group_id not in group_id_ver_map:
			group_id_ver_map[group_id] = version
		if artifact_id not in artifact_id_ver_map:
			artifact_id_ver_map[artifact_id] = version
			summary_log.append("Prebuilts: %s --> %s" % (artifact_id, version))
			prebuilts_log.append(artifact_id+'-'+version)

def get_updated_version_maps():
	try:
		# Run git status --porcelain to get the names of the libraries that have changed
		# (cut -c4- removes the change-type-character from git status output)
		gitdiff_ouput = subprocess.check_output('git status --porcelain | cut -c4-', shell=True)
	except subprocess.CalledProcessError:
		print_e('FAIL: No artifacts to import from build ID %s' %  build_id)
		return None
	# Iterate through the git diff output to map libraries to their new versions
	artifact_id_ver_map = {}
	group_id_ver_map = {}
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
			if update_new_artifacts(line.decode(), group_id_ver_map, artifact_id_ver_map, group_id):
				continue
		if len(file_path_list) == 4:
			group_id = ".".join(file_path_list[:-2])
			# New library, so we need to check full directory tree to get version(s)
			if update_new_artifacts(line.decode(), group_id_ver_map, artifact_id_ver_map, group_id):
				continue
		version = file_path_list[-2]
		update_version_maps(group_id_ver_map, artifact_id_ver_map, group_id, artifact_id, version)
	return group_id_ver_map, artifact_id_ver_map

# Inserts new groupdId into PublishDocsRules.kt
def insert_new_group_id_into_pdr(pdr_lines, num_lines, new_group_id, group_id_ver_map):
	new_group_id_insert_line = 0
	new_group_id_variable_name = new_group_id.replace("androidx.","").replace(".","_").upper()
	for i in range(num_lines):
		cur_line = pdr_lines[i]
		# Skip any line that doesn't declare a version
		if 'LibraryGroups' not in cur_line: continue
		group_id_variable_name = cur_line.split('LibraryGroups.')[1].split(',')[0]
		# Skip any line that does contain a version
		cur_line_split = cur_line.split('\"')
		if len(cur_line_split) < 2: continue
		# Iterate through until you found the alphabetical place to insert the new group_id
		if new_group_id_variable_name <= group_id_variable_name:
			new_group_id_insert_line = i
			break
		else:
			new_group_id_insert_line = i + 1
	# Failed to find a spot for the new groupID, so append it to the end of the LibraryGroup list
	pdr_lines.insert(new_group_id_insert_line, "    prebuilts(LibraryGroups." \
				+ new_group_id_variable_name + ", \"" \
				+ group_id_ver_map[new_group_id] + "\")\n")
	summary_log.append("PublishDocsRules.kt: ADDED %s with version %s" %(new_group_id, group_id_ver_map[new_group_id]))
	publish_docs_log.append(new_group_id.lower()+'-'+group_id_ver_map[new_group_id])

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

def update_publish_doc_rules(group_id_ver_map, artifact_id_ver_map):
	group_id_found = {}
	for key in group_id_ver_map:
		group_id_found[key] = False
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
		group_id_variable_name = cur_line.split('LibraryGroups.')[1].split(',')[0]
		group_id = "androidx." + group_id_variable_name.replace(".group", "").replace("_", ".").lower()
		# Get the artifact_id (if it exists)
		cur_line_split = cur_line.split('\"')
		# Skip any line that does contain a version
		if len(cur_line_split) < 2: continue
		artifact_id = ""
		if len(cur_line_split) >= 4:
			artifact_id = cur_line_split[-4]
		# Split lines based on quotes and get second to last string - this will be the version
		outdated_ver = cur_line.split('\"')[-2]
		ver_index = cur_line.find(outdated_ver)
		# Skip any line that does contain a version
		if not outdated_ver[0].isnumeric():	continue
		### Update group_id or artifact_id ###
		if artifact_id in artifact_id_ver_map:
			group_id_found[group_id] = True
			# Skip version updates that would decrement to a smaller version
			if outdated_ver == get_higher_version(outdated_ver, artifact_id_ver_map[artifact_id]): continue
			# Update version of artifact_id
			if artifact_id_ver_map[artifact_id] != outdated_ver:
				pdr_lines[i] = cur_line[:ver_index] \
					+ artifact_id_ver_map[artifact_id] \
					+ cur_line[ver_index+len(outdated_ver):]
				summary_log.append("PublishDocsRules.kt: Updated %s from %s to %s" %(artifact_id, outdated_ver, artifact_id_ver_map[artifact_id]))
				publish_docs_log.append(artifact_id+'-'+artifact_id_ver_map[artifact_id])
		if not artifact_id and group_id in group_id_ver_map:
			group_id_found[group_id] = True
			# Skip version updates that would decrement to a smaller version
			if outdated_ver == get_higher_version(outdated_ver, group_id_ver_map[group_id]): continue
			# Update version of group_id
			if group_id_ver_map[group_id] != outdated_ver:
				pdr_lines[i] = cur_line[:ver_index] \
					+ group_id_ver_map[group_id] \
					+ cur_line[ver_index+len(outdated_ver):]
				summary_log.append("PublishDocsRules.kt: Updated %s from %s to %s" %(group_id.lower(), outdated_ver, group_id_ver_map[group_id]))
				publish_docs_log.append(group_id.lower()+'-'+group_id_ver_map[group_id])
	for group_id in group_id_found:
		if not group_id_found[group_id]:
			insert_new_group_id_into_pdr(pdr_lines, num_lines, group_id, group_id_ver_map)
	# Open file for writing and update all lines
	with open(PUBLISHDOCSRULES_FP, 'w') as f:
		f.writelines(pdr_lines)
	return True

def update_androidx(target, build_id, local_file):
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
		if not copy_and_merge_artifacts(repo_dir, './androidx', args.groups, args.artifacts):
			print_e('Failed to copy and merge AndroidX repository')
			return False
		print("Copy and merge artifacts... Successful")
		remove_type_aar_from_pom_files("androidx")
		remove_maven_metadata_files("androidx")
		# Now that we've merged new prebuilts, we need to update our version map
		group_id_ver_map, artifact_id_ver_map = get_updated_version_maps()
		if not args.skip_publishdocrules:
			if not update_publish_doc_rules(group_id_ver_map, artifact_id_ver_map):
				print_e('Failed to update PublicDocRules.kt')
				return False
			print("Update PublishDocsRules.kt... Successful")
		return True
	finally:
		# Remove temp directories and temp files we've created 
		rm(repo_dir)
		rm('%s.zip' % repo_dir)
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
	description=("""Import AndroidX prebuilts from the Android Build Server
		and if necessary, update PublishDocsRules.kt.  By default, uses
		top-of-tree-m2repository-all-<BUILDID>.zip to get artifacts."""))
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
	'--groups', metavar='group_id', nargs='+',
	help="""If specified, only update libraries whose group_id contains the listed text.
	For example, if you specify \"--groups paging slice lifecycle\", then this
	script will import each library with group_id beginning with \"androidx.paging\", \"androidx.slice\",
	or \"androidx.lifecycle\"""")
parser.add_argument(
	'--artifacts', metavar='artifact_id', nargs='+',
	help="""If specified, only update libraries whose artifact_id contains the listed text.
	For example, if you specify \"--artifacts core slice-view lifecycle-common\", then this
	script will import specific artifacts \"androidx.core:core\", \"androidx.slice:slice-view\",
	and \"androidx.lifecycle:lifecycle-common\"""")
parser.add_argument(
	'--no-commit', action="store_true",
	help='If specified, this script will not commit the changes')

# Parse arguments and check for existence of build ID or file
args = parser.parse_args()
args.file = True
if not args.source:
	parser.error("You must specify a build ID or local Maven ZIP file")
	sys.exit(1)

# Force the user to explicity decide which set of prebuilts to import
if args.all_prebuilts == False and args.groups == None and args.artifacts == None:
	print_e("Need to pass an argument such as --all-prebuilts or pass in group_ids or artifact_ids")
	print_e("Run `./import_release_prebuilts.py --help` for more info")
	sys.exit(1)

if not update_androidx('androidx', get_build_id(args), get_file(args)):
	print_e('Failed to update AndroidX, aborting...')
	sys.exit(1)

if args.no_commit:
	summary_log.append("These changes were NOT committed.")
else:
	if not commit_prebuilts(): sys.exit(1)
	commit_publish_docs_rules()

print_change_summary()
print("Test and check these changes before uploading to Gerrit")
