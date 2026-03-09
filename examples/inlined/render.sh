#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render xr.yaml composition.yaml
