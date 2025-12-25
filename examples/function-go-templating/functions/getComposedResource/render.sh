#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render --observed-resources=observed.yaml  xr.yaml composition.yaml functions.yaml
exec function-pythonic render --observed-resources=observed.yaml xr.yaml composition.yaml
