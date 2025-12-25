
import asyncio
import os
import pathlib
import shlex
import signal
import sys

import crossplane.function.proto.v1.run_function_pb2_grpc as grpcv1
import grpc

from . import (
    command,
    function,
)


class Command(command.Command):
    name = 'grpc'
    help = 'Run function-pythonic gRPC server'

    @classmethod
    def add_parser_arguments(cls, parser):
        cls.add_function_arguments(parser)
        parser.add_argument(
            '--address',
            default='0.0.0.0:9443',
            help='Address to listen on for gRPC connections, default: 0.0.0.0:9443',
        )
        parser.add_argument(
            '--tls-certs-dir',
            default=os.getenv('TLS_SERVER_CERTS_DIR'),
            metavar='DIRECTORY',
            help='Serve using TLS certificates.',
        )
        parser.add_argument(
            '--insecure',
            action='store_true',
            help='Run without mTLS credentials, --tls-certs-dir will be ignored.',
        )
        parser.add_argument(
            '--packages',
            action='store_true',
            help='Discover python packages from function-pythonic ConfigMaps.'
        )
        parser.add_argument(
            '--packages-secrets',
            action='store_true',
            help='Also Discover python packages from function-pythonic Secrets.'
        )
        parser.add_argument(
            '--packages-namespace',
            action='append',
            default=[],
            metavar='NAMESPACE',
            help='Namespaces to discover function-pythonic ConfigMaps in, default is cluster wide.',
        )
        parser.add_argument(
            '--packages-dir',
            default='./pythonic-packages',
            metavar='DIRECTORY',
            help='Directory to store discovered function-pythonic ConfigMaps to, defaults "<cwd>/pythonic-packages"'
        )
        parser.add_argument(
            '--pip-install',
            metavar='INSTALL',
            help='Pip install command to install additional Python packages.'
        )

    def initialize(self):
        if not self.args.tls_certs_dir and not self.args.insecure:
            print('Either --tls-certs-dir or --insecure must be specified', file=sys.stderr)
            sys.exit(1)

        if self.args.pip_install:
            import pip._internal.cli.main
            pip._internal.cli.main.main(['install', '--user', *shlex.split(self.args.pip_install)])

        self.initialize_function()

        # enables read only volumes or mismatched uid volumes
        sys.dont_write_bytecode = True

    async def run(self):
        grpc.aio.init_grpc_aio()
        grpc_runner = function.FunctionRunner(self.args.debug, self.args.render_unknowns)
        grpc_server = grpc.aio.server()
        grpcv1.add_FunctionRunnerServiceServicer_to_server(grpc_runner, grpc_server)
        if self.args.insecure:
            grpc_server.add_insecure_port(self.args.address)
        else:
            certs = pathlib.Path(self.args.tls_certs_dir).expanduser().resolve()
            grpc_server.add_secure_port(
                self.args.address,
                grpc.ssl_server_credentials(
                    private_key_certificate_chain_pairs=[(
                        (certs / 'tls.key').read_bytes(),
                        (certs / 'tls.crt').read_bytes(),
                    )],
                    root_certificates=(certs / 'ca.crt').read_bytes(),
                    require_client_auth=True,
                ),
            )
        await grpc_server.start()

        if self.args.packages:
            from . import packages
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(grpc_server.wait_for_termination())
                tasks.create_task(packages.operator(
                    grpc_server,
                    grpc_runner,
                    self.args.packages_secrets,
                    self.args.packages_namespace,
                    self.args.packages_dir,
                ))
        else:
            def stop():
                asyncio.ensure_future(grpc_server.stop(5))
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGINT, stop)
            loop.add_signal_handler(signal.SIGTERM, stop)
            await grpc_server.wait_for_termination()
