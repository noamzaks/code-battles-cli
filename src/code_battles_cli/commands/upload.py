import os
from typing import Optional

import click

from code_battles_cli.api import Client
from code_battles_cli.logging import log


@click.command()
@click.option(
    "-U", "--url", help="The competitions URL, for example https://code-battles.web.app"
)
@click.option("-u", "--username", help="Your team's username, for example mercedes")
@click.option("-p", "--password", help="Your team's password")
@click.option(
    "--dump-credentials",
    default=True,
    show_default=True,
    help="Dump the URL, username and password to a `code-battles.json` file",
)
@click.argument(
    "file",
    type=click.Path(exists=True, readable=True, dir_okay=False),
)
@click.option(
    "-n",
    "--name",
    help="The name of the bot to upload. By default, the file name without the extension will be used as the bot's name.",
)
def upload(
    file: str,
    name: Optional[str],
    url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    dump_credentials: bool,
):
    bot_name = name if name is not None else os.path.splitext(os.path.basename(file))[0]
    with open(file, "r") as f:
        bot_code = f.read()

    client = Client(url, username, password, dump_credentials)
    client.set_bots({bot_name: bot_code})
    log.info(f"{bot_code.count('\n') + 1} lines of code were uploaded as '{bot_name}'.")
