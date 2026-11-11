"""Python scripts evaluated against an isolated project copy.

Two modes:

restricted (default)  the script may change ``project`` and use the names
                      listed in the tutorial. Imports are limited to ``math``
                      and ``from slipsurface.<project|loads|materials|...>
                      import <names>``; file access, ``exec``/``eval``,
                      names and attributes that start with an underscore and
                      ``Project.save``/``load`` are refused before anything runs.
trusted               ordinary Python with the user's permissions.

The restricted mode stops a script from reaching the file system, the network
or other programs by the ordinary routes. It is a guard for scripts received
from others, not a security boundary against a determined attacker: read a
script before running it, as with any file that changes a model.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import inspect
import io

from slipsurface.loads import FacingType, SupportType
from slipsurface.project import MaterialSpec, Project, empty_project

SAFE_PLAIN_IMPORTS = frozenset({"math"})
SAFE_FROM_IMPORTS = frozenset(
    {
        "math",
        "slipsurface.project",
        "slipsurface.loads",
        "slipsurface.materials",
        "slipsurface.materials.catalog",
        "slipsurface.geometry",
        "slipsurface.lem",
        "slipsurface.analysis",
    }
)
BLOCKED_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "input",
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "memoryview",
        "help",
        "exit",
        "quit",
    }
)
BLOCKED_ATTRIBUTES = frozenset({"save", "load"})  # Project file access
ALLOWED_DUNDER_NAMES = frozenset({"__name__"})
SAFE_BUILTINS = (
    "abs all any bool dict divmod enumerate filter float frozenset int isinstance len list "
    "map max min pow print range repr reversed round set slice sorted str sum tuple zip "
    "ArithmeticError AssertionError Exception IndexError KeyError LookupError RuntimeError "
    "StopIteration TypeError ValueError ZeroDivisionError True False None"
).split()


class ScriptNotAllowed(ValueError):
    """The script uses something the restricted mode does not permit."""


def _refuse(node: ast.AST, what: str) -> ScriptNotAllowed:
    return ScriptNotAllowed(
        f"line {getattr(node, 'lineno', '?')}: {what} is not available in restricted mode. "
        "Tick 'Full Python access' to run a script you trust."
    )


def check_restricted(source: str) -> None:
    """Raise ScriptNotAllowed (or SyntaxError) before a restricted script runs."""
    for node in ast.walk(ast.parse(source, "<project-script>")):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in SAFE_PLAIN_IMPORTS:
                    raise _refuse(node, f"'import {alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module not in SAFE_FROM_IMPORTS:
                raise _refuse(node, f"'from {node.module} import …'")
            for alias in node.names:
                if alias.name == "*" or alias.name.startswith("_"):
                    raise _refuse(node, f"importing '{alias.name}'")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES:
                raise _refuse(node, f"the attribute '.{node.attr}'")
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES or (
                node.id.startswith("_") and node.id not in ALLOWED_DUNDER_NAMES
            ):
                raise _refuse(node, f"'{node.id}'")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.ClassDef)):
            raise _refuse(node, f"a '{type(node).__name__}' statement")


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed = SAFE_FROM_IMPORTS if fromlist else SAFE_PLAIN_IMPORTS
    if level or name not in allowed:
        raise ScriptNotAllowed(f"'import {name}' is not available in restricted mode.")
    module = builtins.__import__(name, globals, locals, fromlist, level)
    for item in fromlist or ():
        if inspect.ismodule(getattr(module, item, None)):
            raise ScriptNotAllowed(f"'{name}.{item}' is a module; restricted mode refuses it.")
    return module


def _restricted_builtins() -> dict:
    safe = {name: getattr(builtins, name) for name in SAFE_BUILTINS}
    safe["__import__"] = _restricted_import
    return safe


def run_script(source: str, project: Project, trusted: bool = False) -> tuple[Project, str]:
    """Run `source` against a copy of `project`; returns (new project, printed text).

    `trusted=False` (the default) applies the restricted mode described in the
    module docstring; `trusted=True` runs ordinary Python."""
    candidate = project.copy()
    namespace: dict = {
        "__name__": "__main__",
        "project": candidate,
        "Project": Project,
        "MaterialSpec": MaterialSpec,
        "SupportType": SupportType,
        "FacingType": FacingType,
        "empty_project": empty_project,
    }
    if not trusted:
        check_restricted(source)
        namespace["__builtins__"] = _restricted_builtins()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(source, "<project-script>", "exec"), namespace)
    candidate = namespace["project"]
    if not isinstance(candidate, Project):
        raise ValueError("project must be a Project instance")
    candidate.validate()
    candidate.build_geometry()
    return candidate, output.getvalue()
