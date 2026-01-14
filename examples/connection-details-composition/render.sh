#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render xr.yaml composition.yaml functions.yaml

#function-pythonic render xr.yaml composition.yaml
#function-pythonic render --observed-resource user.yaml xr.yaml composition.yaml
function-pythonic render --observed-resource user.yaml --observed-resource access-keys.yaml --secret-store secrets.yaml xr.yaml composition.yaml
#function-pythonic render --crossplane-v1 --observed-resource user.yaml --observed-resource access-keys.yaml --secret-store secrets.yaml --include-connection-xr xr.yaml composition.yaml
