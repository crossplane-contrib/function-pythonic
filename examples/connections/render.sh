#!/usr/bin/env bash
cd $(dirname $(realpath $0))
exec function-pythonic render xr.yaml composition.yaml \
     --debug \
     --observed-resources rds-observed.yaml \
     --secret-store step-credential.yaml \
     --secret-store composite-connection.yaml \
     --secret-store rds-connection.yaml \
     --include-connection-xr
