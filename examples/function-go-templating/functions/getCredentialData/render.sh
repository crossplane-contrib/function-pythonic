#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --required-resources=resources.yaml --include-context xr.yaml composition.yaml
