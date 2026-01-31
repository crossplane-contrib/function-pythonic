#!/usr/bin/env bash

cd $(dirname $(realpath $0))
exec function-pythonic render --python-path=. xr.yaml composition.yaml
