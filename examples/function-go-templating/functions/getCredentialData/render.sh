#!/usr/bin/env bash
cd $(dirname $(realpath $0))
#exec crossplane render --function-credentials=credentials.yaml --include-context xr.yaml composition.yaml functions.yaml
exec function-pythonic render --secret-store=credentials.yaml --include-context xr.yaml composition.yaml
