#!/usr/bin/env bash
cd $(dirname $(realpath $0))
find . -name render.sh -exec bash -c 'echo "======================= {} ===========================" && {}' \;
