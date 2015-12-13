import re
import sys
from toolkit_base import ToolkitBase

__author__ = 'rotem'

# scope (major) version
SCOPE = 3

ABIS = {
    0: 'universal',
    1: 'armeabi',
    2: 'armeabi-v7a',
    3: 'x86'
}

DENSITIES = {
    0: 'all',
    1: 'mdpi',
    2: 'hdpi',
    3: 'xhdpi',
    4: 'xxhdpi',
}

SCREEN_VARIANTS = {
    0: 'phone/combined',
    1: 'tablet',
}


class CalcVersionName(object):
    METHOD = "c2n"
    DOC = "Calculate version name from version code"


    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument('version_code', type=int, help='version code to be translated')

    def handle(self, namespace):
        return self(namespace.version_code)

    def __call__(self, version_code):
        revision = (version_code & 0xfffc0000) >> AbiSplitsVersion.REVISION_OFFSET

        if revision < ScreenAbiDensitySplitsVersion.VALID_FROM_REVISION:
            return AbiSplitsVersion().code_to_name(version_code)
        else:
            return ScreenAbiDensitySplitsVersion().code_to_name(version_code)


class CalcVersionCode(object):
    METHOD = "n2c"
    DOC = "Calculate version code from version name"

    @classmethod
    def setup_argparser(cls, parser):
        parser.add_argument("version_name", help="version name to be translated")


    def handle(self, namespace):
        version_code = self(namespace.version_name)
        print '{version_code}'.format(version_code=version_code)

    def __call__(self, version_name):
        return ScreenAbiDensitySplitsVersion().name_to_code(version_name)


class AbiSplitsVersion():
    """
    APK splits only by abis  (older version)
    """
    VALID_FROM_REVISION = 0

    REVISION_OFFSET = 18
    BUILD_NO_OFFSET = 4
    ABI_CODE_OFFSET = 0

    def __init__(self):
        pass

    def code_to_name(self, version_code):
        revision = (version_code & 0xfffc0000) >> self.REVISION_OFFSET
        build_no = (version_code & 0x0003fff0) >> self.BUILD_NO_OFFSET
        abi_code = version_code & 0xf

        version_name = '{scope}.{revision}.{build_no}'.format(scope=SCOPE, revision=revision, build_no=build_no)
        abi = ABIS[abi_code]

        print '{version_name}:{abi}'.format(version_name=version_name, abi=abi)
        return version_name, abi

    def name_to_code(self, version_name):
        parts = re.split('\.|:', version_name)
        if len(parts) < 3:
            print 'wrong input, make sure version name is correct'
            sys.exit(1)

        scope = parts[0]
        revision = parts[1]
        build_no = parts[2]

        version_code = (int(revision) << self.REVISION_OFFSET) + (int(build_no) << self.BUILD_NO_OFFSET)

        if len(parts) == 4:
            abi = parts[3]
            for abi_code, abi_name in ABIS.iteritems():
                if abi_name == abi:
                    version_code += abi_code
                    break

        return version_code


class ScreenAbiDensitySplitsVersion():
    """
    APK splits by screen size, abis and densities combined, started at revision #1348
    """
    VALID_FROM_REVISION = 0

    BUILD_NO_CYCLE_SIZE = 4096
    REVISION_OFFSET = 18
    BUILD_NO_OFFSET = 6
    SCREEN_VARIANT_CODE_OFFSET = 5
    DENSITY_CODE_OFFSET = 2
    ABI_CODE_OFFSET = 0

    # since build number is cyclic (%4096) we must figure out
    # which cycle we're on. MUST be ordered by cycles.
    VERSION_CYCLES = [
        # (cycle, revision)
        (2, 1403),
        (3, 1918),
]

    def __init__(self):
        pass

    def code_to_name(self, version_code):
        revision = (version_code & 0xfffc0000) >> self.REVISION_OFFSET
        build_no = (version_code & 0x0003ffe0) >> self.BUILD_NO_OFFSET
        screen_variant_code = (version_code & 0x00000020) >> self.SCREEN_VARIANT_CODE_OFFSET
        density_code = (version_code & 0x1c) >> self.DENSITY_CODE_OFFSET
        abi_code = version_code & 0x3

        build_no += self.BUILD_NO_CYCLE_SIZE * self.build_number_cycle(int(revision))

        version_name = '{scope}.{revision}.{build_no}'.format(scope=SCOPE, revision=revision, build_no=build_no)
        screen_variant = SCREEN_VARIANTS[screen_variant_code]
        abi = ABIS[abi_code]
        density = DENSITIES[density_code]

        print '{version_name}:{screen_variant}:{density}:{abi}'\
            .format(version_name=version_name, screen_variant=screen_variant, density=density, abi=abi)

        return version_name, screen_variant, density, abi


    def name_to_code(self, version_name):
        parts = re.split('\.|:', version_name)
        # if len(parts) < 4:
        #     print 'wrong input, make sure version name is correct'
        #     sys.exit(1)

        scope = parts[0]
        revision = parts[1]
        build_no = parts[2]

        version_code = (int(revision) << self.REVISION_OFFSET) + ((int(build_no) % self.BUILD_NO_CYCLE_SIZE) << self.BUILD_NO_OFFSET)

        if len(parts) >= 4:
            screen_variant = parts[3]
            for screen_variant_code, screen_variant_name in SCREEN_VARIANTS.iteritems():
                if screen_variant_name == screen_variant:
                    version_code += (screen_variant_code << self.SCREEN_VARIANT_CODE_OFFSET)
                    break

        if len(parts) >= 5:
            abi = parts[4]
            for abi_code, abi_name in ABIS.iteritems():
                if abi_name == abi:
                    version_code += abi_code
                    break

        if len(parts) >= 6:
            density = parts[5]
            for density_code, density_name in DENSITIES.iteritems():
                if density_name == density:
                    version_code += (density_code << self.DENSITY_CODE_OFFSET)
                    break

        return version_code

    def build_number_cycle(self, revision):
        for cycle in reversed(self.VERSION_CYCLES):
            if cycle[1] <= revision:
                return cycle[0]


def version_tool_entry():
    parser = ToolkitBase([CalcVersionName, CalcVersionCode])
    parser.parse()


calc_version_code = CalcVersionCode()
calc_version_name = CalcVersionName()

if __name__ == "__main__":
    version_tool_entry()
