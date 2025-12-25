#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render --include-full-xr --include-function-results xr.yaml composition.yaml functions.yaml
exec function-pythonic render --python-path=. --render-unknowns --include-full-xr --include-function-results xr.yaml composition.yaml
