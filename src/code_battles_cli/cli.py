import click


@click.group()
@click.version_option(message="%(prog)s %(version)s")
def cli() -> None:
    pass


def main() -> int:
    from code_battles_cli.log import setup_logging

    setup_logging()

    from code_battles_cli.commands.download import download
    from code_battles_cli.commands.run import run
    from code_battles_cli.commands.upload import upload

    cli.add_command(download)
    cli.add_command(upload)
    cli.add_command(run)
    cli(standalone_mode=False)

    return 0
