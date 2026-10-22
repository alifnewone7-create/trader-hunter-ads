#!/usr/bin/env bash
# Build obfuscated .c -> native .so, inside this folder's venv.
# Requires: Python 3.11 + python3.11-dev + gcc  (see vps-obfuscated-run.md)
set -e
cd "$(dirname "$0")"

python3.11 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements-vps.txt

# compile every .c in this folder into a .so next to it
./venv/bin/python setup.py build_ext --inplace -j 4

# remove build artefacts and the C sources (optional: keeps only .so)
rm -rf build
rm -f *.c setup.py

echo
echo "Build done. Compiled modules:"
ls -1 *.so
