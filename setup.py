from setuptools import setup, find_packages

VERSION = '1.0.0'

setup(
    name='lobo',
    version=VERSION,
    author='EverythingMe',
    author_email='adam.kariv@gmail.com',
    install_requires=[
        'jira==0.16',
        'pyapi-gitlab>=7.5.0',
        'jenkinsapi>=0.2.26',
        'hypchat>=0.18',
        'python-dateutil>=2.2',
        'futures',
        'pyyaml',
        'Py2ChainMap'
    ],
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'lobo-issue-tracker = lobo:issue_tracker_tool_entry',
            'lobo-git = lobo:git_tool_entry',
            'lobo-cr = lobo:cr_tool_entry',
            'lobo-builder = lobo:builder_tool_entry',
            'lobo-im = lobo:im_tool_entry',
            'lobo-version = lobo:version_tool_entry',
            'lobo = lobo:lobo_entry',
        ]
    },
)
