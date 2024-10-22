import os
from typing import Optional

import click

from code_battles_cli.api import Client
from code_battles_cli.log import log


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
@click.option(
    "-b",
    "--bot",
    help="A specific bot name to download (downloads everything by default)",
)
@click.option(
    "-d",
    type=click.Path(file_okay=False),
    default="bots",
    show_default=True,
    help="The directory to download the bots into",
)
def download(
    url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    dump_credentials: bool,
    bot: Optional[str],
    d: str,
):
    client = Client(url, username, password, dump_credentials)
    bots = client.get_bots()
    if bot is not None:
        if bot not in bots:
            raise Exception(f"The specified bot '{bot}' does not exist!")
        bots = {bot: bots[bot]}

    if not os.path.exists(d):
        os.makedirs(d)

    for bot_name, bot_code in bots.items():
        with open(os.path.join(d, bot_name + ".py"), "w") as f:
            f.write(bot_code)

    log.info(
        f"{len(bots)} {'bots were' if len(bots) != 1 else 'bot was'} downloaded to [blue]{d}[/blue]."
    )
