#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --required-resources=resources.yaml --observed-resources=observed.yaml xr.yaml composition.yaml
