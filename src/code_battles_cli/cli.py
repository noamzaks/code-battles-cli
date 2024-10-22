import datetime

import click


@click.group()
def cli():
    pass


def main() -> int:
    from code_battles_cli.log import setup_logging, log

    setup_logging()

    from code_battles_cli.commands.download import download
    from code_battles_cli.commands.upload import upload
    from code_battles_cli.commands.run import run

    cli.add_command(download)
    cli.add_command(upload)
    cli.add_command(run)
    cli(standalone_mode=False)

    return 0
