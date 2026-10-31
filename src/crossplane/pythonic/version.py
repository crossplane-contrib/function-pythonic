from . import (
    __about__,
    command,
)


class Command(command.Command):
    name = "version"
    help = "Print the function-pythonic version"

    async def run(self) -> None:
        print(__about__.__version__)
