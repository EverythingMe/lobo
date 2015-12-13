import sys,os

import jenkinsapi

from toolkit_base import ToolkitBase
from configuration import get_config, handle_missing_config

from jenkinsapi.utils.requester import Requester
import requests

requests.packages.urllib3.disable_warnings()
jenkins_user = os.environ.get('jenkins_user')
jenkins_token = os.environ.get('jenkins_token')


def get_default_job():
    return get_config("jenkins.default-job")


def get_default_server():
    return get_config("jenkins.default-server")


def get_jenkins_user():
    global jenkins_user
    if jenkins_user:
        return jenkins_user

    jenkins_user = get_config_or_default("jenkins.user")
    if jenkins_user:
        return jenkins_user
    else:
        handle_missing_config("Please set your Jenkins user name:", "jenkins.user", '<username@domain>')


def get_jenkins_token():
    global jenkins_token
    if jenkins_token:
        return jenkins_token
    jenkins_token = get_config_or_default("jenkins.token")
    if jenkins_token:
        return jenkins_token
    else:
        handle_missing_config("Please set your Jenkins private API token (you can grab it from here {}/user/{}/configure):".format(get_default_server(), get_jenkins_user()),
                                            'jenkins.token')


def get_build_path(build_number):
    return '/'.join((get_default_server(), 'job', get_default_job(), build_number))


instance = None
def get_instance():
    global instance
    if instance is None:
        instance = jenkinsapi.jenkins.Jenkins(get_default_server(), get_jenkins_user(), get_jenkins_token(),
                                              requester=Requester(get_jenkins_user(), get_jenkins_token(), baseurl=get_default_server(), ssl_verify=False))
    return instance


class RunBuild(object):
    METHOD = "run-build"
    DOC = "Builds the Product"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("branch", help="branch to build")
        parser.add_argument("--assignee", help="assignee will be sent as a parameter to jenkins for post build actions", dest="assignee")
        parser.add_argument("-b", help="block until the build is finished", action="store_true", dest="block")


    def handle(self, namespace):
        print "BUILDNO=%s SUCCESS=%s" % self(namespace.branch, ["Debug"], namespace.block, assignee=namespace.assignee, split_apks=namespace.split_apks, post_build_task=namespace.post_build_task)

    def __call__(self, branch, block, gitlab_token=None, assignee=None):
        J = get_instance()
        job = J.get_job(get_default_job())
        inv = job.invoke(build_params={"BRANCH": branch, "GITLAB_TOKEN": gitlab_token, "ASSIGNEE": assignee})

        if block:
            print "Waiting for job to leave the queue..."
        else:
            print "Job started, you'll get some notified once it's done..."

        inv.block_until_building()
        build_no = inv.get_build_number()
        print "build#=%s" % build_no
        build = inv.get_build()
        success = None
        if block:
            while build.is_running():
                try:
                    inv.block_until_complete(0)
                except jenkinsapi.custom_exceptions.TimeOut:
                    print ".",
                    sys.stdout.flush()
                    continue
            print
            success = build.get_status() != 'FAILURE'
            consolefn = "build.log"
            file(consolefn, 'w').write(build.get_console())
            print "Build completed with status %s, console output was saved to %s" % (build.get_status(), consolefn)
        return build_no, success


class TestConnection(object):
    METHOD = "test-connection"
    DOC = "Test the jenkins server connection"

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        J = get_instance()
        job = J.get_job(get_default_job())
        lgb = job.get_last_good_build()
        rev = lgb.get_revision()
        print '{}, job: {}, last good build: {}, last good build revision: {}'.format(J, job, lgb, rev)
        return rev is not None
