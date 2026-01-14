#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render --extra-resources environmentConfigs.yaml --include-context xr.yaml composition.yaml functions.yaml
exec function-pythonic render --required-resources=environmentConfigs.yaml --include-context xr.yaml composition.yaml
