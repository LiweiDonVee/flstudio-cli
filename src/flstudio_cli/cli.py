"""Click entrypoints with one JSON result, including usage errors and help."""

from pathlib import Path
import sys

import click
from pydantic import ValidationError

from . import __version__
from .capabilities import list_capabilities
from .contracts import NotesReplaceRequest, Plan, Result
from .environment import inspect_environment
from .flp_probe import probe_flp
from .json_output import JsonValueError, canonical_json, decode_json, encode_result, field_path
from .planning import PlanningError, build_plan


def _emit(result: Result) -> None:
    payload = (encode_result(result) + "\n").encode("utf-8")
    if sys.stdout is None:  # Windows pythonw login startup has no console.
        return
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
                        help='Output UTF-8 JSON (default).')(func)


def _version(ctx, param, value):
    if value and not ctx.resilient_parsing:
        _emit(Result(command="version", status="verified", data={"version": __version__}))
        ctx.exit()


@click.group(cls=JsonGroup, no_args_is_help=False, invoke_without_command=True)
@click.option("--version", is_flag=True, is_eager=True, expose_value=False, callback=_version)
@json_option
@click.pass_context
def app(ctx):
    """Compose and inspect saved FL projects; render with the real FL engine."""
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
    """Quickly check a saved FLP container without decoding its score."""


@flp.command("probe")
@click.option("--input", "input_path", type=click.Path(path_type=Path), required=True)
@json_option
def probe_command(input_path):
    """Validate an FLhd/FLdt envelope and hash one stable file snapshot."""
    _finish(probe_flp(input_path))


@app.group()
@json_option
def notes():
    """Read and edit exact pattern/channel scores in saved project copies."""


@notes.command('list')
@click.option('--project', required=True, type=click.Path(path_type=Path))
@click.option('--pattern-number', type=int, required=True)
@click.option('--channel-index', type=int, default=None)
@json_option
def list_notes(project, pattern_number, channel_index):
    from .flp import Project
    doc = Project.read(project)
    pattern = doc.patterns().get(pattern_number)
    if pattern is None:
        raise ValueError('Pattern does not exist in the saved project')
    values = [n for n in pattern['notes'] if channel_index is None or n['channel_index'] == channel_index]
    _emit(Result(command='notes list', status='verified', verified_scopes=['saved_notes'],
                 data={'project': str(project.resolve()), 'pattern_number': pattern_number,
                       'channel_index': channel_index, 'notes': values, 'count': len(values)}))


@notes.command("replace")
@click.option("--project", type=click.Path(path_type=Path), required=True)
@click.option("--pattern-number", type=int, required=True)
@click.option("--channel-index", type=int, required=True)
@click.option("--notes", "notes_path", type=click.Path(path_type=Path), required=True)
@click.option('--output', type=click.Path(path_type=Path), help='Write a distinct new FLP; the source is preserved.')
@click.option("--dry-run", is_flag=True, help="Build a plan without creating state or touching FL.")
@click.option("--plan-out", type=click.Path(path_type=Path), help="Explicit new plan file; parent must exist.")
@json_option
def replace_notes(project, pattern_number, channel_index, notes_path, output, dry_run, plan_out):
    """Replace one explicit saved score, preserving other channels' original note bytes."""
    if not dry_run and output is None:
        _reject_apply("notes replace")
    request = NotesReplaceRequest.model_validate(dict(operation="notes.replace", project=project,
                                                      pattern_number=pattern_number, channel_index=channel_index,
                                                      notes=_read_json(notes_path)))
    from .flp import Project
    doc = Project.read(project)
    doc.replace_notes(pattern_number, channel_index, [n.model_dump() for n in request.notes])
    target = {'pattern_number': pattern_number, 'channel_index': channel_index,
              'channel_iid': doc.channels()[channel_index]['iid']}
    data = {'target': target, 'requested_count': len(request.notes), 'live_applied': False,
            'source': str(project.resolve()), 'output': str(output.resolve()) if output else None}
    if dry_run:
        data.update(applied_count=None, file_effects=[], backend='flp_file',
                    executable=output is not None, requires_output=output is None)
        if plan_out:
            with plan_out.open('x', encoding='utf-8') as file:
                file.write(canonical_json(data))
            data['file_effects'] = [{'kind': 'plan_file_created', 'path': str(plan_out.resolve())}]
        _emit(Result(command='notes replace', status='planned', data=data))
        return
    doc.save(output)
    saved = Project.read(output)
    actual = [n for n in saved.patterns()[pattern_number]['notes'] if n['channel_index'] == channel_index]
    expected = [(n.key, n.start_tick, n.length_tick, n.velocity) for n in request.notes]
    expected.sort(key=lambda note: note[1])
    observed = [(n['key'], n['start_tick'], n['length_tick'], n['velocity']) for n in actual]
    if observed != expected:
        raise ValueError('Saved score does not match the requested notes')
    data.update(file_note_count=len(actual), applied_count=None)
    _emit(Result(command='notes replace', status='artifact_ready', verified_scopes=['saved_notes'], data=data))


@app.group()
@json_option
def plan():
    """Build source-bound file-edit plans and apply them to new project copies."""


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
@click.option('--dry-run', is_flag=True)
@json_option
def apply_command(plan_file, dry_run):
    """Apply a validated file plan once; source hashes and output paths are checked."""
    import hashlib
    from .flp import Project
    proposed = Plan.model_validate(_read_json(plan_file))
    if not proposed.executable or proposed.request.output is None:
        _reject_apply('plan apply')
    expected_hash = hashlib.sha256(canonical_json(proposed.request).encode('utf-8')).hexdigest()
    if expected_hash != proposed.request_sha256:
        raise PlanningError('Plan request changed after planning')
    doc = Project.read(proposed.request.project)
    if hashlib.sha256(doc.source).hexdigest() != proposed.source_sha256:
        raise PlanningError('Source project changed after planning')
    doc.replace_notes(proposed.request.pattern_number, proposed.request.channel_index,
                      [n.model_dump() for n in proposed.request.notes])
    if dry_run:
        _emit(Result(command='plan apply', status='planned', data={'plan': proposed.model_dump(), 'file_effects': [], 'applied_count': None}))
        return
    output = doc.save(proposed.request.output)
    actual = Project.read(output).patterns()[proposed.request.pattern_number]['notes']
    actual = [n for n in actual if n['channel_index'] == proposed.request.channel_index]
    _emit(Result(command='plan apply', status='artifact_ready', verified_scopes=['saved_notes'],
                 data={'output': str(output), 'file_note_count': len(actual), 'live_applied': False,
                       'target': proposed.bound_target}))


def _reject_apply(command):
    _emit(Result(command=command, status="rejected", reason_code="backend_unimplemented",
                 data={'applied_count': None, 'verified_count': None,
                       'message': 'Choose a distinct output path; live editor writes are not performed'}))
    raise click.exceptions.Exit(7)


def _read_json(path):
    return decode_json(Path(path).read_text(encoding="utf-8-sig"))


def _plan_result(command, request, plan_out):
    from .flp import Project
    import hashlib
    doc = Project.read(request.project)
    doc.replace_notes(request.pattern_number, request.channel_index, [n.model_dump() for n in request.notes])
    observation = doc.inspect()
    observation.update(path=str(request.project), sha256=hashlib.sha256(doc.source).hexdigest())
    planned = build_plan(request, Result(command='observe', status='verified', verified_scopes=['saved_notes'], data=observation))
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
    _emit(Result(command=command, status="planned", verified_scopes=['saved_notes'],
                 reason_code=None if planned.executable else 'output_path_required', data={"plan": planned.model_dump(mode="python"),
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
    except ValueError as exc:
        _emit(Result(command='cli', status='rejected', reason_code='invalid_project_request', data={'message': str(exc)}))
        raise SystemExit(2) from None
    except OSError as exc:
        _emit(Result(command="cli", status="failed", reason_code="file_io_error", data={"message": str(exc)}))
        raise SystemExit(5) from None
    except Exception as exc:
        _emit(Result(command="cli", status="failed", reason_code="internal_error",
                     data={"error_type": type(exc).__name__, "message": str(exc)}))
        raise SystemExit(5) from None


from .workflows import register as register_workflows
register_workflows(app, _emit, json_option)
from .live import register as register_live
register_live(app, _emit, json_option)
from .midi_bridge import register as register_bridge
register_bridge(app, _emit, json_option)
