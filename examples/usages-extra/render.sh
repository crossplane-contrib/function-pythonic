#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --required-resources=extraResources.yaml --observed-resources=observedResources.yaml xr.yaml composition.yaml
