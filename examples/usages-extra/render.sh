#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render --extra-resources extraResources.yaml --observed-resources=observedResources.yaml xr.yaml composition.yaml functions.yaml
exec function-pythonic render --extra-resources=extraResources.yaml --observed-resources=observedResources.yaml xr.yaml composition.yaml
