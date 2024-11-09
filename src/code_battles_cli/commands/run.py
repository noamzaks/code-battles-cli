import time
import logging
import sys
from typing import List, Optional, Tuple

import click

from code_battles_cli.api import Client, Simulation
from code_battles_cli.log import log, progress


@click.command()
@click.argument("map", required=False)
@click.argument("bots", nargs=-1)
@click.option(
    "-U",
    "--url",
    help="The competition's URL, for example https://code-battles.web.app",
)
@click.option("-u", "--username", help="Your team's username, for example mercedes")
@click.option("-p", "--password", help="Your team's password")
@click.option(
    "--dump-credentials",
    is_flag=True,
    default=True,
    show_default=True,
    help="Dump the URL, username and password to a `code-battles.json` file",
)
@click.option(
    "--force-download",
    is_flag=True,
    default=False,
    show_default=True,
    help="Re-downloads the simulation code from the website",
)
@click.option(
    "-s", "--seed", type=int, help="Sets the given randomness seed for the simulation"
)
@click.option(
    "-S",
    "--simulation-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Re-downloads the simulation code from the website",
)
@click.option(
    "-O",
    "output_file",
    type=click.Path(exists=False),
    help="Output file to dump the simulation into",
)
def run(
    url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    dump_credentials: bool,
    map: str,
    bots: Tuple[str],
    force_download: bool,
    seed: Optional[int],
    simulation_file: Optional[str],
    output_file: Optional[str],
):
    logging.getLogger("rich").setLevel(logging.WARNING)
    client = Client(url, username, password, dump_credentials)
    client._possibly_download(force_download)
    start = time.time()

    with progress:
        progress_id = progress.add_task("[green]Simulating...", total=None)

        def on_step():
            progress.update(progress_id, advance=1)

        if simulation_file is not None:
            assert (
                map is None
            ), "The simulation's map is given from the simulation file!"
            assert (
                len(bots) == 0
            ), "The simulation's bots are given from the simulation file!"
            assert (
                seed is None
            ), "The simulation's seed is given from the simulation file!"
            assert (
                output_file is None
            ), "Shouldn't dump simualtion file from existing simulation file!"

            with open(simulation_file, "r") as f:
                simulation_text = f.read()
            simulation = Simulation.load(simulation_text)
            logging.info(
                f"Detected simulation file of {simulation.game} {simulation.version}"
            )
            logging.info(
                f"Simulation happened in {simulation.map} between {', '.join(simulation.player_names)} with seed {simulation.seed}"
            )
            logging.info(f"Simulation contains {len(simulation.decisions)} decisions")
            progress.update(progress_id, total=len(simulation.decisions) - 1)
            results = client.run_simulation_from_file(
                simulation_file, force_download=False, on_step=on_step
            )
        else:
            assert map is not None, "Map is required for simulation!"
            assert len(bots) > 0, "Bots are required for simulation!"

            results = client.run_simulation(
                map,
                list(bots),
                seed=seed,
                force_download=False,
                on_step=on_step,
                output_file=output_file,
            )
    print("The winner is", results.winner, "after", results.steps, "steps.")
    end = time.time()
    log.info(f"Simulation took {(end - start) :.2f}s.")
