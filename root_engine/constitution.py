"""Trusted-code drift detection for pending promotions (not a security boundary)."""

import hashlib
from pathlib import Path

from .store import RootError, digest

PROJECT = Path(__file__).resolve().parents[1]

TRUSTED_RELATIVE_PATHS = (
    "root_engine/constitution.py",
    "root_engine/store.py",
    "root_engine/goals.py",
    "root_engine/promotion.py",
    "root_engine/retry_component.py",
    "root_engine/evaluate_component.py",
    "root_engine/__main__.py",
)


def _assert_unresolved_path_is_regular(unresolved, root):
    if unresolved.is_symlink():
        raise RootError(f"Trusted path must not be a symlink: {unresolved}")
    current = unresolved.parent
    root = root.resolve()
    while True:
        if current.is_symlink():
            raise RootError(f"Trusted path parent must not be a symlink: {current}")
        if current.resolve() == root:
            break
        if current == current.parent:
            raise RootError("Trusted path escaped project root")
        current = current.parent


def trusted_manifest(root=None):
    root = Path(root) if root is not None else PROJECT
    root_resolved = root.resolve()
    manifest = {}
    seen = set()
    for relative in TRUSTED_RELATIVE_PATHS:
        unresolved = root / relative
        if not unresolved.exists():
            raise RootError(f"Trusted path missing: {relative}")
        _assert_unresolved_path_is_regular(unresolved, root)
        resolved = unresolved.resolve()
        if not resolved.is_file() or resolved.is_symlink():
            raise RootError(f"Trusted path must be a regular file: {relative}")
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise RootError(f"Trusted path escapes project root: {relative}")
        if resolved in seen:
            raise RootError(f"Trusted path resolved duplicate: {relative}")
        seen.add(resolved)
        manifest[relative] = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return manifest


def trusted_manifest_digest(root=None):
    return digest(trusted_manifest(root))


def assert_trusted_manifest(stored, root=None):
    if not isinstance(stored, dict):
        raise RootError("Promotion trusted manifest is invalid")
    current = trusted_manifest(root)
    if stored != current:
        raise RootError("Trusted code changed since promotion was opened; promotion is stale")
