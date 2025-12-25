#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render xr.yaml ../../package/composite-composition.yaml functions.yaml
exec function-pythonic render xr.yaml
