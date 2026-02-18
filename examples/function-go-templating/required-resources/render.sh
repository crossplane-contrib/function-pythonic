#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --required-resources resources.yaml xr.yaml composition.yaml
