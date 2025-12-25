"""The function-pythonic's main CLI."""

import argparse
import asyncio
import sys

from . import (
    grpc,
    render,
    version,
)


def main():
    parser = argparse.ArgumentParser('Crossplane Function Pythonic')
    subparsers = parser.add_subparsers(title='Command', metavar='')
    grpc.Command.create(subparsers)
    render.Command.create(subparsers)
    version.Command.create(subparsers)
    args = parser.parse_args()
    if not hasattr(args, 'command'):
        parser.print_help()
        sys.exit(1)
    asyncio.run(args.command(args).run())


if __name__ == '__main__':
    main()
