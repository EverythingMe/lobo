import yaml

__author__ = 'rotem'


def load_modules_config():
    try:
        with open(".lobomodules", 'r') as stream:
            modules = yaml.load(stream)
    except (IOError, yaml.scanner.ScannerError):
        modules = dict()

    if not modules:
        modules = dict()

    return modules


def is_module_excluded(module_name):
    global modules
    stripped = module_name.strip("./")
    if not modules.has_key("exclude"):
        return False
    return stripped in modules["exclude"]


modules = load_modules_config()
