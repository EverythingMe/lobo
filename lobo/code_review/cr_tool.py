from lobo import configuration, nop_driver

cr_tool = configuration.get_config('driver:cr')
if cr_tool == 'gitlab':
    import gitlab_tool as cr_driver
else:
    cr_driver = nop_driver.NopDriver()


class SignedCommentMR(object):
    METHOD = 'signed-comment-mr'
    DOC = 'Add a signed comment to an mr'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="branch name")
        parser.add_argument("comment", help="comment")

    def handle(self, namespace):
        self(namespace.repo, namespace.branch, namespace.comment)

    def __call__(self, repo, sourceBranch, comment):
        ts = int(time.time())
        key = "%08x|%s" % (ts, comment)
        digest = md5.md5(key).hexdigest()[:4]
        comment = digest + key
        return add_comment_to_mr(repo, sourceBranch, comment)


class ApproveBase(object):
    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="branch name")

    @classmethod
    def filter_message(cls, message):
        return message.startswith('PASSED %s' % cls.WHAT)

    def handle(self, namespace):
        self(namespace.repo, namespace.branch)

    def __call__(self, repo, sourceBranch, extra=''):
        return add_signed_comment_to_mr(repo, sourceBranch, "PASSED %s%s" % (self.WHAT, extra))


class ApproveQA(ApproveBase):
    METHOD = 'approve-qa'
    DOC = 'Mark an MR as QA approved'
    WHAT = 'QA'


class ApproveCR(ApproveBase):
    METHOD = 'approve-cr'
    DOC = 'Mark an MR as Code Reviewed'
    WHAT = 'CODE REVIEW'


class ApproveUITests(ApproveBase):
    METHOD = 'approve-ui-tests'
    DOC = 'Mark an MR passed UI tests'
    WHAT = 'UI TESTS'


class ApproveProbeTests(ApproveBase):
    METHOD = 'approve-probe-tests'
    DOC = 'Mark an MR passed probe tests'
    WHAT = 'PROBE TESTS'


class ApproveBuild(ApproveBase):
    METHOD = 'approve-build'
    DOC = 'Mark an MR passed build & unit tests'
    WHAT = 'BUILD'

    def __call__(self, repo, sourceBranch, build_no=None):
        super(ApproveBuild, self).__call__(repo, sourceBranch, " #%s" % build_no if build_no is not None else '')


class GetApprovals(object):
    METHOD = 'get-approvals'
    DOC = 'Return a list of all approvals on an MR'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("repo", help="repository")
        parser.add_argument("branch", help="branch name")

    def handle(self, namespace):
        for approval in self(namespace.repo, namespace.branch):
            print "%s:%s by %s" % (approval['created_at'], approval['body'], approval['author']['name'])

    def __call__(self, repo, sourceBranch):
        gl = get_instance()
        project = get_project(repo)
        if not project:
            raise StopIteration
        mr = get_open_mr(project, sourceBranch)
        if mr is None:
            raise StopIteration
        comments = gl.getmergerequestwallnotes(project['id'], mr['id'])
        for comment in comments:
            note = comment['body']
            try:
                digest = md5.md5(note[4:]).hexdigest()[:4]
            except:
                continue
            if note[:4] == digest:
                try:
                    ts1 = int(note[4:12], 16)
                    ts1 = datetime.datetime.utcfromtimestamp(ts1)
                    ts2 = dateutil.parser.parse(comment['created_at'])
                    diff = abs((ts2.replace(tzinfo=None) - ts1).total_seconds())
                    if diff < 600:  # some leeway for non-exact clocks
                        comment['body'] = note[13:]
                        yield comment
                except Exception, e:
                    pass

add_comment_to_mr = cr_driver.CommentMR()
create_mr = cr_driver.CreateMR()
close_mr = cr_driver.CloseMR()
get_file = cr_driver.GetFile()
protect_branch = cr_driver.ProtectBranch()
test_connection = cr_driver.TestConnection()

add_signed_comment_to_mr = SignedCommentMR()
approve_qa = ApproveQA()
approve_cr = ApproveCR()
approve_ui_tests = ApproveUITests()
approve_probe_tests = ApproveProbeTests()
approve_build = ApproveBuild()
get_signed_comments = GetApprovals()

def tool_entry():
    parser = ToolkitBase(
        [cr_driver.CommentMR, cr_driver.CreateMR, cr_driver.etFile, cr_driver.CloseMR, cr_driver.ProtectBranch, cr_driver.TestConnection,
         SignedCommentMR, ApproveQA, ApproveCR, ApproveUITests, ApproveProbeTests, GetApprovals,
        ])
    parser.parse()

if __name__ == "__main__":
    tool_entry()
