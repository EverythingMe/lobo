import sys
import argparse


class ToolkitBase(object):
    def __init__(self, commands):
        self.argparser = argparse.ArgumentParser(sys.argv[0])
        self.command_map = {}
        subparsers = self.argparser.add_subparsers(title="command", help='command to use', dest='_command')

        for cmd in commands:
            self.command_map[cmd.METHOD] = cmd
            cmd_parser = subparsers.add_parser(cmd.METHOD, help=cmd.DOC)
            cmd.setup_argparser(cmd_parser)

    def parse(self):
        namespace = self.argparser.parse_args()
        cmd = self.command_map[namespace._command]
        cmd().handle(namespace)
