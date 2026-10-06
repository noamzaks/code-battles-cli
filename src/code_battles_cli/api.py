"""
Code Battles Python Client API

Firestore client implementation inspired by https://medium.com/@bobthomas295/client-side-authentication-with-python-firestore-and-firebase-352e484a2634
"""

from __future__ import annotations

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
from typing import Any, Callable, Literal

import requests
from google.cloud.firestore import Client as FirestoreClient
from google.oauth2.credentials import Credentials
from rich.prompt import Prompt
from typing_extensions import overload

from code_battles_cli.log import console, log

SIMULATION_FINISHED_MARK = b"--- SIMULATION FINISHED ---"
SIMULATION_STEP_MARK = b"__CODE_BATTLES_ADVANCE_STEP"


def normalize(url: str) -> str:
    if url.startswith("https"):
        url = url[5:]

    try:
        url = url[: url.index(".web.app")]
    except ValueError:
        pass

    return url


class SimulationException(Exception):
    def __init__(self, stderr: bytes, exit_code: int):
        self.stderr = stderr
        self.exit_code = exit_code

    def __str__(self) -> str:
        return (
            f"Simulation failed with exit code {self.exit_code}. Output:\n"
            + self.stderr.decode()
        )


@dataclass
class LogEntry:
    step: int
    text: str
    color: str
    player_index: int | None


@dataclass
class SimulationResults:
    winner_index: int
    winner: str
    steps: int
    logs: list[LogEntry]
    statistics: dict[str, float]


@dataclass
class Simulation:
    parameters: dict[str, str]
    statistics: dict[str, float]
    player_names: str
    game: str
    version: str
    timestamp: datetime.datetime
    logs: list[Any]
    alerts: list[Any]
    decisions: list[bytes]
    seed: int

    def dump(self) -> str:
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
                        "statistics": self.statistics,
                    }
                ).encode()
            )
        ).decode()

    @staticmethod
    def load(file: str) -> Simulation:
        contents: dict[str, Any] = json.loads(gzip.decompress(base64.b64decode(file)))
        return Simulation(
            contents["parameters"]
            if "parameters" in contents
            else {"map": contents["map"]},
            contents.get("statistics", {}),
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
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        dump_credentials: bool = True,
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

    def _get_credentials(self) -> None:
        if os.path.exists("code-battles.json"):
            with open("code-battles.json", "r") as f:
                configuration = json.load(f)
            self.url = configuration["url"]
            self.username = configuration["username"]
            self.password = configuration["password"]

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

            if self.username != self.username.lower():
                log.warning("Your username should most likely be lowercased.")

            self.password = Prompt.ask(
                "Enter your team's password", console=console, password=True
            )

    def _dump_credentials(self) -> None:
        with open("code-battles.json", "w") as f:
            json.dump(
                {"url": self.url, "username": self.username, "password": self.password},
                f,
            )
        log.info(
            "Credentials were dumped to `code-battles.json`. Make sure other teams don't have access to this file!"
        )

    def _get_firebase_data(self) -> None:
        configuration = requests.get(self.url + "/firebase-configuration.json").json()
        self.firebase_api_key: str = configuration["apiKey"]
        self.firebase_project_id: str = configuration["projectId"]

    def _sign_in(self, email_domain: str = "gmail.com") -> None:
        try:
            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.firebase_api_key}",
                json={
                    "email": self.username + "@" + email_domain,
                    "password": self.password,
                    "returnSecureToken": True,
                },
            ).json()
        except Exception as e:
            raise RuntimeError(
                "Sign in failed! Make sure the username and password are correct."
            ) from e

        self.credentials = Credentials(response["idToken"], response["refreshToken"])
        self.client = FirestoreClient(self.firebase_project_id, self.credentials)
        self.document = self.client.document(f"bots/{self.username}")

    def get_bots(self) -> dict[str, str]:
        """Returns a mapping from a bot's name to their Python code."""
        result = self.document.get().to_dict()
        assert result is not None
        return result

    def set_bots(self, bots: dict[str, str], merge: bool = True) -> None:
        """
        Sets the bots in the website to the specified bots.
        Doesn't remove any bot unless ``merge`` is ``False``, in which case only bots specified in ``bots`` will remain.
        """
        self.document.set(bots, merge)

    def _possibly_download(self, force_download: bool = False) -> str:
        directory_name = "".join(
            [c for c in normalize(self.url) if c.isalnum() or c == "-"]
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
        p: subprocess.Popen[bytes],
        json_output: bool = False,
        on_step: Callable[[], None] | None = None,
    ) -> SimulationResults | str:
        while True:
            if p.poll() is not None and p.returncode != 0:
                assert p.stderr is not None
                raise SimulationException(p.stderr.read(), p.returncode)

            assert p.stdout is not None
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

        output_json = json.loads(output)
        result = SimulationResults(
            output_json["winner_index"],
            output_json["winner"],
            output_json["steps"],
            [
                LogEntry(
                    entry["step"], entry["text"], entry["color"], entry["player_index"]
                )
                for entry in output_json["logs"]
            ],
            output_json.get("statistics", {}),
        )

        assert p.stderr is not None
        error: bytes = p.stderr.read()
        exit_code = p.wait()
        if exit_code != 0:
            raise SimulationException(error, exit_code)

        return result

    @overload
    def run_simulation(
        self,
        parameters: dict[str, str],
        bot_filenames: list[str],
        bot_names: list[str] | None = None,
        seed: int | None = None,
        force_download: bool = False,
        json_output: Literal[False] = False,
        on_step: Callable[[], None] | None = None,
        output_file: str | None = None,
    ) -> SimulationResults: ...

    @overload
    def run_simulation(
        self,
        parameters: dict[str, str],
        bot_filenames: list[str],
        bot_names: list[str] | None = None,
        seed: int | None = None,
        force_download: bool = False,
        json_output: Literal[True] = True,
        on_step: Callable[[], None] | None = None,
        output_file: str | None = None,
    ) -> str: ...

    def run_simulation(
        self,
        parameters: dict[str, str],
        bot_filenames: list[str],
        bot_names: list[str] | None = None,
        seed: int | None = None,
        force_download: bool = False,
        json_output: bool = False,
        on_step: Callable[[], None] | None = None,
        output_file: str | None = None,
    ) -> SimulationResults | str:
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
                str(
                    os.path.abspath(output_file)
                    if output_file is not None
                    else output_file
                ),
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
        force_download: bool = False,
        json_output: bool = False,
        on_step: Callable[[], None] | None = None,
    ) -> SimulationResults | str:
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
