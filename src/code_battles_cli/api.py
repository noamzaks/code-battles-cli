"""
Code Battles Python Client API

Firestore client implementation inspired by https://medium.com/@bobthomas295/client-side-authentication-with-python-firestore-and-firebase-352e484a2634
"""

import base64
import datetime
import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import requests
from google.cloud.firestore import Client as FirestoreClient
from google.oauth2.credentials import Credentials
from rich.prompt import Prompt

from code_battles_cli.log import console, log

SIMULATION_FINISHED_MARK = b"--- SIMULATION FINISHED ---"
SIMULATION_STEP_MARK = b"__CODE_BATTLES_ADVANCE_STEP"


class SimulationException(Exception):
    def __init__(self, stderr: bytes, exit_code: int):
        self.stderr = stderr
        self.exit_code = exit_code

    def __str__(self):
        return (
            f"Simulation failed with exit code {self.exit_code}. Output:\n"
            + self.stderr.decode()
        )


@dataclass
class LogEntry:
    step: int
    text: str
    color: str
    player_index: Optional[int]


@dataclass
class SimulationResults:
    winner_index: int
    winner: str
    steps: int
    logs: List[LogEntry]


@dataclass
class Simulation:
    parameters: Dict[str, str]
    player_names: str
    game: str
    version: str
    timestamp: datetime.datetime
    logs: list
    alerts: list
    decisions: List[bytes]
    seed: int

    def dump(self):
        return base64.b64encode(
            gzip.compress(
                json.dumps(
                    {
                        "parameters": self.parameters,
                        "playerNames": self.player_names,
                        "game": self.game,
                        "version": self.version,
                        "timestamp": self.timestamp.isoformat(),
                        "logs": self.logs,
                        "alerts": self.alerts,
                        "decisions": [
                            base64.b64encode(decision).decode()
                            for decision in self.decisions
                        ],
                        "seed": self.seed,
                    }
                ).encode()
            )
        ).decode()

    @staticmethod
    def load(file: str):
        contents: Dict[str, Any] = json.loads(gzip.decompress(base64.b64decode(file)))
        return Simulation(
            contents["parameters"]
            if "parameters" in contents
            else {"map": contents["map"]},
            contents["playerNames"],
            contents["game"],
            contents["version"],
            datetime.datetime.fromisoformat(contents["timestamp"]),
            contents["logs"],
            contents["alerts"],
            [base64.b64decode(decision) for decision in contents["decisions"]],
            contents["seed"],
        )


class Client:
    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        dump_credentials=True,
    ):
        """
        Creates a client for getting and setting the bots for a Code Battles hosted at `url`
        and signing in as `username` with `password`.
        """

        if url is None or username is None or password is None:
            self._get_credentials()
        else:
            self.url = url
            self.username = username
            self.password = password

        self._get_firebase_data()
        self._sign_in()

        if dump_credentials:
            self._dump_credentials()

    def _get_credentials(self):
        if os.path.exists("code-battles.json"):
            try:
                with open("code-battles.json", "r") as f:
                    configuration = json.load(f)
                self.url: str = configuration["url"]
                self.username: str = configuration["username"]
                self.password: str = configuration["password"]
            except Exception:
                pass

        if (
            not hasattr(self, "url")
            or not hasattr(self, "username")
            or not hasattr(self, "password")
        ):
            self.url = Prompt.ask("Enter your competition's URL", console=console)

            if not self.url.startswith("https://"):
                log.warning("Your URL should most likely start with 'https://'.")
            if not self.url.endswith(".web.app"):
                log.warning("Your URL should most likely end with '.web.app'.")

            self.username = Prompt.ask("Enter your team's username", console=console)

            if not self.username == self.username.lower():
                log.warning("Your username should most likely be lowercased.")

            self.password = Prompt.ask(
                "Enter your team's password", console=console, password=True
            )

    def _dump_credentials(self):
        with open("code-battles.json", "w") as f:
            json.dump(
                {"url": self.url, "username": self.username, "password": self.password},
                f,
            )
        log.info(
            "Credentials were dumped to `code-battles.json`. Make sure other teams don't have access to this file!"
        )

    def _get_firebase_data(self):
        configuration = requests.get(self.url + "/firebase-configuration.json").json()
        self.firebase_api_key: str = configuration["apiKey"]
        self.firebase_project_id: str = configuration["projectId"]

    def _sign_in(self, email_domain="gmail.com"):
        try:
            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.firebase_api_key}",
                json={
                    "email": self.username + "@" + email_domain,
                    "password": self.password,
                    "returnSecureToken": True,
                },
            ).json()
        except Exception:
            raise Exception(
                "Sign in failed! Make sure the username and password are correct."
            )

        self.credentials = Credentials(response["idToken"], response["refreshToken"])
        self.client = FirestoreClient(self.firebase_project_id, self.credentials)
        self.document = self.client.document(f"bots/{self.username}")

    def get_bots(self) -> Dict[str, str]:
        """Returns a mapping from a bot's name to their Python code."""
        return self.document.get().to_dict()

    def set_bots(self, bots: Dict[str, str], merge=True) -> None:
        """
        Sets the bots in the website to the specified bots.
        Doesn't remove any bot unless ``merge`` is ``False``, in which case only bots specified in ``bots`` will remain.
        """
        self.document.set(bots, merge)

    def _possibly_download(self, force_download=False):
        directory_name = "".join(
            [
                c
                for c in self.url.removeprefix("https").removesuffix(".web.app")
                if c.isalnum() or c == "-"
            ]
        )
        code_directory = os.path.expanduser(f"~/.cache/code-battles/{directory_name}")

        if force_download and os.path.exists(code_directory):
            shutil.rmtree(code_directory)

        if not os.path.exists(code_directory):
            os.makedirs(code_directory)

            with console.status("[blue]Fetching packed Python file..."):
                packed_file = requests.get(self.url + "/scripts/packed.py").text
                local_path = Path(code_directory) / "packed.py"
                local_path.write_text(packed_file)
                logging.info("Fetched packed Python file.")

        return code_directory

    def _get_simulation_output(
        self,
        p: subprocess.Popen,
        json_output=False,
        on_step: Optional[Callable[[], None]] = None,
    ) -> Union[SimulationResults, str]:
        while True:
            line: bytes = p.stdout.readline()
            line = line.strip()
            if line == SIMULATION_FINISHED_MARK:
                break
            elif line == SIMULATION_STEP_MARK:
                if on_step is not None:
                    on_step()
            elif len(line) != 0:
                logging.info(line.decode())

        output: bytes = p.stdout.read()
        if json_output:
            return output.decode()

        output = json.loads(output)
        result = SimulationResults(
            output["winner_index"],
            output["winner"],
            output["steps"],
            [
                LogEntry(
                    entry["step"], entry["text"], entry["color"], entry["player_index"]
                )
                for entry in output["logs"]
            ],
        )

        error: bytes = p.stderr.read()
        exit_code = p.wait()
        if exit_code != 0:
            raise SimulationException(error, exit_code)

        return result

    def run_simulation(
        self,
        parameters: Dict[str, str],
        bot_filenames: List[str],
        bot_names: Optional[List[str]] = None,
        seed: Optional[int] = None,
        force_download=False,
        json_output=False,
        on_step: Optional[Callable[[], None]] = None,
        output_file: Optional[str] = None,
    ) -> Union[SimulationResults, str]:
        """
        Runs the given simulation without UI locally.
        If ``bot_names`` is not specified, they will be the filenames without the extension.

        If required (or ``force_download``), this method downloads the simulation code from the website.

        If ``json_output`` is ``True``, returns the JSON string of the results instead.
        """

        if bot_names is None:
            bot_names = [
                os.path.splitext(os.path.basename(filename))[0]
                for filename in bot_filenames
            ]

        code_directory = self._possibly_download(force_download=force_download)

        p = subprocess.Popen(
            [
                sys.executable,
                os.path.join(code_directory, "packed.py"),
                "simulate",
                str(seed),
                str(os.path.abspath(output_file)),
                json.dumps(parameters),
                "-".join(bot_names),
            ]
            + [os.path.abspath(f) for f in bot_filenames],
            env={"PYTHONPATH": os.path.join(code_directory, "code_battles")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return self._get_simulation_output(p, json_output, on_step)

    def run_simulation_from_file(
        self,
        simulation_file: str,
        force_download=False,
        json_output=False,
        on_step: Optional[Callable[[], None]] = None,
    ) -> Union[SimulationResults, str]:
        """
        Runs the given simulation without UI locally from the given simulation file.

        If required (or ``force_download``), this method downloads the simulation code from the website.

        If ``json_output`` is ``True``, returns the JSON string of the results instead.
        """

        code_directory = self._possibly_download(force_download=force_download)

        p = subprocess.Popen(
            [
                sys.executable,
                os.path.join(code_directory, "packed.py"),
                "simulate-from-file",
                simulation_file,
            ],
            env={"PYTHONPATH": os.path.join(code_directory, "code_battles")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return self._get_simulation_output(p, json_output, on_step)
