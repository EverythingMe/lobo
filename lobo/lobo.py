import sys
import re
import os
import datetime
import itertools
import pprint
import subprocess
from threading import Thread
import time
import json
import tempfile
from operator import itemgetter
from functools import partial
from distutils import spawn
from collections import Counter

import configuration
from issue_tracker import issue_tracker_tool
import git_tool
from code_review import cr_tool
from builder import builder_tool
from instant_messaging import im_tool
import user_db
from toolkit_base import ToolkitBase
from common import BOLD, UNDERLINE, RED, YELLOW, cd, compose
from git_tool import resolve_errors
from version import VERSION
from handling import FETCH_HANDLING, REBASE_HANDLING, APPROVAL_HANDLING, MERGE_HANDLING


LOG_LINE_BE_LIKE = re.compile(r'^[a-f0-9]{7} (FIXES )?([A-Z]+-\d+): ')
YES = ['Y', 'y']


def update():
    for cmd in ['pip', 'git']:
        if not spawn.find_executable(cmd):
            print '{0} not found. are you sure it\'s installed?'.format(cmd)
            exit(1)

    pip_version = subprocess.Popen('pip --version', shell=True, stdout=subprocess.PIPE).stdout.readline().split(' ')[1]
    pip_flags = '--process-dependency-links' if pip_version.startswith('1.5') else ''

    repo = tempfile.mkdtemp(suffix='lobo')

    subprocess.Popen('git clone {0} {1}'.format(WOLF_REPO_URL, repo), shell=True).wait()
    with cd(repo):
        subprocess.Popen('sudo pip install -U {0} .'.format(pip_flags), shell=True).wait()
        print BOLD('update complete')


def issue_from_branchname(branchname, squashed=False):
    try:
        parts = branchname.split('__')
        if len(parts) < (4 if squashed else 3):
            return None
        issue = parts[1]
        issue = re.findall("([a-z]+)([0-9]+)", issue)[0]
        issue = "%s-%s" % issue
        issue = issue.upper()
        return issue
    except:
        return None


def get_branches_for_issue(issue, squashed=False):
    branches = git_tool.get_all_branches(remote=True)
    return filter((lambda x: issue_from_branchname(x, squashed) == issue), branches)


def branchname_from_issue(issue, test=False, squashed=False, exit_on_fail=True):
    possible_branchnames = git_tool.recurse_submodules(lambda: get_branches_for_issue(issue, squashed), False, False)
    possible_branchname_set = set()
    for ret in possible_branchnames:
        submodule, branchnames = ret
        branchnames = filter(lambda x: x.endswith('__sq') == squashed, branchnames)
        if len(branchnames) == 1:
            possible_branchname_set.add(branchnames[0])
        elif len(branchnames) > 1:
            print "Found multiple possible branches in submodule %s: %r" % (submodule, branchnames)
            sys.exit(1)

    if len(possible_branchname_set) == 1:
        return possible_branchname_set.pop()

    if len(possible_branchname_set) == 0:
        if test:
            return None
        print "Failed to find branches matching issue %s" % issue
        sys.exit(1) if exit_on_fail else None

    if len(possible_branchname_set) > 1:
        if test:
            return None
        print "Found multiple possible branches for issue: %r" % possible_branchname_set
        sys.exit(1) if exit_on_fail else None

    return None


def get_current_branch():
    current_branches = git_tool.recurse_submodules(git_tool.get_current_branch, False, False, concurrent=True)

    grouped_branches = itertools.groupby(sorted(current_branches, key=itemgetter(1)), itemgetter(1))
    grouped_branches = {k: map(itemgetter(0), v) for k, v in grouped_branches}
    if len(grouped_branches) != 1:
        print "Invalid state: on more than one branch:"
        for branch_name, submodules in grouped_branches.iteritems():
            print '{}:'.format(branch_name)
            for submodule in submodules:
                print '\t{}'.format(submodule)
            print
        sys.exit(1)
    return grouped_branches.keys()[0]

def append_squashed_branch_suffix(branch):
    return branch + '__sq'

def strip_squashed_branch_suffix(squashed_branch):
    branch = squashed_branch
    if squashed_branch.endswith('__sq'):
        branch = squashed_branch[:-len('__sq')]
    return branch

def is_squashed_branch(branch):
    return branch.endswith('__sq')

def update_jira(fn, description):
    try:
        result = fn()
        message = description if result else 'update failed'
        print BOLD('JIRA:'), message
    except issue_tracker_tool.JIRAError as e:
        print BOLD('JIRA:'), e.text


def display_uninited_modules_instructions(uninited_modules):
    if uninited_modules:
        print RED('there are non initialized modules, first initialize {}'.format(uninited_modules))
        branch = git_tool.get_current_branch()
        for module in uninited_modules:
            module_name = module.split()[1]
            print RED('To init submodule type the following: git submodule update --init {module_name}; ' \
                      'cd {module_name}; ' \
                      'git checkout -b {branch}'.format(module_name=module_name, branch=branch))

def check_root():
    if not git_tool.is_at_root():
        print 'OMG where are we?! are you sure we\'re at the root project dir?'
        exit(-1)

class WorkOn(object):
    METHOD = 'work-on'
    DOC = 'Switch to an existing branch or tag (aka "checkout-remote")'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("target", help="what should be checked out? (issue / branchname / tag)")

    def handle(self, namespace):
        ret = self(namespace.target)

    def __call__(self, target):
        check_root()
        to_fetch = None
        if issue_tracker_tool.ISSUE_BE_LIKE.match(target) is None:
            # doesn't look like an issue
            to_fetch = [target]
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch(to_fetch)), **FETCH_HANDLING)
        kind = None
        if all(x[1] for x in git_tool.recurse_submodules(lambda: git_tool.is_remote_branch(target))):
            kind = "branch"
        elif all(x[1] for x in git_tool.recurse_submodules(lambda: git_tool.is_tag(target))):
            kind = "tag"
        elif issue_tracker_tool.validate_issue(target) is not None:
            _target = target
            target = branchname_from_issue(target, test=True)
            kind = "branch"

            if target is None:
                print ("Can't find any matching branches. You probably didn't run 'new-feature'")
                do_new_feature = raw_input("Do you want to run it now [y/N]?")
                if do_new_feature in YES:
                    new_feature(_target,labels=None)
                    target = branchname_from_issue(_target)
                else:
                    print RED("Please run new-feature first")
                    sys.exit(1)

        if kind is not None:
            resolve_errors(git_tool.recurse_submodules(lambda: git_tool.checkout_remote(target, kind)),
                           title="Checking out %s %s..." % (kind, target))
        else:
            print "Failed to resolve target '%s'" % target


class NewFeature(object):
    METHOD = 'new-feature'
    DOC = 'Start working on a new feature / bug / task'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("message", help="Feature to work on, can contain an existing jira ref (lobo new-feature \"AN-xxx\") or create a new task/bug (lobo new-feature \"new DISCO task: cool new task\")")
        parser.add_argument('-l', action='append', help="The label of the issue)", default=[], dest="labels")

    def handle(self, namespace):
        ret = self(namespace.message, namespace.labels)

    def __call__(self, message, labels=None):
        check_root()
        if labels is None:
            labels = []

        key = summary = None
        try:
            issue = issue_tracker_tool.validate_issue(message.strip().upper())
            assert (issue is not None)
            summary = issue.fields.summary
            key = issue.key
        except Exception, e:
            print e
            message = issue_tracker_tool.process_message(message, labels)
            summary = message.summary
            key = message.issue
            issue = issue_tracker_tool.get_jira_server().issue(key)

        # look for existing branches before creating a new one
        existing_branches = [s for s in git_tool.get_all_branches() if key.replace('-', '').lower() in s]
        if existing_branches:
            print "There is already a branch for issue {issue}: {branches}".format(issue=key, branches=str(existing_branches))
            exit(1)

        branch_name = "%s__%s__%s" % (issue_tracker_tool.get_jira_username(),
                                      key.replace('-', ''),
                                      summary)
        branch_name = branch_name.replace(' ', '_').lower()
        branch_name = "".join(re.findall("[a-z0-9_]", branch_name))
        while '__' in branch_name.split('__', 2)[2]:
            parts = branch_name.split('__', 2)
            parts[2] = parts[2].replace('__', '_')
            branch_name = "__".join(parts)
        branch_name = branch_name[:40]
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.checkout_remote('master', kind="branch")),
                       title="Checking out master...")
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.new_branch(branch_name)),
                       title="Creating new branch...")
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.forcepush(branch_name)),
                       title="Pushing newly created branches...")

        update_jira(partial(issue_tracker_tool.start_progress, key), 'Started progress')


class Commit(object):
    METHOD = 'commit'
    DOC = 'Commit your work across all submodules'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("message", help="standard message")

    def handle(self, namespace):
        ret = self(namespace.message)

    def __call__(self, message):
        check_root()
        current_branches = get_current_branch()
        current_issue = issue_from_branchname(current_branches)
        message = "%s: %s" % (current_issue, message)

        def commit_if_necessary():
            status = git_tool.status()
            if status is None:
                return None, "Status is none??"
            if len(status.staged) > 0:
                return git_tool.gitcmd(["commit", "-nm", message])
            return None, None

        resolve_errors(git_tool.recurse_submodules(commit_if_necessary))


class Daily(object):
    METHOD = 'daily'
    DOC = 'Daily routine - rebase, fix-refs, push, (future: upload new translations)'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument('--no-checks', action='store_true')
        parser.add_argument('--no-push', action='store_true')

    def handle(self, namespace):
        checks = not namespace.no_checks
        push = not namespace.no_push
        ret = self(checks=checks, push=push)

    def __call__(self, checks=True, push=True):
        check_root()
        if checks:
            check_config()

        uninited_modules = git_tool.get_uninited_submodules()
        if uninited_modules:
            display_uninited_modules_instructions(uninited_modules)
            return

        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch(['master'])), **FETCH_HANDLING)
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.rebase_if_needed('master')), **REBASE_HANDLING)
        resolve_errors(git_tool.fix_refs(), title="Fixing submodule references")

        if push:
            resolve_errors(git_tool.recurse_submodules(git_tool.forcepush), title="Pushing...")


class Sync(object):
    METHOD = 'sync'
    DOC = 'Sync your work with the server'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self()

    def __call__(self):
        check_root()
        uninited_modules = git_tool.get_uninited_submodules()
        if uninited_modules:
            display_uninited_modules_instructions(uninited_modules)
            return

        current_branch = get_current_branch()
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch([current_branch])), **FETCH_HANDLING)
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.rebase_if_needed(current_branch)), **REBASE_HANDLING)
        resolve_errors(git_tool.fix_refs(), title="Fixing submodule references")
        resolve_errors(git_tool.recurse_submodules(git_tool.push), title="Pushing...")

class RebaseAndBuild(object):

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self(namespace)

    def __call__(self, namespace):
        check_root()
        branch = get_current_branch()
        authors = Counter()

        if is_squashed_branch(branch):
            print "You are trying to submit a squashed branch doll, go back to the original branch, it'll surely work!"
            return

        squashed_branch = append_squashed_branch_suffix(branch)
        issue = issue_from_branchname(branch)
        issue = issue_tracker_tool.validate_issue(issue)

        title = issue.fields.summary
        title = "%s: %s" % (issue.key, title)

        uninited_modules = git_tool.get_uninited_submodules()
        if uninited_modules:
            display_uninited_modules_instructions(uninited_modules)
            return
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch(['master'])), **FETCH_HANDLING)
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.rebase_if_needed('master')), **REBASE_HANDLING)

        def get_original_author():
            if git_tool.is_branch_diverged('origin/master'):
                authors[git_tool.get_author()] += 1

        list(git_tool.recurse_submodules(get_original_author))
        author = authors.most_common(1)[0][0] if authors else None

        def create_squashed_branch():
            git_tool.gitcmd(['branch', '-f', squashed_branch, branch])
            return git_tool.gitcmd(['checkout', squashed_branch])

        def squash():
            ret = err = None
            if git_tool.is_branch_diverged('origin/master'):
                ret, err = git_tool.squash(title, author)
            return ret, err

        def push_and_back():
            git_tool.gitcmd(['checkout', branch])
            return git_tool.forcepush(squashed_branch)

        resolve_errors(git_tool.recurse_submodules(git_tool.forcepush), title="Pushing...")
        resolve_errors(git_tool.recurse_submodules(create_squashed_branch), title="Creating squashed branch...")
        resolve_errors(git_tool.recurse_submodules(squash), title="Squashing...")
        resolve_errors(git_tool.fix_refs(), title="Fixing refs...")
        resolve_errors(git_tool.recurse_submodules(push_and_back), title="Pushing squashed branch...")

        self.process(namespace, squashed_branch)

    def build(self, post_build_task, assignee=None, branch=None, wait=False):
        print BOLD("Building...")
        builder_tool.build_launcher(branch=branch,
                                        profiles=["Debug"],
                                        block=wait,
                                        gitlab_token=cr_tool.get_gitlab_token(),
                                        assignee=assignee,
                                        split_apks="no",
                                        post_build_task=post_build_task)


class Submit(RebaseAndBuild):
    METHOD = 'submit'
    DOC = 'submit a change to review'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("assignee", help="who should the MR be assigned to? (username in gitlab)")

    def handle(self, namespace):
        if user_db.get_user_for_service(namespace.assignee, 'gitlab'):
            super(Submit, self).handle(namespace)
        else:
            print "There is no assignee by the name {}, " \
                  "I thought we sorted that imaginary friends situation, didn't we ??!".format(namespace.assignee)

    def process(self, namespace, squashed_branch):
        super(Submit, self).build("post-build-submit", assignee=namespace.assignee, branch=squashed_branch)


class PreLand(RebaseAndBuild):
    METHOD = 'pre-land'
    DOC = 'rebase and rebuild before landing'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-w", dest="wait", action='store_true', help="wait until the build finishes")

    def process(self, namespace, squashed_branch):
        super(PreLand, self).build("post-build-pre-land", branch=squashed_branch, wait=True)


class PostBuild(object):

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self()

    def __call__(self):
        squashed_branch = os.environ.get('BRANCH')
        assignee = os.environ.get('ASSIGNEE')
        assigner = os.environ.get('BUILD_USER_ID')
        build_number = os.environ.get('BUILD_NUMBER')
        apk_path = os.environ.get('APK_PATH')

        # # must have all parameters to continue
        # if not(squashed_branch and assignee and assigner and build_number):
        #     print RED("Cannot continue, got a missing environment variable BRANCH: {} ASSIGNEE: {} USER_ID: {} BUILD_NUMBER: {}"
        #               .format(squashed_branch, assignee, assigner, build_number))
        #     return

        branch = strip_squashed_branch_suffix(squashed_branch)
        issue = issue_from_branchname(branch)
        issue = issue_tracker_tool.validate_issue(issue)
        title = issue.fields.summary
        title = "%s: %s" % (issue.key, title)

        self.process(assigner, assignee, build_number, issue, title, apk_path, squashed_branch)

    def process(self):
        """
        run a post build task
        :return:
        """
        pass


class PostBuildForPreLand(PostBuild):
    METHOD = 'post-build-pre-land'
    DOC = "Not for mortals!!! This should be init from a Jenkins job once the build is completed successfully, " \
          "will create post build tasks for the 'pre-land' command (update via hipchat on successful build)"

    def process(self, assigner, assignee, build_number, issue, title, apk_path, squashed_branch):
        print "Sending notification to initiator"
        jenkins_job_url = builder_tool.get_build_path(build_number)
        jira_issue_url = issue_tracker_tool.get_issue_url(issue.key)
        issue_tracker_tool.comment_issue(issue.key, "Build {0}, [Download Link|{1}]".format(build_number, apk_path))
        hipchat_assigner = user_db.get_user_for_service(assigner, 'hipchat')
        im_tool.send_message(hipchat_assigner, "Build {0} ({1}) is successful, you can either wait for tests to finish, or be hasty and land it now! [{2}, {3}]"
                                  .format(build_number, issue, jenkins_job_url, jira_issue_url))


class PostBuildForSubmit(PostBuild):
    METHOD = 'post-build-submit'
    DOC = "Not for mortals!!! This should be init from a Jenkins job once the build is completed successfully, " \
          "will create post build tasks for the 'submit' command (update jira, create MRs, update via hipchat)"

    def process(self, assigner, assignee, build_number, issue, title, apk_path, squashed_branch):
        hipchat_assigner = user_db.get_user_for_service(assigner, 'hipchat')
        hipchat_assignee = user_db.get_user_for_service(assignee, 'hipchat')
        jenkins_job_url = builder_tool.get_build_path(build_number)
        jira_issue_url = issue_tracker_tool.get_issue_url(issue.key)
        issue_tracker_tool.comment_issue(issue.key, "Build {0}, [Download Link|{1}]".format(build_number, apk_path))
        im_tool.send_message(hipchat_assigner, "Build {0} ({1}) is successful, listing MRs... [{2}, {3}]".format(build_number, issue, jenkins_job_url, jira_issue_url))
        im_tool.send_message(hipchat_assignee, "Build {0} ({1}) is successful, MRs are coming your way... [{2}, {3}]".format(build_number, issue, jenkins_job_url, jira_issue_url))

        def open_mr():
            git_tool.fetch(['master'])
            if git_tool.is_branch_diverged('origin/master'):
                mr = cr_tool.create_mr(git_tool.get_repo(), squashed_branch, assignee, "WIP: "+title)
                cr_tool.approve_build(git_tool.get_repo(), squashed_branch, build_number)


                im_tool.send_message(hipchat_assigner, "MR {0} has been assigned to @{1}".format(mr, hipchat_assignee))
                im_tool.send_message(hipchat_assignee, "Hey, @{0} sent you a MR to review: {1}".format(hipchat_assigner, mr))
                return mr, None
            return None, None


        resolve_errors(git_tool.recurse_submodules(open_mr), title="Opening MRs...")
        update_jira(partial(issue_tracker_tool.send_to_cr, issue.key, user_db.get_user_for_service(assignee, 'jira')),
                    'Requested code review')

class Test(object):
    METHOD = 'test'
    DOC = 'test build your branch'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self()

    def __call__(self):
        check_root()
        branch = get_current_branch()
        resolve_errors(git_tool.recurse_submodules(git_tool.forcepush), title="Pushing...")
        print BOLD("Building")
        builder_tool.build_launcher(branch, ["Debug"], False)


def issues_not_in_branch(branchname):
    cmd = 'log --oneline {0}..{1}'.format(branchname, 'origin/master')
    ret, _ = git_tool.gitcmd(cmd)
    keys = LOG_LINE_BE_LIKE.findall(ret)
    keys = set(x[1] for x in keys)

    return list(keys)


class Release(object):
    METHOD = 'release'
    DOC = 'released all issues in the current RC'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-p", dest='project', help="Jira project name", default='Android,Context,Discovery')

    def handle(self, namespace):
        ret = self(namespace.project)

    def __call__(self, project="Android,Context,Discovery"):
        check_root()

        def mark_issues_to_released():
            """
            mark issues as RELEASED:
            we move all the issues in status IN_RC to status RELEASED
            """
            jql = 'project in ({0}) and status="{1}"'.format(project, issue_tracker_tool.JiraStatus.IN_RC)
            issues = issue_tracker_tool.search(jql)
            print "{0} issues found".format(len(issues))
            keys_in_rc = [issue.key for issue in issues]

            for key in set(keys_in_rc):
                print "{0}: marking as released".format(key)
                issue_tracker_tool.mark_as_released(key)
            print "Done marking issues as released"

        mark_issues_to_released()
        pass  # possibly, in the future add additional automation for release( except for Jira transitions)

class Freeze(object):
    METHOD = 'freeze'
    DOC = 'freeze a build into an RC branch'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("build_no", help="build number which should be frozen")
        parser.add_argument("-p", dest='project', help="Jira project name", default='Android,Context,Discovery')

    def handle(self, namespace):
        ret = self(int(namespace.build_no), namespace.project)

    def __call__(self, build_no, project="Android,Context,Discovery"):
        check_root()
        tag = "cibuild_%s" % build_no
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch()), **FETCH_HANDLING)

        # make sure we get the correct week even if we freeze on Sunday
        now = datetime.datetime.now()
        day = datetime.timedelta(days=1)
        cal = (now+day).isocalendar()
        year = cal[0]
        pulse = cal[1]
        branchname = "rc-%d-%02d" % (year, pulse)

        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.new_branch(branchname, tag)),
                       title="Freezing into %s" % branchname)
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.forcepush(branchname)),
                       title="Pushing %s" % branchname)

        def protect():
            repo = git_tool.get_repo()
            success = cr_tool.protect_branch(repo, branchname)
            return None, None if success else "Failed"

        def mark_issues_to_rc():
            """
            mark issues as IN_RC:
            we search Jira for all issues with IN_MASTER status and then exclude issues not found in the git log
            of the branchname
            """
            jql = 'project in ({0}) and status="{1}"'.format(project, issue_tracker_tool.JiraStatus.LANDED_IN_MASTER)
            issues = issue_tracker_tool.search(jql)
            keys_in_master = [issue.key for issue in issues]

            exclude = issues_not_in_branch(branchname)
            print 'excluding issues not in {0}'.format(branchname), exclude

            for key in set(keys_in_master) - set(exclude):
                print "{0}: marking in rc".format(key)
                issue_tracker_tool.mark_in_rc(key, branchname)

        resolve_errors(git_tool.recurse_submodules(protect), title="Protecting %s" % branchname)

        mark_issues_to_rc()

        print BOLD("Initiating a build")
        rc_build_no, success = builder_tool.build_launcher(branch=branchname,
                                    profiles=["Debug"],
                                    block=True,
                                    gitlab_token=cr_tool.get_gitlab_token(),
                                    split_apks="yes")

        if success:
            print BOLD("Updating Rollout")
            rollout_tool.create_release(rc_build_no, 0)  # freezing a release is always with distribution=0

            print BOLD("Sending event to Timebox")
            timebox_tool.send_event('freeze', rc_build_no, '0', pulse, builder_tool.get_build_path(str(rc_build_no)))


class Land(object):
    METHOD = 'land'
    DOC = 'land a fix into master'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("what", help="what should be landed (issue/branchname)")
        parser.add_argument("--allow-not-ff", help="allow landing even if target is not rebased with master",
                            action='store_true', default=False, dest='ok_no_ff')

    def handle(self, namespace):
        ret = self(namespace.what, namespace.ok_no_ff)

    def __call__(self, what, ok_no_ff):
        check_root()

        if get_current_branch() != 'master':
            print "You should be on the master branch before landing a feature, sweetie!"
            return
        fetched = False
        if issue_tracker_tool.ISSUE_BE_LIKE.match(what) is not None:
            issue = what
            branchname = branchname_from_issue(issue, test=True, squashed=True)
            if branchname is None:
                resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch()), **FETCH_HANDLING)
                fetched = True
                branchname = branchname_from_issue(what, squashed=True)
        else:
            branchname = what
            issue = issue_from_branchname(what, squashed=True)
        if not is_squashed_branch(branchname):
            print YELLOW("Warning: landning non-squashed branch!")
        if issue is None:
            print YELLOW("Warning: unknown issue!")

        def is_ready_to_land():
            if not fetched:
                git_tool.fetch([branchname, 'master'])
            if git_tool.is_merged_with("origin/%s" % branchname, ref="origin/master"):
                return None, None

            err = []
            if not git_tool.is_merged_with("origin/master", ref="origin/%s" % branchname):
                err.append("Not rebased!")
            approvals = list(cr_tool.get_signed_comments(git_tool.get_repo(), branchname))
            body = lambda x: x['body']
            built = filter(compose(cr_tool.ApproveBuild.filter_message, body), approvals)
            cr = filter(compose(cr_tool.ApproveCR.filter_message, body), approvals)
            qa = filter(compose(cr_tool.ApproveQA.filter_message, body), approvals)
            ui = filter(compose(cr_tool.ApproveUITests.filter_message, body), approvals)
            probe = filter(compose(cr_tool.ApproveProbeTests.filter_message, body), approvals)


            ret = []
            if len(built) == 0:
                err.append("Wasn't built!")
            else:
                ret.extend('Built by %s at %s' % (x['author']['name'], x['created_at']) for x in built)
            if len(cr) == 0:
                err.append("Wasn't reviewed!")
            else:
                ret.extend('Reviewd by %s at %s' % (x['author']['name'], x['created_at']) for x in cr)
            if len(qa) == 0:
                err.append("Didn't pass QA!")
            else:
                ret.extend("Passed QA's %s at %s" % (x['author']['name'], x['created_at']) for x in qa)
            if len(ui) == 0:
                err.append("Didn't pass UI tests!")
            else:
                ret.extend("Passed UI Tests at %s" % x['created_at'] for x in ui)
            if len(probe) == 0:
                err.append("Didn't pass Probe benchmark test")
            else:
                ret.extend("Passed Probe benchmark test at %s" % x['created_at'] for x in probe)

            return "\n".join(ret), (None if len(err) == 0 else "\n".join(err))

        resolve_errors(git_tool.recurse_submodules(is_ready_to_land), **APPROVAL_HANDLING)


        def do_push():
            return git_tool.push('master')

        def do_merge():
            ret, err = git_tool.gitcmd(['merge', '--ff' if ok_no_ff else '--ff-only', 'origin/%s' % branchname])
            if err is not None:
                return ret, err

            return ret, None

        merge_success = resolve_errors(git_tool.recurse_submodules(do_merge), **MERGE_HANDLING)
        if merge_success:
            resolve_errors(git_tool.fix_refs(), title="Fixing submodule references")
            push_success = resolve_errors(git_tool.recurse_submodules(do_push), title="Pushing...")

            # Make sure all MR for this issue in gitlab are closed
            def check_open_mr():
                repo = git_tool.get_repo()
                project = cr_tool.get_project(repo)
                mr = cr_tool.get_open_mr(project, branchname)
                if mr is not None:
                    print RED("ALERT: merge request is still open in GitLab for {}!".format(repo))
                    return None, "ALERT: merge request is still open in GitLab"
                return None, None

            gitlab_check_success = resolve_errors(git_tool.recurse_submodules(check_open_mr), title="Checking GitLab status...")
            if not gitlab_check_success:
                print RED("ERROR: there are still open MR in GitLab after land for {}, something is terribly wrong!!".format(issue))

            if push_success and issue is not None:
                update_jira(partial(issue_tracker_tool.land, issue), 'landed in master')
                return push_success
        return False

class Backout(object):
    METHOD = 'backout'
    DOC = 'pick a specific feature/fix to backout from master'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue which should be elevated")
        parser.add_argument("-n", help="dry run", action="store_true", default=False, dest="dry_run")

    def handle(self, namespace):
        self(namespace.issue, namespace.dry_run)

    def __call__(self, issue, dry_run):
        check_root()
        branch = get_current_branch()
        if branch != 'master':
            work_on('master')

        # list of reverted commits and their 'revert commits'
        excluded_commits = set()

        def should_revert(commit):
            message = commit['message']
            if "This reverts commit" in message:
                revert_commit = commit['id']
                reverted_commit = message.split("This reverts commit", 1)[1].strip(' .')
                excluded_commits.add(revert_commit)
                excluded_commits.add(reverted_commit)
                print '{repo}: {reverted_commit} is already reverted by {revert_commit}'\
                    .format(repo=git_tool.get_repo(), reverted_commit=reverted_commit, revert_commit=revert_commit)
                return False

            return not commit['id'] in excluded_commits

        def do_the_revert():
            GIT_COMMIT_FIELDS = ['id', 'author_name', 'author_email', 'date', 'message']
            GIT_LOG_FORMAT = ['%H', '%an', '%ae', '%ad', '%B']
            GIT_LOG_FORMAT = '%x1f'.join(GIT_LOG_FORMAT) + '%x1e'
            REVERT_TEMPLATE = """Revert "{message}"\n\nThis reverts commit {commit}."""

            # ":" is added to issue id to prevent mistakes (--grep AN-xxx:)
            (log, err) = git_tool.gitcmd(['log', '--grep', issue+':', '--format={}'.format(GIT_LOG_FORMAT)])
            if not log:
                return log, err
            # turn log into a list of dictionaries for for easier use
            log = log.strip('\n\x1e').split("\x1e")
            log = [row.strip().split("\x1f") for row in log]
            log = [dict(zip(GIT_COMMIT_FIELDS, row)) for row in log]

            # filter only those commits which have not been reverted already
            revert_candidates = filter(should_revert, log)
            ret = None if not revert_candidates else '\n'.join(map(str, revert_candidates))

            if not dry_run:
                for commit in revert_candidates:
                    # try reverting
                    revert_ret, revert_err = git_tool.gitcmd(['revert','--no-edit',commit['id']])

                    submodules = None
                    if revert_err is not None:
                        # try resolving submodule reference issues automatically
                        gitstatus = git_tool.status()
                        if submodules is None:
                            submodules = git_tool.get_submodules()
                            if submodules is None:
                                return ret, err
                        non_subs = set(gitstatus.conflict) - set(submodules)
                        if len(non_subs) > 0:
                            print "Conflict in non submodules %r" % non_subs
                            return revert_ret, revert_err
                        for sub in gitstatus.conflict:
                            print "Adding %s" % sub
                            add_ret, add_err = git_tool.gitcmd(['add', sub])
                            if add_err is not None:
                                return revert_ret, revert_err
                        commit_ret, commit_err = git_tool.gitcmd(['commit', '-m', REVERT_TEMPLATE.format(message=commit['message'], commit=commit['id'])])

                        return commit_ret, commit_err

                    if revert_err:
                        ret = revert_ret
                        err = revert_err
            return ret, err

        if not dry_run:
            input = raw_input(RED("Are you sure you want backout {issue}? "
                    "(It is advised that you use '-n' to initiate a dry run first) [y/N]".format(issue=issue)))
            if input not in ['Y', 'y']:
                sys.exit(0)

        ret = resolve_errors(git_tool.recurse_submodules(do_the_revert), title="Reverting...")

        #there was an error during resolve_errors, don't reopen the ticket just yet
        if not ret:
            print "OMG! There was an error during revert. Fix it and try again..."
            exit(1)

        if not dry_run:
            print 'Stopping Progress on Jira issue {issue}'.format(issue=issue)
            if issue_tracker_tool.stop_progress(issue):
                print 'Successfully stopped progress on {issue}'.format(issue=issue)
            else:
                print 'Could not stop progress on {issue}'.format(issue=issue)

        return ret

class CherryPick(object):
    METHOD = 'cherry-pick'
    DOC = 'pick a specific fix into an RC branch'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue which should be elevated")
        parser.add_argument("branchname", help="name of RC branch")

    def handle(self, namespace):
        ret = self(namespace.issue, namespace.branchname)

    def __call__(self, issue, branchname):
        check_root()
        work_on(branchname)

        def do_the_cherry():
            if os.path.exists('.git/CHERRY_PICK_HEAD'):
                ret, err = git_tool.gitcmd(['cherry-pick', '--allow-empty-message', '--continue'])
                if err is not None:
                    return ret, err
            ret, err = git_tool.gitcmd(
                ['log', '--grep=%s' % issue, '--reverse', '--date-order', '--cherry', '--oneline',
                 '%s..origin/master' % branchname])
            if err is not None:
                return ret, err
            commits = [x[1:].split() for x in ret.split('\n') if len(x) > 1]
            commits = [x[0] for x in commits if len(x) > 0]
            if len(commits) > 0:
                print BOLD("applying " + ", ".join(UNDERLINE(x) for x in commits))
                commits = ['cherry-pick'] + commits
            else:
                return None, None
            return git_tool.gitcmd(commits)

        return resolve_errors(git_tool.recurse_submodules(do_the_cherry), title="Cherry Picking...")


class ApproveGeneric(object):
    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("what", help="issue/branchname which should be %s approved" % cls.KIND)

    def handle(self, namespace):
        ret = self(namespace.what)

    @staticmethod
    def is_issue(what):
        return issue_tracker_tool.ISSUE_BE_LIKE.match(what) is not None

    def __call__(self, what):
        resolve_errors(git_tool.recurse_submodules(lambda: git_tool.fetch()), **FETCH_HANDLING)

        if self.is_issue(what):
            branchname = branchname_from_issue(what, test=True, squashed=True)
        else:
            branchname = what

        def approve():
            if git_tool.is_merged_with("origin/%s" % branchname, ref="origin/master"):
                return None, None
            added = self.APPROVAL_FUNC(git_tool.get_repo(), branchname)
            return added, None

        resolve_errors(git_tool.recurse_submodules(approve), title="Marking your approvals...")

    def get_issue(self,what):
        if self.is_issue(what):
            return what
        else:
            return issue_from_branchname(what,what.endswith('__sq'))


class ApproveCR(ApproveGeneric):
    METHOD = 'approve-cr'
    DOC = 'mark an issue as CR approved'
    KIND = "CR"
    APPROVAL_FUNC = cr_tool.approve_cr

    def __call__(self, what):
        super(ApproveCR, self).__call__(what)
        issue = self.get_issue(what)
        if issue is not None:
            update_jira(partial(issue_tracker_tool.send_to_qa, issue), 'marked CR approved, requesting QA')

        msg = "@{assigner} just finished reviewing your code for {issue} and it's good to go! Sending to QA..."
        notify_hipchat_cr(msg, issue)


class ApproveQA(ApproveGeneric):
    METHOD = 'approve-qa'
    DOC = 'mark an issue as QA approved'
    KIND = "QA"
    APPROVAL_FUNC = cr_tool.approve_qa

    def __call__(self, what):
        super(ApproveQA, self).__call__(what)
        issue = self.get_issue(what)
        if issue is not None:
            update_jira(partial(issue_tracker_tool.resolve_issue, issue), 'marked QA approved')


class ApproveUITests(ApproveGeneric):
    METHOD = 'approve-ui-tests'
    DOC = 'mark an issue passed UI tests'
    KIND = "UI-TESTS"
    APPROVAL_FUNC = cr_tool.approve_ui_tests


class Reopen(object):
    METHOD = 'reopen'
    DOC = 'Reopen an issue'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue to reopen")

    def handle(self, namespace):
        ret = self(namespace.issue)

    def __call__(self, issue):
        return issue_tracker_tool.reopen(issue)


class RejectCR(object):
    METHOD = issue_tracker_tool.reject.METHOD + "-cr"
    DOC = issue_tracker_tool.reject.DOC

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue to reopen")

    def handle(self, namespace):
        ret = self(namespace.issue)

    def __call__(self, issue):
        issue_tracker_tool.reject(issue)
        msg = "@{assigner} just finished reviewing your code for {issue} and there are fixes to be made. Enjoy :)"
        notify_hipchat_cr(msg, issue)


class Info():
    METHOD = 'info'
    DOC = 'prints the current version and running config'

    def collect_info(self):
        info = configuration.get_running_config()
        info['version'] = VERSION
        return info

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print json.dumps(self.collect_info(), indent=2, sort_keys=True)

    def __call__(self):
        return self.collect_info()


class CheckConfig():
    METHOD = 'check-config'
    DOC = 'test your configuration'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        self()

    def __call__(self):
        threads = []
        jenkins_t = Thread(target=test_jenkins_connection)
        threads.append(jenkins_t)
        jira_t = Thread(target=test_jira_connection)
        threads.append(jira_t)
        gitlab_t = Thread(target=test_gitlab_connection)
        threads.append(gitlab_t)
        hipchat_t = Thread(target=test_hipchat_connection)
        threads.append(hipchat_t)

        # Start all threads
        [t.start() for t in threads]

        # Wait for all of them to finish
        [t.join() for t in threads]


def test_jenkins_connection():
    if builder_tool.test_connection():
        print "Jenkins credentials verified"


def test_jira_connection():
    if issue_tracker_tool.test_connection():
        print "JIRA credentials verified"


def test_gitlab_connection():
    if cr_tool.test_connection():
        print "GitLab credentials verified"


def test_hipchat_connection():
    if im_tool.test_connection():
        print "HipChat credentials verified"


class Update():
    METHOD = 'update'
    DOC = 'update lobo'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        self()

    def __call__(self):
        return update()


class ShowOpenIssues():
    METHOD = 'show-open-issues'
    DOC = 'Show the open issues of a user in the CurrentWork sprint'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-user", default=None, help="user assigned to the open issues, no input is current user")

    def handle(self, namespace):
        ret = self(namespace.user)

    def __call__(self, user=None):
        # issues assigned to user
        print 'Getting issues, be patient...'
        issues = issue_tracker_tool.get_open_issues(user)
        if len(issues) > 0:
            print '\n\nOpen issues for {0}\n--------------------------'.format(issues[0].fields.assignee)
            for issue in issues:
                print "%-12s|  %-20s|  %s" % (issue.key, issue.fields.status, issue.fields.summary)
        else:
            print 'No open issues found'

        # issues waiting for user's review
        issues = issue_tracker_tool.get_issues_to_review(user)
        if len(issues) > 0:
            print '\n\nIssues waiting for review by {0}\n--------------------------'.format(
                getattr(issues[0].fields, issue_tracker_tool.CUSTOM_FIELD_REVIEWER))
            for issue in issues:
                print "%-12s|  %-20s|  %s" % (issue.key, issue.fields.status, issue.fields.summary)


class UpdateQA():
    METHOD = 'update-qa'
    DOC = 'Notifies the QA hipchat room that there\'s a build ready for testing'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue to reopen")
        parser.add_argument("-t", dest='tester', help="Assigned tester to mention")
        parser.add_argument("-m", dest='message', help="Specific message for QA")

    def handle(self, namespace):
        ret = self(namespace.issue, namespace.tester, namespace.message)

    def __call__(self, issue, tester=None, message=None):

        if not tester:
            tester = issue_tracker_tool.get_tester(issue)
        latest_build = issue_tracker_tool.get_latest_build(issue)

        link = issue_tracker_tool.get_link(issue)
        summary = issue_tracker_tool.get_summary(issue)
        msg = message+'.' if message else ''
        user = '@{} - Enjoy!'.format(user_db.get_user_for_service(tester, 'hipchat')) if tester else ''
        notification = '@here Yo! {link} ({summary}) is ready for testing! Please grab {latest_build}. {msg} {user}'\
            .format(link=link, summary=summary, latest_build=latest_build, msg=msg, user=user)
        im_tool.send_message('QA', notification)


class Abort():
    METHOD = 'abort'
    DOC = 'Closes all existing open merge requests and aborts the Jira ticket'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("issue", help="issue to abort")

    def handle(self, namespace):
        ret = self(namespace.issue)

    def __call__(self, issue):
        print BOLD("Aborting issue {}...".format(issue))
        branchname = branchname_from_issue(issue, squashed=True, exit_on_fail=False)

        def close():
            if git_tool.is_merged_with("origin/%s" % branchname, ref="origin/master"):
                return None, None
            closed = cr_tool.close_mr(git_tool.get_repo(), branchname)
            return closed, None

        # close open MRs, if there are any
        if branchname:
            resolve_errors(git_tool.recurse_submodules(close), title="Closing open MRs...")
        else:
            print BOLD("No open MRs to close")

        # move Jira ticket to "Aborted"
        print BOLD("Aborting Jira ticket...")
        issue_tracker_tool.abort(issue)
        print BOLD("DONE")

class NotifyBugs():
    METHOD = 'notify-bugs'
    DOC = 'Sends a Hipchat notification to all who have blocker bugs assigned to them waiting in ToDo'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self()

    def __call__(self):
        print 'Getting issues, be patient...'
        issues = issue_tracker_tool.get_blocker_bugs_todo()

        for issue in issues:
            assignee = issue_tracker_tool.get_assignee(issue)
            hipchat_assignee = user_db.get_user_for_service(assignee, 'hipchat')
            link = issue_tracker_tool.get_link(issue)
            summary = issue_tracker_tool.get_summary(issue)
            print 'Notifying {assignee}: {summary} ({link})'.format(assignee=assignee, summary=summary, link=link)

            msg = 'A critical bug is assigned to you:\n{summary} ({link}) \nJust do it :)'.format(
                summary=summary, link=link)
            im_tool.send_message(hipchat_assignee, msg)


def pretty_elapsed(elapsed):
    if elapsed < 60:
        return 'took {:.2f} seconds'.format(elapsed)

    mm, ss = divmod(elapsed, 60)
    return 'took {:.0f}.{:.0f} minutes'.format(mm, ss)


def notify_hipchat_cr(msg, issue):
    assigner = issue_tracker_tool.get_reviewer(issue)
    assignee = issue_tracker_tool.get_assignee(issue)
    hipchat_assignee = user_db.get_user_for_service(assignee, 'hipchat')
    hipchat_assigner = user_db.get_user_for_service(assigner, 'hipchat')
    im_tool.send_message(hipchat_assignee, msg.format(assigner=hipchat_assigner, issue=issue))

def lobo_entry():

    parser = ToolkitBase( [WorkOn, NewFeature, Commit, Daily, Submit, PreLand, Land, Backout, Freeze, ApproveCR,
                           ApproveQA, CherryPick, Test, Info, Reopen, RejectCR, CheckConfig, Update,
                           ApproveUITests, Sync, Release, ShowOpenIssues, PostBuildForPreLand, PostBuildForSubmit,
                           configuration.SetEnv, configuration.Config, configuration.GetConfig,
                           UpdateQA, Abort, NotifyBugs] )
    started = time.time()
    parser.parse()
    elapsed = time.time() - started
    if elapsed > 1:
        print pretty_elapsed(elapsed)


new_feature = NewFeature()
work_on = WorkOn()
commit = Commit()
daily = Daily()
test = Test()
submit = Submit()
pre_land = PreLand()
freeze = Freeze()
land = Land()
backout = Backout()
approve_cr = ApproveCR()
approve_qa = ApproveQA()
approve_ui_tests = ApproveUITests()
reopen = Reopen()
reject_cr = RejectCR()
cherry_pick = CherryPick()
check_config = CheckConfig()
sync = Sync()
release = Release()
show_open_issues = ShowOpenIssues()
update_qa = UpdateQA()
abort = Abort()
notify_bugs = NotifyBugs()

post_build_pre_land = PostBuildForPreLand()
post_build_submit = PostBuildForSubmit()

if __name__ == "__main__":
    lobo_entry()
