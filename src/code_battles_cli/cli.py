import datetime

import click


@click.group()
def cli():
    pass


def main() -> int:
    from code_battles_cli.logging import setup_logging, log

    setup_logging()

    from code_battles_cli.commands.download import download
    from code_battles_cli.commands.upload import upload

    cli.add_command(download)
    cli.add_command(upload)
    cli(standalone_mode=False)

    return 0
