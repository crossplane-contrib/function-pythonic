
from . import (
    __about__,
    command,
)


class Command(command.Command):
    name = 'version'
    help = 'Print the function-oythonic version'

    async def run(self):
        print(__about__.__version__)
