"""Click entrypoints with one JSON result, including usage errors and help."""

from pathlib import Path
import sys

import click
from pydantic import ValidationError

from . import __version__
from .capabilities import list_capabilities
from .contracts import NotesReplaceRequest, Result
from .environment import inspect_environment
from .flp_probe import probe_flp
from .json_output import JsonValueError, canonical_json, decode_json, encode_result, field_path
from .planning import PlanningError, build_plan


def _emit(result: Result) -> None:
    payload = (encode_result(result) + "\n").encode("utf-8")
    # Binary output does not depend on the Windows console/OEM code page.
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(payload.decode("utf-8"))


def _help(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if value and not ctx.resilient_parsing:
        _emit(Result(command=ctx.command_path, status="verified", data={"help": ctx.get_help()}))
        ctx.exit()


class JsonHelp:
    def get_help_option(self, ctx):
        return click.Option(["--help", "-h"], is_flag=True, is_eager=True, expose_value=False,
                            callback=_help, help="Show help as JSON and exit.")


class JsonCommand(JsonHelp, click.Command):
    pass


class JsonGroup(JsonHelp, click.Group):
    command_class = JsonCommand

    def group(self, *args, **kwargs):
        kwargs.setdefault("cls", JsonGroup)
        return super().group(*args, **kwargs)


def json_option(func):
    return click.option("--json", "json_output", is_flag=True, expose_value=False,
                        help="Output UTF-8 JSON (the M0 default).")(func)


def _version(ctx, param, value):
    if value and not ctx.resilient_parsing:
        _emit(Result(command="version", status="verified", data={"version": __version__}))
        ctx.exit()


@click.group(cls=JsonGroup, no_args_is_help=False, invoke_without_command=True)
@click.option("--version", is_flag=True, is_eager=True, expose_value=False, callback=_version)
@json_option
@click.pass_context
def app(ctx):
    """FL Studio CLI M0: read-only files, capabilities and unexecutable plans."""
    if ctx.invoked_subcommand is None:
        _help(ctx, None, True)


@app.command()
@click.option("--fl-install", type=click.Path(path_type=Path), help="Explicit FL installation directory.")
@json_option
def doctor(fl_install):
    """Inspect file versions/hashes and discover tools without starting FL."""
    _finish(inspect_environment(fl_install))


@app.command("capabilities")
@json_option
def capabilities_command():
    """List implementation separately from external research evidence."""
    _emit(Result(command="capabilities", status="verified", data={"capabilities": list_capabilities()}))


@app.group()
@json_option
def flp():
    """Inspect saved FLP files; no semantic score reader in M0."""


@flp.command("probe")
@click.option("--input", "input_path", type=click.Path(path_type=Path), required=True)
@json_option
def probe_command(input_path):
    """Validate an FLhd/FLdt envelope and hash one stable file snapshot."""
    _finish(probe_flp(input_path))


@app.group()
@json_option
def notes():
    """Validate and plan note changes; all live application is unavailable."""


@notes.command("replace")
@click.option("--project", type=click.Path(path_type=Path), required=True)
@click.option("--pattern-number", type=int, required=True)
@click.option("--channel-index", type=int, required=True)
@click.option("--notes", "notes_path", type=click.Path(path_type=Path), required=True)
@click.option("--dry-run", is_flag=True, help="Build a plan without creating state or touching FL.")
@click.option("--plan-out", type=click.Path(path_type=Path), help="Explicit new plan file; parent must exist.")
@json_option
def replace_notes(project, pattern_number, channel_index, notes_path, dry_run, plan_out):
    """Plan replacement at unbound one-based pattern/zero-based global channel selectors."""
    if not dry_run:
        _reject_apply("notes replace")
    request = NotesReplaceRequest.model_validate(dict(operation="notes.replace", project=project,
                                                      pattern_number=pattern_number, channel_index=channel_index,
                                                      notes=_read_json(notes_path)))
    _plan_result("notes replace", request, plan_out)


@app.group()
@json_option
def plan():
    """Build plans; M0 deliberately has no plan executor."""


@plan.command("build")
@click.option("--request", "request_path", type=click.Path(path_type=Path), required=True)
@click.option("--plan-out", type=click.Path(path_type=Path), help="Explicit new plan file; parent must exist.")
@json_option
def build_command(request_path, plan_out):
    """Validate a notes.replace request and inspect its source container."""
    request = NotesReplaceRequest.model_validate(_read_json(request_path))
    _plan_result("plan build", request, plan_out)


@plan.command("apply")
@click.option("--file", "plan_file", type=click.Path(path_type=Path), required=True)
@json_option
def apply_command(plan_file):
    """Reject application with exit 7; no file loading or dispatch occurs."""
    _reject_apply("plan apply")


def _reject_apply(command):
    _emit(Result(command=command, status="rejected", reason_code="backend_unimplemented",
                 data={"applied_count": None, "verified_count": None, "message": "M0 has no live execution backend"}))
    raise click.exceptions.Exit(7)


def _read_json(path):
    return decode_json(Path(path).read_text(encoding="utf-8-sig"))


def _plan_result(command, request, plan_out):
    probe = probe_flp(request.project)
    if "flp_container" not in probe.verified_scopes:
        _finish(probe.model_copy(update={"command": command}))
    planned = build_plan(request, probe)
    effects = []
    if plan_out is not None:
        target = plan_out.resolve()
        try:
            with target.open("x", encoding="utf-8", newline="\n") as file:
                file.write(canonical_json(planned) + "\n")
        except FileExistsError:
            _emit(Result(command=command, status="rejected", reason_code="plan_output_exists",
                         data={"path": str(target), "message": "plan output must be a new file"}))
            raise click.exceptions.Exit(2)
        effects.append({"kind": "plan_file_created", "path": str(target)})
    _emit(Result(command=command, status="planned", verified_scopes=["flp_container"],
                 reason_code="backend_unimplemented", data={"plan": planned.model_dump(mode="python"),
                 "requested_count": planned.requested_count, "artifact_count": None, "applied_count": None,
                 "verified_count": None, "file_effects": effects}))


def _finish(result):
    _emit(result)
    if result.status in ("failed", "rejected"):
        raise click.exceptions.Exit(2 if result.status == "rejected" else 5)


def main() -> None:
    try:
        # Click returns an explicit Exit code in non-standalone mode.
        # Preserve it for both console scripts and python -m.
        raise SystemExit(app(prog_name="flstudio", standalone_mode=False))
    except click.exceptions.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except click.ClickException as exc:
        _emit(Result(command="cli", status="rejected", reason_code="invalid_arguments", data={"message": exc.format_message()}))
        raise SystemExit(2) from None
    except ValidationError as exc:
        errors = [{"path": field_path(item["loc"]), "message": item["msg"], "type": item["type"]} for item in exc.errors()]
        _emit(Result(command="cli", status="rejected", reason_code="invalid_request", data={"errors": errors}))
        raise SystemExit(2) from None
    except (JsonValueError, UnicodeError) as exc:
        _emit(Result(command="cli", status="rejected", reason_code="invalid_json", data={"message": str(exc), "path": getattr(exc, "path", "$")}))
        raise SystemExit(2) from None
    except PlanningError as exc:
        _emit(Result(command="cli", status="rejected", reason_code="invalid_source_evidence", data={"message": str(exc)}))
        raise SystemExit(3) from None
    except OSError as exc:
        _emit(Result(command="cli", status="failed", reason_code="file_io_error", data={"message": str(exc)}))
        raise SystemExit(5) from None
    except Exception as exc:
        _emit(Result(command="cli", status="failed", reason_code="internal_error",
                     data={"error_type": type(exc).__name__, "message": str(exc)}))
        raise SystemExit(5) from None
