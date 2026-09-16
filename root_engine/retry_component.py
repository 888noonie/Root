"""A curated, restricted adapter for an upstream Retry-After parser.

The full fetched module is never executed. Only a closed subset of the named
parser is accepted; network, file access, loops and arbitrary calls are absent.
"""

import ast
import email.utils
import math
import re
from types import SimpleNamespace

from .store import RootError

COMPONENT = "retry_after_parser"
ALLOWED_NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If,
                 ast.Assign, ast.AnnAssign, ast.Expr, ast.Return, ast.Raise,
                 ast.Compare, ast.Call, ast.Name, ast.Load, ast.Store,
                 ast.Constant, ast.Attribute, ast.BinOp, ast.Sub, ast.Is,
                 ast.IsNot, ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq,
                 ast.NotEq, ast.JoinedStr, ast.FormattedValue)
ALLOWED_NAMES = {"self", "retry_after", "seconds", "retry_date_tuple", "retry_date",
                 "int", "max", "InvalidHeader", "re", "email", "time", "str", "float"}
ALLOWED_ATTRIBUTES = {"re.match", "email.utils", "email.utils.parsedate_tz",
                      "email.utils.mktime_tz", "time.time", "self.retry_after_max"}
ALLOWED_CALLS = {"re.match", "email.utils.parsedate_tz", "email.utils.mktime_tz",
                 "time.time", "int", "max", "InvalidHeader"}


def attribute_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return attribute_name(node.value) + "." + node.attr
    return "unsupported"


def extract_parser(source):
    if not isinstance(source, str) or len(source.encode()) > 128 * 1024:
        raise RootError("Candidate source exceeds curated adapter limit")
    tree = ast.parse(source)
    matches = [method for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == "Retry"
               for method in cls.body if isinstance(method, ast.FunctionDef) and method.name == "parse_retry_after"]
    if len(matches) != 1:
        raise RootError("Candidate has no unique Retry.parse_retry_after adapter")
    method = matches[0]
    if method.decorator_list or [arg.arg for arg in method.args.args] != ["self", "retry_after"]:
        raise RootError("Unsupported parser signature")
    if method.args.defaults or method.args.kw_defaults or method.args.kwonlyargs or method.args.posonlyargs or method.args.vararg or method.args.kwarg:
        raise RootError("Unsupported parser arguments")
    for node in ast.walk(method):
        if isinstance(node, ast.FunctionDef) and node is not method:
            raise RootError("Nested function definitions are not permitted")
        if not isinstance(node, ALLOWED_NODES):
            raise RootError(f"Curated adapter rejects syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise RootError(f"Curated adapter rejects name: {node.id}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id not in {"seconds", "retry_date_tuple", "retry_date"}:
            raise RootError("Parser may assign only its three local variables")
        if isinstance(node, ast.Attribute) and (attribute_name(node) not in ALLOWED_ATTRIBUTES or not isinstance(node.ctx, ast.Load)):
            raise RootError("Curated adapter rejects attribute access")
        if isinstance(node, ast.Call):
            name = attribute_name(node.func)
            if name not in ALLOWED_CALLS or node.keywords:
                raise RootError("Curated adapter rejects call")
            if name == "re.match" and (len(node.args) != 2 or not isinstance(node.args[0], ast.Constant) or node.args[0].value != r"^\s*[0-9]+\s*$"):
                raise RootError("Only the known bounded numeric-header regex is permitted")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 120:
            raise RootError("Candidate constant exceeds adapter limit")
    method.returns = None
    for arg in method.args.args:
        arg.annotation = None
    # Drop type-only declarations; supplied namespaces contain no imports/IO.
    method.body = [node for node in method.body if not isinstance(node, ast.AnnAssign) or node.value is not None]
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    return ast.unparse(module)


def parser_from_source(source, now):
    code = extract_parser(source)
    namespace = {"__builtins__": {}, "int": int, "max": max,
                 "InvalidHeader": ValueError, "re": SimpleNamespace(match=re.match),
                 "email": SimpleNamespace(utils=SimpleNamespace(parsedate_tz=email.utils.parsedate_tz, mktime_tz=email.utils.mktime_tz)),
                 "time": SimpleNamespace(time=lambda: now)}
    exec(compile(code, "<restricted Retry-After adapter>", "exec"), namespace)
    # Preserve server delays: do not inherit an upstream cap that shortens them.
    return lambda header: namespace["parse_retry_after"](SimpleNamespace(retry_after_max=math.inf), header)


def candidate_delay(source, header, now):
    if header is None:
        return 300.0
    if not isinstance(header, str) or len(header) > 512:
        raise RootError("Retry-After header exceeds supported input bounds")
    try:
        delay = float(parser_from_source(source, now)(header))
    except (ValueError, OverflowError, TypeError):
        # Invalid instructions have no interpretable delay; preserve the baseline.
        return 300.0
    if not math.isfinite(delay):
        raise RootError("Retry-After delay is not finite")
    return max(300.0, delay)


def active_delay(store, header):
    exists = store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='components'").fetchone()
    if not exists:
        return 300.0
    row = store.db.execute("SELECT source FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
    return candidate_delay(row[0], header, store.now()) if row else 300.0
