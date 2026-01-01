#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render -r xr.yaml composition.yaml functions.yaml

exec function-pythonic render \
     xr.yaml composition.yaml \
     --include-function-results

#exec function-pythonic render \
#     xr.yaml composition.yaml \
#     --observed-resources observed.yaml \
#     --include-function-results
