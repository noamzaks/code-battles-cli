import time
import logging
from typing import List, Optional, Tuple

import click

from code_battles_cli.api import Client
from code_battles_cli.log import log


@click.command()
@click.argument("map")
@click.argument("bots", nargs=-1)
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
    "--force-download",
    default=False,
    show_default=True,
    help="Re-downloads the simulation code from the website",
)
def run(
    url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    dump_credentials: bool,
    map: str,
    bots: Tuple[str],
    force_download: bool,
):
    logging.getLogger("rich").setLevel(logging.WARNING)
    client = Client(url, username, password, dump_credentials)
    start = time.time()
    results = client.run_simulation(map, list(bots), force_download=force_download)
    print("The winner is", results.winner, "after", results.steps, "steps.")
    end = time.time()
    log.info(f"Simulation took {(end - start) :.2f}s.")
