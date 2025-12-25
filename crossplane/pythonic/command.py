
import logging
import pathlib
import sys


class Command:
    name = None
    command = None
    description = None

    @classmethod
    def create(cls, subparsers):
        parser = subparsers.add_parser(cls.name, help=cls.help, description=cls.description)
        parser.set_defaults(command=cls)
        cls.add_parser_arguments(parser)

    @classmethod
    def add_parser_arguments(cls, parser):
        pass

    @classmethod
    def add_function_arguments(cls, parser):
        parser.add_argument(
            '--debug', '-d',
            action='store_true',
            help='Emit debug logs.',
        )
        parser.add_argument(
            '--log-name-width',
            type=int,
            default=40,
            metavar='WIDTH',
            help='Width of the logger name in the log output, default 40.',
        )
        parser.add_argument(
            '--python-path',
            action='append',
            default=[],
            metavar='DIRECTORY',
            help='Filing system directories to add to the python path.',
        )
        parser.add_argument(
            '--render-unknowns', '-u',
            action='store_true',
            help='Render resources with unknowns, useful during local development.'
        )
        parser.add_argument(
            '--allow-oversize-protos',
            action='store_true',
            help='Allow oversized protobuf messages',
        )

    def __init__(self, args):
        self.args = args
        self.initialize()

    def initialize(self):
        pass

    def initialize_function(self):
        formatter = Formatter(self.args.log_name_width)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG if self.args.debug else logging.INFO)

        for path in reversed(self.args.python_path):
            sys.path.insert(0, str(pathlib.Path(path).expanduser().resolve()))

        if self.args.allow_oversize_protos:
            from google.protobuf.internal import api_implementation
            if api_implementation._c_module:
                api_implementation._c_module.SetAllowOversizeProtos(True)

    async def run(self):
        raise NotImplementedError()


class Formatter(logging.Formatter):
    def __init__(self, name_width):
        super(Formatter, self).__init__(
            f"[{{asctime}}.{{msecs:03.0f}}] {{sname:{name_width}.{name_width}}} [{{levelname:8.8}}] {{message}}",
            '%Y-%m-%d %H:%M:%S',
            '{',
        )
        self.name_width = name_width

    def format(self, record):
        record.sname = record.name
        extra = len(record.sname) - self.name_width
        if extra > 0:
            names = record.sname.split('.')
            for ix, name in enumerate(names):
                if len(name) > extra:
                    names[ix] = name[extra:]
                    break
                names[ix] = name[:1]
                extra -= len(name) - 1
            record.sname = '.'.join(names)
        return super(Formatter, self).format(record)
