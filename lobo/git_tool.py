import datetime
import os
import subprocess
from multiprocessing.pool import ThreadPool
import sys
import warnings
import modules
from common import cd, TEMP_DIR, RED, BOLD, UNDERLINE, printp, FILLER
import configuration

from toolkit_base import ToolkitBase
from collections import namedtuple

try:
    subprocess.Popen(['git'], stdout=subprocess.PIPE)
except OSError as e:
    print RED('FATAL: git not found in path, exiting.')
    exit(1)

log_file = os.path.join(TEMP_DIR, 'lobo.log')
out = file(log_file, "w")

giterr = None
verbose = False


def gitcmd(command, cwd='.', git=True):
    global giterr
    global verbose

    if type(command) == list:
        parts = command
    else:
        parts = command.split()
    if git:
        parts = ["git"] + parts

    msg = ">> %s" % " ".join(parts)
    if verbose: print msg
    out.write("%s\n" % msg)
    out.flush()

    p = subprocess.Popen(parts, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ret, err = p.communicate()

    ret = ret.rstrip()
    err = err.rstrip()

    if verbose:
        print ret + err
    out.write(ret + err + "\n")
    out.flush()

    errorcode = p.returncode
    if errorcode == 0:
        giterr = None
        return ret, None
    else:
        giterr = ret + err
        return None, giterr


GitStatus = namedtuple("GitStatus", "merge staged modified untracked conflict")


def status():
    ret, err = gitcmd(['status', '--porcelain', '--ignore-submodules=dirty'])
    if ret is None:
        print err
        return None
    ret = ret.split('\n')
    ret = [(x[:2], x[3:]) for x in ret if len(x) >= 4]
    merge = False
    untracked = []
    modified = []
    staged = []
    conflict = []
    for kind, filename in ret:
        if filename[0] == '"':
            filename = eval(filename)
        if kind == '??':
            untracked.append(filename)
        if kind[1] in ['M', 'D']:
            modified.append(filename)
        if kind[1] in ['M', 'D', ' '] and kind[0] in ['M', 'A', 'R', 'C', 'D']:
            staged.append(filename)
        if kind in ['DD', 'DU', 'AA', 'AU', 'UA', 'UD', 'UU']:
            conflict.append(filename)
            merge = True
    return GitStatus(merge, staged, modified, untracked, conflict)


def get_author():
    """
    :return: author name of last commit
    """
    author, _ = gitcmd(['--no-pager', 'show', '-s', "--format='%an <%ae>''"])
    return author

def fetch(branches=None):
    if branches is not None:
        return gitcmd(['fetch', 'origin']+branches+['--no-recurse-submodules'])
    else:
        return gitcmd(['fetch', '--no-recurse-submodules'])


def is_merged_with(branchname, ref="HEAD"):
    # ref contains branchname
    ret, _ = gitcmd(['branch','-r', '--merged',ref])
    if ret is None:
        print "No such branch {0}?".format(branchname)
        ret = []
    else:
        ret = set(x[2:].strip() for x in ret.split('\n'))
    return branchname in ret


def get_all_branches(remote=True):
    if remote:
        ret, _ = gitcmd(['branch', '-r'])
        ret = set(x[2:].strip() for x in ret.split('\n'))
        ret = [x.split('/', 1)[1] for x in ret if x.startswith('origin/')]
    else:
        ret, _ = gitcmd(['branch'])
        ret = set(x[2:].strip() for x in ret.split('\n'))
    return list(ret)


def is_remote_branch(branchname):
    return branchname in get_all_branches(remote=True)


def is_tag(tagname):
    ret, err = gitcmd("tag -l %s" % tagname)
    return ret.strip() == tagname


def is_branch_diverged(branchname, ref='HEAD'):
    head, _ = gitcmd(['rev-parse', 'HEAD'])
    ref, _ = gitcmd(['rev-parse', branchname])
    return head != ref


def get_git_dir():
    git_dir, _ = gitcmd('rev-parse --git-dir')
    return git_dir


def is_at_root():
    expected = os.environ.get('GIT_DIR', '.git')
    git_dir = get_git_dir()
    return git_dir == expected


def get_rebase_step():
    try:
        return file(os.path.join(get_git_dir(), 'rebase-merge', 'msgnum')).read()
    except:
        try:
            return file(os.path.join(get_git_dir(), 'rebase-apply', 'next')).read()
        except:
            return None


def get_submodules():
    ret, err = gitcmd(['submodule', 'status'])
    if err is not None:
        return None
    subs = []
    for l in ret.split('\n'):
        if l != "":
            s = l.split()
            if len(s) > 1:
                module_name = s[1]
                if not modules.is_module_excluded(module_name):
                    subs.append(module_name)
            else:
                print "Failed to get submodules, offending line is %r" % l
                return None
    return subs


def get_uninited_submodules():
    """
    Check if there's a uninitialized submodule, returns a list of uninitialized modules.
    An empty list means all modules are initialized
    """
    ret = gitcmd('submodule status')
    modules = ret[0].split('\n')

    # Each SHA-1 will be prefixed with:
    # - if the submodule is not initialized
    # + if the currently checked out submodule commit does not match the SHA-1 found in the index of the containing repository
    # U if the submodule has merge conflicts.
    uninited_modules = [s for s in modules if s.startswith('-')]

    return uninited_modules


class GitConfig(object):
    METHOD = 'git-config'
    DOC = 'Get a git configuration item'

    warnings.warn("The 'git-tool.GetConfig' class is deprecated, use configuration.GetConfig, "
                  "use this ONLY for git configuration querying", DeprecationWarning, stacklevel=2)

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="configuration key")

    def handle(self, namespace):
        print self(namespace.key)

    def __call__(self, key):

        value, _ = gitcmd("config --get %s" % key)
        if value is None or value == "":
            return None

        return value


class TreeRoot(object):
    METHOD = 'tree-root'
    DOC = 'Get the root of the current git repo'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        ret, _ = gitcmd('rev-parse --show-toplevel')
        return ret


class GetRepo(object):
    METHOD = 'get-repo'
    DOC = 'Get the name of the current repo'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        url = git_config('remote.origin.url')
        url = url.split(':')[-1]
        if url.endswith('.git'):
            url = url[:-4]
        return url


class CompareBranches(object):
    METHOD = 'compare-branches'
    DOC = 'Get a list of commits from branch A to branch B'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("src", help="source branch name")
        parser.add_argument("dst", help="target branch name")

    def handle(self, namespace):
        print "\n".join(self(namespace.src, namespace.dst))

    def __call__(self, src, dst):
        module = os.path.basename(os.path.abspath('.'))
        cmd = r'log ' + src + '..' + dst + ' --no-merges --format="format:%ct ' + module + ' | %cr | %h: %s (%an)"'
        ret, _ = gitcmd(cmd).split("\n")
        return ret


class GetRemote(object):
    METHOD = 'get-remote'
    DOC = 'Get the target of a specific remote'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("remote", help="remote name to fetch")

    def handle(self, namespace):
        print self(namespace.remote)

    def __call__(self, remote):
        remotes, _ = gitcmd("remote -v")
        remotes = [l.split() for l in remotes.split('\n')]
        remotes = [l for l in remotes if l[0] == remote and l[2] == "(push)"][0][1]
        return remotes


class RecurseSubmodules(object):
    METHOD = 'recurse-submodules'
    DOC = 'Run a command recursively on all submodules'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-p", help="post order traversal: start with leaves and go up to the top",
                            action="store_true", dest="post_traversal")
        parser.add_argument("cmd", help="command to perform")

    def handle(self, namespace):
        for submodule, ret in self(namespace.cmd, namespace.post_traversal):
            ret, err = ret
            print submodule
            print '-' * len(submodule)
            print ret if ret is not None else "ERROR:"
            print err if err is not None else ""

    def all_submodules(self, cwd='.', root_first=True):
        ret = cwd
        if root_first:
            yield ret
        subs, _ = gitcmd('submodule status', cwd)
        subs = [l.split() for l in subs.split('\n') if l != ""]
        for l in subs:
            if len(l) > 1:
                fullpath = os.path.join(cwd, l[1])
                for x in self.all_submodules(fullpath, root_first):
                    yield x
            else:
                print "BAD SUBMODULE: %s" % " ".join(l)
        if not root_first:
            yield ret

    def __call__(self, cmd, post_traversal=False, concurrent=False):
        for submodule in self.all_submodules(root_first=not post_traversal):
            with cd(submodule):
                if modules.is_module_excluded(submodule):
                    continue

                pool = ThreadPool(processes=4) if concurrent else None
                if callable(cmd):
                    if concurrent:
                        o = pool.apply_async(cmd).get()
                    else:
                        o = cmd()
                else:
                    if concurrent:
                        o = pool.apply_async(gitcmd, (cmd, False)).get()
                    else:
                        o = gitcmd(cmd, git=False)
            yield submodule, o


class NewBranch(object):
    METHOD = 'new-branch'
    DOC = 'Create and switch to a new branch'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("branchname", help="name of the branch to create")
        parser.add_argument("-o", help="origin of the branch to create", dest="origin", default="HEAD")

    def handle(self, namespace):
        print self(namespace.branchname, namespace.origin)

    def __call__(self, branchname, origin="HEAD"):
        ret, err = gitcmd('branch %s %s' % (branchname, origin))
        if err is not None:
            return ret, err
        ret, err = gitcmd('checkout %s' % branchname)
        return ret, err


class Push(object):
    METHOD = 'push'
    DOC = 'Push the current branch (or other, if specified) to origin'
    FORCE = False

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-b", help="name of the branch to push", dest="branchname",
                            default=None)

    def handle(self, namespace):
        print self(namespace.branchname)

    def __call__(self, branch=None, bypass_hooks=True):
        if branch is None:
            branch = get_current_branch()
        args = ['push']
        if self.FORCE:
            args.append('-f')
        if bypass_hooks:
            args.append('--no-verify')
        args.extend(['origin', '{0}:{0}'.format(branch)])
        return gitcmd(args)


class ForcePush(Push):
    METHOD = 'force-push'
    DOC = 'Force push the current branch (or other, if specified) to origin'
    FORCE = True


class GetCurrentBranch(object):
    METHOD = 'get-current-branch'
    DOC = 'get the name of the current branch'

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print self()

    def __call__(self):
        ret, err = gitcmd('rev-parse --abbrev-ref HEAD')
        return ret if ret != 'HEAD' else None


class CheckoutRemote(object):
    METHOD = 'checkout-remote'
    DOC = """Check out a remote branch or tag;
for branches: create a local branch if needed and reset that branch''s state to match its remote counterpart"""

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("branchname", help="name of branch/tag to checkout")
        parser.add_argument("-k", help="kind: branch / tag. If unspecified will try to guess",
                            choices=['tag', 'branch'], dest='kind', default=None)

    def handle(self, namespace):
        print self(namespace.branchname, namespace.kind)

    def __call__(self, target, kind):
        if kind is None:
            if not is_tag(target):
                kind = "branch"
            else:
                kind = "tag"
        ret, err = gitcmd("rev-parse HEAD")
        if ret is not None:
            gitcmd("checkout %s" % ret)
        else:
            return ret, err
        if kind == "branch":
            # not a tag
            ret, err = gitcmd("branch -f {0} origin/{0}".format(target))
            if err is not None:
                return ret, err
            ret, err = gitcmd('checkout -B {0} --track origin/{0}'.format(target))
            if err is not None:
                return ret, err
        elif kind == "tag":
            ret, err = gitcmd('checkout -B {0}'.format(target))
            if err is not None:
                print "FAILED to check out tag {0}".format(target)
                print err.replace('\n', '\n\t')
                return ret, err
        else:
            return None, "Unknown kind %s" % kind

        ret, err = gitcmd('submodule update --init')
        if err is not None:
            return ret, err
        return None, None


class RebaseIfNeeded(object):
    METHOD = 'rebase-if-needed'
    DOC = "Rebase this branch if needed, if we're in the middle of a rebase then continue it"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("branchname", help="name of the branch to rebase from")

    def handle(self, namespace):
        print self(namespace.branchname)

    def __call__(self, branchname):
        step = get_rebase_step()
        if step is None and is_merged_with('origin/%s' % branchname):
            # we're based on master, no need to do anything
            return None, None
        else:
            if step is None:
                ret, err = gitcmd(['rebase', '--autostash', 'origin/%s' % branchname])
            else:
                ret, err = gitcmd(['rebase', '--continue'])
            submodules = None
            while err is not None:
                gitstatus = status()
                if submodules is None:
                    submodules = get_submodules()
                    if submodules is None:
                        return ret, err
                non_subs = set(gitstatus.conflict) - set(submodules)
                if len(non_subs) > 0:
                    print "Conflict in non submodules %r" % non_subs
                    return ret, err
                for sub in gitstatus.conflict:
                    print "Adding %s" % sub
                    _ret, _err = gitcmd(['add', sub])
                    if _err is not None:
                        return ret, err
                ret, err = gitcmd(['rebase', '--continue'])
                if err is not None:
                    if get_rebase_step() == step:
                        return ret, err
                step = get_rebase_step()
            return ret, err


class Squash(object):
    METHOD = 'squash'
    DOC = "Squash this branch commits with master (we're already supposed to be rebased)"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("message", help="message to use in unified commit")

    def handle(self, namespace):
        self(namespace.message)

    def __call__(self, message, author=None):
        head, _ = gitcmd(['rev-parse', 'HEAD'])
        ret = "%s: Squashed, HEAD was at %s" % (get_repo(), head)
        # I used the script from http://rebaseandsqua.sh/
        # Get the current branch name.
        branch, _ = gitcmd(['rev-parse', '--abbrev-ref', 'HEAD'])
        # Get author of last commit
        if author is None:
            author = get_author()
        # Determine the commit at which the current branch diverged.
        ancestor, _ = gitcmd(['merge-base', 'origin/master', 'HEAD'])
        # Stash any uncommited, changed files.
        gitcmd(['stash', '--all'])
        # Revert the branch back to the ancestor SHA.
        gitcmd(['reset', '--hard', ancestor])
        # Squash all commits from ancestor to previous SHA.
        gitcmd(['merge', '-q', '--squash', 'HEAD@{1}'])
        # Perform the commit, prompting for the message.
        # change the new squashed commit's author to the original author no matter who squashes it)
        gitcmd(['commit', '-q', '-m', message, '--author', author])
        # Restore previous uncommited changes, if any.
        gitcmd(['stash', 'pop'])
        return ret, None


class FixRefs(object):
    METHOD = 'fix-refs'
    DOC = "Fix submodule references recursively"

    @classmethod
    def setup_argparser(cls, parser):
        pass

    def handle(self, namespace):
        print "%r" % list(self())

    def __call__(self):

        def fix_refs():
            subs = get_submodules()
            if subs is None:
                return None, "no submodules?"
            gitstatus = status()
            if gitstatus is None:
                return None, "no status?"
            added = []
            for sub in subs:
                if sub in gitstatus.modified:
                    gitcmd(['add', sub])
                    added.append(sub)
            if len(added) > 0:
                print "commiting %r" % added
                return gitcmd(['commit', '-nm', 'lobo: Updating submodule references'])
            return None, None

        return recurse_submodules(fix_refs, post_traversal=True)


class Cleanup(object):
    METHOD = 'cleanup'
    DOC = 'Delete merged branches across the project. Will only delete merged branches older than 45 days'

    PROTECTED = ['master', 'origin/master', '* master', '*', '->', 'HEAD', 'origin/HEAD']
    DISCARD_AGE_DAYS = 45

    dry_run = False
    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("-r", help="also run on remotes", action="store_true", dest="remote")
        parser.add_argument("-n", help="dry run", action="store_true", dest="dry_run")

    def handle(self, namespace):
        self.dry_run = namespace.dry_run
        self.remote = namespace.remote
        if not self.dry_run:
            input = raw_input(RED("Are you sure you want to run cleanup? "
                                    "(It is advised that you use '-n' to initiate a dry run first) [y/N]"))
            if input not in ['Y', 'y']:
                sys.exit(0)

        self()

    def __call__(self):
        print resolve_errors(recurse_submodules(self.cleanup), title='Running git-tool cleanup...\n')

    def cleanup(self):
        fetch()
        local_deleted_branches = self.delete_merged_local()
        local = BOLD('\nDeleted {} local branches:\n{}\n'.format(len(local_deleted_branches), '\n'.join(local_deleted_branches)))

        if self.remote:
            remote_deleted_branches = self.delete_merged_remote()
            remote = BOLD('\nDeleted {} remote branches:\n{}\n'.format(len(remote_deleted_branches), '\n'.join(remote_deleted_branches)))
            return '{}{}'.format(local, remote), None

        return '{}'.format(local), None

    def delete_merged_local(self):
        printp('Deleting merged local branches...')
        branches, _ = gitcmd(['branch', '--no-color', '--merged', 'origin/master'])
        branch_list = branches.split('\n')
        branch_list = map(str.strip, branch_list)
        branch_list = [x.strip() for x in branch_list if (x not in self.PROTECTED and not '*' in x)]
        deleted_branches = list()
        for branch in branch_list:
            if self.should_delete(branch):
                deleted_branches.append(branch)
                if not self.dry_run:
                    gitcmd(['branch', '-d', branch])

        return deleted_branches

    def delete_merged_remote(self):
        printp("Deleting local refs to remote branches that don't exist...")
        gitcmd(['remote', 'prune', 'origin'])
        printp('Deleting merged remote branches...')
        branches, _ = gitcmd(['branch', '-r', '--no-color', '--merged', 'origin/master'])
        branch_list = branches.split()
        branch_list = map(str.strip, branch_list)
        if branch_list:
            branch_list = [x.strip() for x in branch_list if (x not in self.PROTECTED and not '*' in x)]

        deleted_branches = list()
        trimmed_branches = list()
        for branch in branch_list:
            if self.should_delete(branch):
                deleted_branches.append(branch)
                split = branch.split('/')
                trimmed_branches.append(split[1])

        if not self.dry_run:
            gitcmd(['push', 'origin', '--delete'] + trimmed_branches)
        return deleted_branches

    def should_delete(self, branch):
        split = branch.split('/')
        branch_name = branch if len(split) < 2 else split[1]
        branch_date = self.get_changed_date(branch)
        branch_age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(branch_date)).days

        return branch_age > self.DISCARD_AGE_DAYS and \
               not branch_name.startswith('rc')

    def get_changed_date(self, branch):
        if 'detached' in branch:
            print branch
        branch_date_string = gitcmd(['show', '-1', '--pretty=%ct', branch])[0]
        changed_date = int(branch_date_string.split('\n')[0])
        return changed_date

class Tag(object):
    METHOD = 'tag'
    DOC = 'Add git tags for all modules'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("tag_name", help="tag")
        parser.add_argument("-d", help="delete tag", action="store_true", dest="delete_flag")

    def handle(self, namespace):
        self(namespace.tag_name, namespace.delete_flag)

    def __call__(self, tag_name, delete_flag):
        def tag():
            if delete_flag:
                gitcmd(['tag', '-d', tag_name])
                ret = gitcmd(['push', '--delete', 'origin', tag_name])
            else:
                gitcmd(['tag', tag_name])
                ret = push(tag_name)

            return ret

        return resolve_errors(recurse_submodules(tag), 'Pushing tag...')


def resolve_errors(gen, title=None, errorMsg=None, errorHandling=None):
    printed = False
    error = False
    if title is not None:
        print BOLD(title)
    for submodule, ret in gen:
        if ret[1] is not None:
            printed = True
            error = True
            print "%s:%s\n%s\n%s\n" % (
            UNDERLINE("ERROR for " + submodule), FILLER, ret[0] + "\n" if ret[0] is not None else "", RED(ret[1]))
        else:
            if ret[0] is not None and len(ret[0].strip()) > 0:
                printed = True
                print "%s:%s\n%s" % (UNDERLINE(submodule), FILLER, ret[0])
            else:
                printp(submodule)
    if not printed:
        print "ALL DONE" + FILLER
    if error:
        if errorMsg is not None:
            print RED(errorMsg)
        if errorHandling is not None and callable(errorHandling):
            errorHandling()
    return not error

def git_tool_entry():
    parser = ToolkitBase([TreeRoot, CompareBranches, RecurseSubmodules,
                          GetRemote, NewBranch, CheckoutRemote, GetCurrentBranch,
                          RebaseIfNeeded, Squash, Push, FixRefs, GetRepo, Tag, Cleanup])
    parser.parse()

tree_root = TreeRoot()
compare_branches = CompareBranches()
recurse_submodules = RecurseSubmodules()
get_remote = GetRemote()
new_branch = NewBranch()
checkout_remote = CheckoutRemote()
get_current_branch = GetCurrentBranch()
rebase_if_needed = RebaseIfNeeded()
squash = Squash()
push = Push()
forcepush = ForcePush()
fix_refs = FixRefs()
get_repo = GetRepo()
cleanup = Cleanup()
git_config = GitConfig()
tag = Tag()

verbose = configuration.get_config('git-tool.verbose')

if __name__ == "__main__":
    git_tool_entry()
