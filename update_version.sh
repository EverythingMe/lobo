#!/usr/bin/env sh
sed -e "s/^VERSION = .*/VERSION = '$1' # $2/" -i '' flow_toolkit/version.py setup.py
