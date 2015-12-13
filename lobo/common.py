import os, sys
from contextlib import contextmanager
import tempfile

TEMP_DIR = tempfile.gettempdir()

@contextmanager
def cd(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)

def BOLD(x):
    return '\033[1m%s\033[0m' % x


def UNDERLINE(x):
    return '\033[4m%s\033[24m' % x


def RED(x):
    return '\033[31m%s\033[39m' % x


def YELLOW(x):
    return '\033[33m%s\033[39m' % x


def compose(*functions):
    def inner(arg):
        for f in reversed(functions):
            arg = f(arg)
        return arg

    return inner

FILLER = 60 * " "
def printp(message):
    """
    Print progress message. The message will override currently printed line
    :return:
    """
    print '{}{}\r'.format(message, FILLER),
    sys.stdout.flush()