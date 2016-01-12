#!/usr/bin/env sh
sed -e "s/^VERSION = .*/VERSION = '$1' # $2/" -i '' lobo/version.py setup.py
