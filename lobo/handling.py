import sys
from flow_toolkit.common import RED

__author__ = 'rotem'


"""
This is a temporary solution for handling custom errors in resolve_errors, it's ugly,
but it's safe, we'll design a a better solution asap
"""

FETCH_HANDLING = {
    "title": "Fetching...",
    "errorMsg": "Let's make sure we have gitlab connectivity first, alright?",
    "errorHandling": lambda: sys.exit(1)
}

REBASE_HANDLING = {
    "title": "Rebasing...",
    "errorMsg": "Please complete the rebase first (you can re-run this when you're ready)",
    "errorHandling": lambda: sys.exit(1)
}

MERGE_HANDLING = {
    "title": "Merging...",
    "errorMsg": "Merge failed, is this branch rebased ?",
    "errorHandling": lambda: sys.exit(1)
}


def exit_with_confirmation(msg):
    def inner():
        ignore_errors = raw_input(msg)
        if ignore_errors not in ['Y', 'y']:
            sys.exit(1)
    return inner

APPROVAL_HANDLING = {
    "title": "Getting approvals...",
    "errorHandling": exit_with_confirmation(RED("There were errors, are you sure you want to continue with landing? [y/N]"))
}

