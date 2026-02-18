#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#function-pythonic render xr.yaml composition.yaml
function-pythonic render --observed-resource observed.yaml --required-resource resources.yaml xr.yaml composition.yaml
#function-pythonic render --crossplane-v1 --observed-resource observed.yaml --required-resource resources.yaml --include-connection-xr xr.yaml composition.yaml
