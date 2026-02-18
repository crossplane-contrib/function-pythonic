#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render xr.yaml composition.yaml
#exec function-pythonic render --observed-resources observed.yaml xr.yaml composition.yaml
