
from . import (
    command,
    __about__,
)


class Command(command.Command):
    name = 'version'
    help = 'Print the function-oythonic version'

    async def run(self):
        print(__about__.__version__)
