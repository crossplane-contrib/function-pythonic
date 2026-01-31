#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --required-resources=environmentConfigs.yaml --include-context xr.yaml composition.yaml
