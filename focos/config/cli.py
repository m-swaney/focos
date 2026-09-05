"""`focos init`, `focos migrate`, and the `focos config ...` sub-app."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from .. import paths, settings

config_app = typer.Typer(no_args_is_help=True, help="Validate, show, or export the schema of config files.")


def _echo(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


def init(home: Path = typer.Option(None, "--home", help="data dir to create (default: the resolved FOCOS_HOME)"),
         set_default: bool = typer.Option(False, "--set-default", help="write ~/.focos/home.txt so every focos "
                                                                    "command uses this dir")) -> None:
    """Create a household data dir from the templates (safe to re-run; existing files are kept)."""
    from .init import init_home

    target = Path(home) if home else paths.HOME
    out = init_home(target, set_default=set_default)
    paths.rebind(out["home"])
    settings.reset()
    _echo(out)


def migrate(home: Path = typer.Option(None, "--home"), dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Upgrade config files in the data dir to the current layout."""
    from . import migrate as mig

    target = Path(home).expanduser().resolve() if home else paths.HOME
    out = mig.run(target, dry_run=dry_run)
    settings.reset()
    _echo(out)
    if out.get("error"):
        raise typer.Exit(1)


@config_app.command("validate")
def config_validate(home: Path = typer.Option(None, "--home")) -> None:
    """Check every config file against its schema and cross-file references. Exit 1 on errors."""
    from .validate import has_errors, validate_all

    cdir = (Path(home).expanduser().resolve() / "config") if home else paths.CONFIG
    issues = validate_all(cdir)
    _echo({"config_dir": str(cdir), "ok": not has_errors(issues), "issues": [i.as_dict() for i in issues]})
    if has_errors(issues):
        raise typer.Exit(1)


@config_app.command("show")
def config_show(name: str = typer.Argument(..., help="focos | profile | goals | accounts | entities | ...")) -> None:
    """Print a config file as JSON after defaults are applied (focos.yml) or as loaded (others)."""
    key = name if name.endswith(".yml") else f"{name}.yml"
    if key == "focos.yml":
        _echo(settings.focos())
    else:
        _echo(settings._load_yaml(key))


@config_app.command("schema")
def config_schema(out: Path = typer.Option(None, "--out", help="directory to write <file>.schema.json into")) -> None:
    """Export JSON Schema for every config file (used by the dashboard forms)."""
    from .models import MODELS

    schemas = {name: model.model_json_schema() for name, model in MODELS.items()}
    if out:
        out.mkdir(parents=True, exist_ok=True)
        for name, schema in schemas.items():
            (out / f"{name[:-4]}.schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        _echo({"written": sorted(f"{n[:-4]}.schema.json" for n in schemas)})
    else:
        _echo(schemas)


@config_app.command("home")
def config_home() -> None:
    """Print the resolved data dir and how it was found."""
    import os

    src = ("FOCOS_HOME" if os.environ.get("FOCOS_HOME") else "FOCOS_REPO_ROOT" if os.environ.get("FOCOS_REPO_ROOT")
           else "pointer file" if paths.pointer_file().exists() else "cwd/checkout/default")
    _echo({"home": str(paths.HOME), "app": str(paths.APP), "resolved_from": src, "pointer_file": str(paths.pointer_file()),
           "version_file": paths.VERSION_FILE.read_text(encoding="utf-8").strip() if paths.VERSION_FILE.exists() else None})
