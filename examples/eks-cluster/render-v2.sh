#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render xr.yaml composition-v2.yaml functions.yaml
exec function-pythonic render xr.yaml composition-v2.yaml
