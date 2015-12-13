import os
import re
import sys
import configuration
from configuration import get_config

from common import YELLOW

from toolkit_base import ToolkitBase

from jira.client import JIRA
from jira.resources import Issue
import jira.exceptions

import logging

logging.basicConfig()
Logger = logging.getLogger('JiraTool')
Logger.setLevel(logging.DEBUG)

CONNECTION_ERROR_MSG = "Failed to log in to JIRA, you may need to re-configure your jira password: lobo config --global jira.password <password>"
CUSTOM_FIELD_REVIEWER = 'customfield_10902'
CUSTOM_FIELD_TESTER = 'customfield_10903'
CUSTOM_FIELD_PULSE = 'customfield_11000'

ISSUE_BE_LIKE = re.compile(r'([A-Z]+-\d+)', flags=re.IGNORECASE)

JIRAError = jira.exceptions.JIRAError

jira_username = os.environ.get('ISSUE_MANAGER_USER')
jira_password = os.environ.get('ISSUE_MANAGER_PASS')


def get_jira_username():
    global jira_username
    if jira_username != None:
        return jira_username
    jira_username = get_config("jira.username")
    if jira_username is None:
        configuration.handle_missing_config('Please set your jira username:', 'jira.username', '<username>')
    else:
        return jira_username


def get_jira_password():
    global jira_password
    if jira_password != None:
        return jira_password
    jira_password = get_config("jira.password")
    if jira_password is None:
        configuration.handle_missing_config('Please set your jira password:', ' jira.password', '<password>')
    else:
        return jira_password


jira_server = None
jira_server_config = ''

def get_jira_server():
    global jira_server, jira_server_config
    if jira_server != None:
        return jira_server
    jira_server_config = get_config('jira.server')
    user = get_jira_username()
    password = get_jira_password()
    try:
        options = {'server': jira_server_config}
        jira_server = JIRA(options, basic_auth=(user, password))  # a username/password tuple
    except jira.exceptions.JIRAError as e:
        print
        print CONNECTION_ERROR_MSG
        print e
        print
        sys.exit(1)
    return jira_server


def get_issue_url(issue_id):
    return '/'.join((jira_server_config, 'browse', issue_id))


class Message:
    pass


def process_message(message, labels=[]):
    message = message.split('\n')
    ret = Message()
    ret.description = "".join(message[1:])  # currently description is always empty
    ret.labels = labels
    try:
        issue, ret.summary = message[0].split(':', 1)
        ret.summary = ret.summary.strip()
        issue = issue.lower().strip().split()
        ret.fixes = issue[0] == 'fixes'
        if ret.fixes:
            issue = issue[1:]
        ret.created = issue[0] == 'new'
        if ret.created:
            project = issue[1].upper()
            ret.kind = {'bug': 'Bug', 'task': 'Task', 'feature': 'New Feature'}[issue[2]]
            ret.issue = new_issue(project, ret.summary, ret.kind, description=ret.description, labels=ret.labels)
        else:
            ret.issue = issue[0].upper()
            validate_issue(ret.issue)

        ret.processed = "%s%s: %s\n%s" % ("FIXES" if ret.fixes else "", ret.issue, ret.summary, ret.description)
        return ret
    except Exception, e:
        print "Failed to parse message:"
        print e
        return None


def validate_issue(key):
    try:
        return get_jira_server().issue(key)
    except jira.exceptions.JIRAError:
        return None


def get_assignee(issue):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    if issue and issue.fields.assignee:
        return issue.fields.assignee.name
    else:
        return None


def get_reviewer(issue):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    if issue:
        return getattr(issue.fields, CUSTOM_FIELD_REVIEWER).name
    else:
        return None


def set_reviewer(issue, username):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    return issue.update(fields={CUSTOM_FIELD_REVIEWER: {'name': username}})


def get_tester(issue):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    if issue:
        tester = getattr(issue.fields, CUSTOM_FIELD_TESTER).name
        return None if tester == 'none' else tester
    else:
        return None


def set_tester(issue, username):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    return issue.update(fields={CUSTOM_FIELD_TESTER: {'name': username}})


def get_summary(issue):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    return issue.fields.summary


def set_pulse(issue, name):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)

    return issue.update(fields={CUSTOM_FIELD_PULSE: name})


def get_link(issue):
    key = issue if not type(issue) is Issue else issue.key
    return "{}/browse/{}".format(jira_server_config, key)


def get_latest_build(issue):
    if not type(issue) is Issue:
        issue = get_jira_server().issue(issue)
        for comment in reversed(issue.fields.comment.comments):
            if comment.raw['author']['displayName'] == "Builder Builderson":  #and
                body = (comment.raw['body']).replace('[Download Link|','').replace(']','')
                return body


class TestConnection(object):
    METHOD = 'test-connection'
    DOC = 'Test your settings'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        get_jira_server()
        return True  # if we got here...


class NewIssue(object):
    METHOD = 'new-issue'
    DOC = 'Create a new issue'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("project", help="project key")
        parser.add_argument("summary", help="Title of the ticket")
        parser.add_argument("-k", action='store', choices=["Bug", "Task", "New Feature"],
                            help="The kind of the issue", default="Bug", dest="kind")
        parser.add_argument("--user", action='store',
                            help="User to assign the issue to (default is current user)",
                            default=None, dest="assignee")
        parser.add_argument("-l", action='append',
                            help="The label of the issue)", default=[], dest="labels")

    def handle(self, namespace):
        self(namespace.project, namespace.summary, namespace.kind, namespace.assignee, namespace.labels)

    def __call__(self, project, summary, kind, assignee=None, description='', labels=[]):
        server = get_jira_server()
        new_issue = server.create_issue(project={'key': project}, summary=summary,
                                        description=description, issuetype={'name': kind})
        if assignee is None:
            assignee = get_jira_username()
        server.assign_issue(new_issue, assignee)

        if labels:
            new_issue.update(labels=labels)

        print "Created issue %s" % new_issue.key
        return new_issue.key


# transitions in Android board
class JiraTransition(object):
    TRANSITION = None
    RESOLUTION = None
    FINAL_STATUS = None

    @staticmethod
    def check_permission(issue):
        return True, None

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="issue key")

    def handle(self, namespace):
        ret = self(namespace.key)
        print ret

    def __call__(self, key):
        server = get_jira_server()
        issue = server.issue(key)

        if issue.fields.status.name == self.FINAL_STATUS:
            print 'status is up to date'
            return True

        permission, warning = self.check_permission(issue)
        if not permission:
            print YELLOW('WARNING: {0}'.format(warning))

        transitions = server.transitions(issue)
        transition_id = None
        for t in transitions:
            if t['name'] == self.TRANSITION:
                transition_id = t['id']

        if transition_id is None:
            valid = ", ".join([t['name'] for t in transitions])
            raise jira.exceptions.JIRAError(
                text='Not a valid transition: \'{0}\' choose one of [{1}]'.format(self.TRANSITION, valid))
        else:
            if self.RESOLUTION:
                server.transition_issue(key, transition_id, resolution={'id': self.RESOLUTION})
            else:
                server.transition_issue(key, transition_id)
            return True


class JiraTransitions(object):
    START_PROGRESS = 'Start Progress'
    STOP_PROGRESS = 'Stop Progress'
    SENT_TO_CODE_REVIEW = 'Send to Code Review'
    SEND_TO_QA = 'Send to QA'
    RESOLVE = 'Resolve'
    REOPEN = 'Reopen'
    LAND = 'Land'
    WRAP_RC = 'Wrap RC'
    RELEASE = 'Release to Store'
    REJECT = 'Reject'
    ABORT = 'Abort'


class JiraStatus(object):
    NEW = 'New'
    IN_PROGRESS = 'In Progress'
    IN_CODE_REVIEW = 'In Code Review'
    IN_QA = 'In QA'
    RESOLVED = 'Resolved'
    LANDED_IN_MASTER = 'In Master'
    IN_RC = 'In RC'
    REOPENED = 'Reopened'
    RELEASED = 'Released'
    ABORTED = 'Aborted'


class JiraResolution(object):
    FIXED = '1'
    WONT_FIX = '2'
    DUPLICATE = '3'
    INCOMPLETE = '4'
    CANNOT_REPRODUCE = '5'
    DONE = '10000'


def is_assignee(issue):
    assignee = issue.fields.assignee
    if not assignee:
        return False, "{0} isn't assigned to anyone".format(issue.key)
    elif get_jira_username() != assignee.name:
        return False, "{0} is assigned to {1}".format(issue.key, assignee.name)
    return True, None


def is_reviewer(issue):
    reviewer = getattr(issue.fields, CUSTOM_FIELD_REVIEWER)
    if not reviewer:
        return False, "there is no reviewer set for {0}".format(issue.key)
    elif get_jira_username() != reviewer.name:
        return False, "{0} is the reviewer for {1}".format(reviewer.name, issue.key)

    return True, None


class Reopen(JiraTransition):
    DOC = 'Reopen an issue'
    METHOD = 'reopen'
    TRANSITION = JiraTransitions.REOPEN
    FINAL_STATUS = JiraStatus.REOPENED


class Reject(JiraTransition):
    DOC = 'Reject an issue, returns to "In Progress"'
    METHOD = 'reject'
    TRANSITION = JiraTransitions.REJECT
    FINAL_STATUS = JiraStatus.IN_PROGRESS


class StartProgress(JiraTransition):
    DOC = 'Start working on an issue'
    METHOD = 'start-progress'
    TRANSITION = JiraTransitions.START_PROGRESS
    FINAL_STATUS = JiraStatus.IN_PROGRESS

    @staticmethod
    def check_permission(issue):
        return is_assignee(issue)


class StopProgress(JiraTransition):
    DOC = 'Stop working on an issue'
    METHOD = 'stop-progress'
    TRANSITION = JiraTransitions.STOP_PROGRESS
    FINAL_STATUS = JiraStatus.NEW

    @staticmethod
    def check_permission(issue):
        return is_assignee(issue)


class SendToCR(JiraTransition):
    DOC = 'Request code review'
    METHOD = 'request-cr'
    TRANSITION = JiraTransitions.SENT_TO_CODE_REVIEW
    FINAL_STATUS = JiraStatus.IN_CODE_REVIEW

    @staticmethod
    def check_permission(issue):
        return is_assignee(issue)

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="issue key")
        parser.add_argument("reviewer", help="user who will review your request")

    def handle(self, namespace):
        ret = self(namespace.key, namespace.reviewer)
        print ret

    def __call__(self, key, reviewer):
        set_reviewer(key, reviewer)
        return super(SendToCR, self).__call__(key)


class SendToQA(JiraTransition):
    METHOD = 'start-testing'
    DOC = 'Start testing on a feature branch'
    TRANSITION = JiraTransitions.SEND_TO_QA
    FINAL_STATUS = JiraStatus.IN_QA

    @staticmethod
    def check_permission(issue):
        return is_reviewer(issue)


class ResolveIssue(JiraTransition):
    DOC = 'Resolve an issue'
    METHOD = 'resolve-issue'
    TRANSITION = JiraTransitions.RESOLVE
    RESOLUTION = JiraResolution.FIXED
    FINAL_STATUS = JiraStatus.RESOLVED


class AbortIssue(JiraTransition):
    DOC = 'Abort an issue'
    METHOD = 'abort-issue'
    TRANSITION = JiraTransitions.ABORT
    RESOLUTION = JiraResolution.WONT_FIX
    FINAL_STATUS = JiraStatus.ABORTED


class LandIssue(JiraTransition):
    DOC = 'Mark issue as landed'
    METHOD = 'land'
    TRANSITION = JiraTransitions.LAND
    FINAL_STATUS = JiraStatus.LANDED_IN_MASTER


class MarkInRC(JiraTransition):
    DOC = 'Mark an issue as in RC'
    METHOD = 'in-rc'
    TRANSITION = JiraTransitions.WRAP_RC
    FINAL_STATUS = JiraStatus.IN_RC

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="issue key")
        parser.add_argument("pulse", help="pulse of RC")

    def handle(self, namespace):
        ret = self(namespace.key, namespace.pulse)
        print ret

    def __call__(self, key, pulse):
        set_pulse(key, pulse)
        return super(MarkInRC, self).__call__(key)


class GetInRC():
    DOC = 'Get all the issues currently in RC'
    METHOD = 'get-in-rc'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-p", dest='project', help="Jira project name", default='Android,Context,Discovery')

    def handle(self, namespace):
        ret = self(namespace.project)
        print ret

    @staticmethod
    def get_key(issue):
        return issue.key

    def __call__(self, project="Android,Context,Discovery"):
        jql = 'project in ({0}) and status="{1}"'.format(project, JiraStatus.IN_RC)
        Logger.info('Executing search with jql=' + jql)
        issues = search(jql)
        Logger.info('%d issues found' % len(issues))
        sorted(issues, key=self.get_key, reverse=True)
        issues_texts = [issue.fields.summary for issue in issues]
        return issues_texts


class MarkAsReleased(JiraTransition):
    DOC = 'Mark an issue as Released'
    METHOD = 'release'
    TRANSITION = JiraTransitions.RELEASE
    FINAL_STATUS = JiraStatus.RELEASED
    FINAL_STATUS = JiraStatus.RESOLVED

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="issue key")

    def handle(self, namespace):
        ret = self(namespace.key)
        print ret

    def __call__(self, key):
        return super(MarkAsReleased, self).__call__(key)

# /transitions

class CommentIssue(object):
    METHOD = 'comment-issue'
    DOC = 'Add a comment in an issue'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="issue key")
        parser.add_argument("comment", help="issue key")

    def handle(self, namespace):
        ret = self(namespace.key, namespace.comment)
        print ret

    def __call__(self, key, comment):
        server = get_jira_server()
        server.add_comment(key, comment)


class Search(object):
    METHOD = 'search'
    DOC = 'Search for issues using a JQL query'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("query", help="JQL query")

    def handle(self, namespace):
        ret = self(namespace.query)
        print ret

    def __call__(self, query):
        issues = get_jira_server().search_issues(query)
        return issues

class GetOpenIssues(object):
    METHOD = 'get_open_issues'
    DOC = 'Returns all open Jira issues of the user'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-user", help="user assigned to the issues")

    def handle(self, namespace):
        print self(namespace.user)

    def __call__(self, user=None):
        if not user:
            user = 'currentUser()'
        jql = 'assignee = {0} and Project in(Android,Discovery,Context) and Sprint is not EMPTY and status not in ' \
              '("In Master", "In RC", Closed, Released, Aborted, Graduated) order by status'.format(user)
        #Logger.info('Executing search with jql=' + jql)
        issues = search(jql)
        #Logger.info('%d issues found' % len(issues))
        return issues

class GetIssuesToReview(object):
    METHOD = 'get_issues_to_review'
    DOC = 'Returns all issues assigned to review by the user'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-user", help="user assigned as reviewer to the issues")

    def handle(self, namespace):
        print self(namespace.user)

    def __call__(self, user=None):
        if not user:
            user = 'currentUser()'
        jql = 'Reviewer = {0} and Project in(Android,Discovery,Context) and Sprint is not EMPTY ' \
              'and status = "In Code Review" '.format(user)
        #Logger.info('Executing search with jql=' + jql)
        issues = search(jql)
        #Logger.info('%d issues found' % len(issues))
        return issues


class GetBlockerBugsToDo(object):
    METHOD = 'get_blocker_bugs_to_do'
    DOC = 'Returns all issues in status todo which are blocker bugs'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        ret = self()

    def __call__(self):
        jql = 'project in (Android, Context, Discovery) AND issuetype = Bug AND priority = Blocker AND status = New'
        issues = search(jql)
        return issues
