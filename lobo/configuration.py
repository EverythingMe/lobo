import os
import pprint
from py2chainmap import ChainMap
import sys
import yaml
from logger import logger


__author__ = 'rotem'

ENV = 'env'
DEFAULT_ENV = 'default'

combined_config = None


class GetConfig(object):
    METHOD = 'get-config'
    DOC = 'Get a lobo configuration item'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="configuration key")

    def handle(self, namespace):
        print self(namespace.key)

    def __call__(self, key):
        global combined_config
        if not combined_config:
            local_config = load_config(False)

            if local_config:
                if local_config.has_key(DEFAULT_ENV):
                    default_local_config = local_config[DEFAULT_ENV]
                else:
                    default_local_config = dict()
                if local_config.has_key(local_config[ENV]):
                    env_local_config = local_config[local_config[ENV]]
                else:
                    env_local_config = dict()
            else:
                default_local_config = dict()
                env_local_config = dict()

            global_config = load_config(True)

            if global_config:
                default_global_config = global_config[DEFAULT_ENV]
                env_global_config = global_config[global_config[ENV]]
            else:
                return None

            combined_config = ChainMap(env_local_config, default_local_config, env_global_config, default_global_config)

        key_splits = str.split(key, '.')
        value = None
        endpoint = combined_config.get(key_splits[0])

        if endpoint:
            value = endpoint.get(key_splits[1])
        return value


class Config(object):
    METHOD = 'config'
    DOC = 'set a configuration parameter'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("key", help="pattern: '{endpoint}.{key}'")
        parser.add_argument("value", help="it's a value!")
        parser.add_argument("--global", help="global config will be saved at ~/.loboconfig, local will be saved in current dir",
                            default=False,
                            action="store_true",
                            dest='isglobal')

    def handle(self, namespace):
        self(namespace.key, namespace.value, namespace.isglobal)

    def __call__(self, key, value, isglobal):
        splits = str.split(key, '.')
        config = load_config(isglobal)
        config.setdefault(ENV, DEFAULT_ENV)
        config.setdefault(config[ENV], {}).setdefault(splits[0], {})[splits[1]] = value
        dump_config(config, isglobal)


class SetEnv(object):
    METHOD = 'setenv'
    DOC = 'Set lobo environemnt (for multiple endpoint configurations)'

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("env", help="environment name")
        parser.add_argument("--global", help="global config will be saved at ~/.loboconfig, local will be saved in current dir",
                            default=False,
                            action="store_true",
                            dest='isglobal')

    def handle(self, namespace):
        self(namespace.env, namespace.isglobal)
        print "lobo env set to {} in {} loboconfig".format(namespace.env, 'global' if namespace.isglobal else 'local')

    def __call__(self, env, isglobal):

        config = load_config(isglobal)
        config[ENV] = env

        # set up an empty environment if configuration file if doesn't exist
        if not config.has_key(DEFAULT_ENV):
            config[DEFAULT_ENV] = dict()

        if not config.has_key(env):
            config[env] = dict()

        dump_config(config, isglobal)


def get_config_or_default(config_key, default=None):
    param = get_config(config_key)
    if param is None:
        return default
    else:
        return param

def get_config_file_path(isglobal):
    if isglobal:
        return os.path.expanduser("~/.loboconfig")
    else:
        return ".loboconfig"


def load_config(isglobal):
    try:
        with open(get_config_file_path(isglobal), 'r') as stream:
            config = yaml.load(stream)
    except (IOError, yaml.scanner.ScannerError):
        config = dict()

    if not config:
        config = dict()

    return config


def dump_config(config, isglobal):
    with open(get_config_file_path(isglobal), 'w') as stream:
        ret = stream.write(yaml.dump(config))
    return ret


def handle_missing_config(message, config_key, value_pattern='value'):
    logger.error(message)
    logger.error('\tlobo config --global {} {}'.format(config_key, value_pattern))
    sys.exit(2)


def get_running_config():
    if combined_config:
        return dict(combined_config)
    else:
        return dict()

setenv = SetEnv()
config = Config()
get_config = GetConfig()
