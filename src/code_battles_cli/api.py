"""
Code Battles Python Client API

Firestore client implementation inspired by https://medium.com/@bobthomas295/client-side-authentication-with-python-firestore-and-firebase-352e484a2634
"""

import os
import json
from typing import Dict, List, Optional

import requests
from google.oauth2.credentials import Credentials
from google.cloud.firestore import Client as FirestoreClient
from rich.prompt import Prompt
from code_battles_cli.logging import console, log


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
        Doesn't remove any bot unless `merge` is `False`, in which case only bots specified in `bots` will remain.
        """
        self.document.set(bots, merge)
