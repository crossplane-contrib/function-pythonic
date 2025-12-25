#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#crossplane render xr.yaml composition-wrapper.yaml functions.yaml
#crossplane render xr.yaml composition-real.yaml functions.yaml

function-pythonic render xr.yaml composition-wrapper.yaml
#function-pythonic render xr.yaml composition-real.yaml
