#!/usr/bin/env bash

cd $(dirname $(realpath $0))

# In one terminal
# PYTHONPATH=. function-pythonic grpc --insecure --debug
# In another terminal:
#exec crossplane render xr.yaml composition.yaml functions.yaml

exec function-pythonic render --python-path=. xr.yaml composition.yaml
