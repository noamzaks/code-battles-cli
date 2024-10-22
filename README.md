<p align="center">
  <img src="https://github.com/noamzaks/code-battles/assets/63877260/b330aa14-7003-4204-8907-e77a5c6e8d81" height="140">
</p>
<h1 align="center">
  Code Battles CLI
  <br />
  <img src="https://img.shields.io/pypi/v/code-battles-cli">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg">
</h1>

<p align="center">
    A CLI for competitors in any Code Battles event!
</p>
<p align="center">
    🏃 <a href="#getting-started">Getting Started</a>
    &nbsp;&middot&nbsp;
    💡 <a href="#features">Features</a>
    &nbsp;&middot&nbsp;
    🚗 <a href="#roadmap">Roadmap</a>
</p>

# Getting Started

-   Install the library by running `pip install code-battles-cli`.
-   Make sure you have the Python scripts folder in your `PATH` by running `code-battles --help`.
-   If that fails, run `py -m code_battles_cli --help`.

The first time you run any command you will be asked for your URL, username and password, and they'll be saved in a `code-battles.json` file for successive calls.

# Features

## Downloading the bots

You can download all of the bots your team has by running `code-battles download`.

## Uploading a bot

You can update a bot in the website by running `code-battles upload bots/example.py` (in this case the bot's name will be `example`).

If you want to choose a custom bot name, you can run `code-battles upload bots/example.py -n myamazingbot`.

## Running a simulation

You can run a simulation by running `code-battles run NYC bots/example.py bots/another_example.py`, where `NYC` is an example of a map.

You will probably find the scripting API nicer to work with if you want to run simulations locally.

## Usage in scripts

You can import the `code_battles_cli.api` module and utilize its `Client` class to hack Code Battles for your needs!

Example:

```python
from code_battles_cli.api import Client

client = Client()

print(client.get_bots())
print(client.run_simulation("NYC", ["bots/example.py", "bots/another_example.py"]))
```

# Roadmap

-   [x] Download bots.
-   [x] Upload bots.
-   [ ] Run no-UI simulations locally.
-   [x] Be usable in scripts.
