#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render --secret-store=credentials.yaml --include-context xr.yaml composition.yaml
