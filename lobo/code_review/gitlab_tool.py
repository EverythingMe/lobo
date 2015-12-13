import os
import sys
import time
import datetime
import md5

import dateutil.parser

import gitlab
from configuration import get_config, handle_missing_config
from toolkit_base import ToolkitBase

# GITLAB_TOKEN might be set as an environment variable (used by jenkins when creating an MR).
# This overrides the git config 'gitlab.token'
gitlab_token = os.environ.get('GITLAB_TOKEN')
gitlab_server= ''


def get_gitlab_token():
    global gitlab_token, gitlab_server
    if gitlab_token:
        return gitlab_token

    gitlab_token = get_config("gitlab.token")
    if not gitlab_token:
        handle_missing_config("Please set your gitlab private token:",
                                            'gitlab.token')
    else:
        return gitlab_token

instance = None


def get_instance():
    global instance
    if instance is None:
        gitlab_server = get_config("gitlab.server")
        instance = gitlab.Gitlab(gitlab_server, token=get_gitlab_token())
    return instance


def get_project(project):
    gl = get_instance()
    project = gl.getproject(project)
    if not project:
        print "ERROR: failed to find project {0}".format(project)

    return project


def get_project_member(project, username):
    gl = get_instance()
    members = gl.getprojectmembers(project['id'], per_page=100)
    for member in members:
        if member['username'] == username:
            return member
    members = gl.getgroupmembers(project['namespace']['id'], per_page=100)
    for member in members:
        if member['username'] == username:
            return member
    print "FAILED to find user for %s" % username


def get_open_mr(project, branch):
    gl = get_instance()
    for i in range(0, 10000, 100):
        mrs = gl.getmergerequests(project['id'], page=(i / 100) + 1, per_page=100)
        if len(mrs) == 0:
            break
        for mr in mrs:
            if mr['state'] != 'opened':
                continue
            if mr['target_project_id'] != project['id']:
                print mr
                continue
            if mr['source_branch'] == branch:
                return mr


def actually_create_mr(project, source_branch, target_branch, title, assignee):
    gl = get_instance()
    assignee = get_project_member(project, assignee)
    print 'assignee_id', assignee['id']
    print 'project id', project['id']
    print source_branch, '->', target_branch
    print 'title', title
    return gl.createmergerequest(project['id'], source_branch, target_branch,
                                 title, project['id'], assignee['id'])


def actually_update_mr(project, mr, source_branch, target_branch, title, assignee):
    gl = get_instance()
    assignee = get_project_member(project, assignee)
    # print 'assignee_id',assignee['id']
    # print 'project id',project['id']
    # print 'mr id',mr['id']
    # print source_branch,'->',target_branch
    # print 'title',title
    return gl.updatemergerequest(project['id'], mr['id'], source_branch=source_branch, target_branch=target_branch,
                                 title=title, assignee_id=assignee['id'])


class CommentMR(object):
    METHOD = 'comment-mr'
    DOC = 'Add a comment to an mr'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="branch name")
        parser.add_argument("comment", help="branch name")

    def handle(self, namespace):
        self(namespace.repo, namespace.branch, namespace.comment)

    def __call__(self, repo, sourceBranch, comment):
        gl = get_instance()
        project = get_project(repo)
        if not project:
            return "Failed to find project"
        mr = get_open_mr(project, sourceBranch)
        if mr is not None:
            gl.addcommenttomergerequest(project['id'], mr['id'], comment)
            return "%s -> %s" % (comment, repo)
        return None

class CreateMR(object):
    METHOD = "create-mr"
    DOC = "Creates a new MR (in case it doesn't already exist)"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="branch name")
        parser.add_argument("assignee", help="assignee (username in gitlab)")
        parser.add_argument("title", help="title for the MR")

    def handle(self, namespace):
        for approval in self(namespace.repo, namespace.branch):
            print "%s:%s by %s" % (approval['created_at'], approval['body'], approval['author']['name'])

    def __call__(self, repo, sourceBranch, assignee, title):
        gl = get_instance()
        project = get_project(repo)
        assert (project['merge_requests_enabled'])
        mr = get_open_mr(project, sourceBranch)
        if mr is None:
            print "Creating a MR"
            mr = actually_create_mr(project, sourceBranch, 'master', title, assignee)
        else:
            success = actually_update_mr(project, mr, sourceBranch, 'master', title, assignee)
            print "Updated MR"

        return "%s/%s/merge_requests/%s/" % (gitlab_server, repo, mr['iid'])


class GetFile(object):
    METHOD = "get-file"
    DOC = "Read a file from a repository"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("ref", help="The name of branch, tag or commit")
        parser.add_argument("path", help="Full path to the file")

    def handle(self, namespace):
        content = self(namespace.repo, namespace.ref, namespace.path)
        if content is not None:
            print content
        else:
            print "No such file!"

    def __call__(self, repo, ref, full_path):
        gl = get_instance()
        project = get_project(repo)
        context = gl.getfile(project['id'], full_path, ref)
        if context is not False:
            return context['content'].decode('base64')
        else:
            return None


def set_file(repo, ref, full_path, contents, message):
    gl = get_instance()
    project = get_project(repo)
    if not gl.updatefile(project['id'], full_path, ref, contents, message):
        gl.createfile(project['id'], full_path, ref, contents, message)


class CloseMR(object):
    METHOD = "close-mr"
    DOC = "Closes a merge request"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="The name of branch")

    def handle(self, namespace):
        print self()

    def __call__(self, repo, branch):
        gl = get_instance()
        project = get_project(repo)
        mr = get_open_mr(project, branch)
        gl.updatemergerequest(project_id=project['id'], mergerequest_id=mr['id'], state_event="close")


class ProtectBranch(object):
    METHOD = "protect-branch"
    DOC = "Mark a branch in a repo as protected"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="The name of branch")

    def handle(self, namespace):
        print "Success" if self(namespace.repo, namespace.branch) else "Failed"

    def __call__(self, repo, branch):
        gl = get_instance()
        project = get_project(repo)
        success = gl.protectbranch(project['id'], branch)
        return success


class TestConnection(object):
    METHOD = "test-connection"
    DOC = "Test the GitLab credentials"

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        project = get_projects()
        return project is not False
