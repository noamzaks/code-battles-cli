"""
Code Battles Python Client API

Firestore client implementation inspired by https://medium.com/@bobthomas295/client-side-authentication-with-python-firestore-and-firebase-352e484a2634
"""

import os
import json
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

import requests
from google.oauth2.credentials import Credentials
from google.cloud.firestore import Client as FirestoreClient
from rich.prompt import Prompt
from code_battles_cli.log import console, log


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
        # print(
        #     f"Got API Key: '{self.firebase_api_key}' and Project ID: '{self.firebase_project_id}'"
        # )

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

    def run_simulation(
        self,
        map: str,
        bot_filenames: List[str],
        bot_names: Optional[List[str]] = None,
        force_download=False,
        json_output=False,
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

        code_directory = os.path.expanduser(
            f"~/.cache/code-battles/{''.join([c for c in self.url.removeprefix("https").removesuffix(".web.app") if c.isalnum()])}"
        )

        if force_download and os.path.exists(code_directory):
            shutil.rmtree(code_directory)

        if not os.path.exists(code_directory):
            os.makedirs(code_directory)

            pyscript_configuration = requests.get(self.url + "/config.json").json()

            for url_path, path in pyscript_configuration["files"].items():
                local_path = os.path.join(
                    code_directory, *path.replace(".pyi", ".py").split("/")
                )
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                text = requests.get(self.url + url_path).text
                with open(local_path, "w") as f:
                    f.write(text)

        p = subprocess.Popen(
            [
                sys.executable,
                os.path.join(code_directory, "main.py"),
                map,
                "-".join(bot_names),
            ]
            + [os.path.abspath(f) for f in bot_filenames],
            env={"PYTHONPATH": os.path.join(code_directory, "code_battles")},
            stdout=subprocess.PIPE,
        )
        p.wait()
        output = p.stdout.read().split(b"--- SIMULATION FINISHED ---")[-1]
        if json_output:
            return output.decode()

        output = json.loads(output)
        return SimulationResults(
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
