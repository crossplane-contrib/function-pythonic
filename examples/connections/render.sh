#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render xr.yaml composition.yaml \
     --debug \
     --observed-resources observed.yaml \
     --required-resources resources.yaml \
     --include-connection-xr
