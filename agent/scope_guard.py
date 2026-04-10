"""
Workspace scope guard — all file operations must stay inside the workspace root.

Usage:
    guard = ScopeGuard("/path/to/project")
    safe_path = guard.validate("src/main.py")    # returns Path
    guard.validate("../../etc/passwd")            # raises ScopeViolation
"""
from __future__ import annotations

from pathlib import Path


class ScopeViolation(Exception):
    """Raised when a path would escape the workspace root."""


class ScopeGuard:
    def __init__(self, workspace_root: str | Path) -> None:
        self.root: Path = Path(workspace_root).resolve()

    def validate(self, path: str | Path) -> Path:
        """
        Resolve path and verify it stays inside self.root.
        Relative paths are resolved relative to the workspace root (not cwd).
        Raises ScopeViolation if path escapes.
        """
        p = Path(path)
        candidate = (self.root / p if not p.is_absolute() else p).resolve()
        root_str = str(self.root)
        cand_str = str(candidate)
        inside = (
            cand_str == root_str
            or cand_str.startswith(root_str + "/")
            or cand_str.startswith(root_str + "\\")
        )
        if not inside:
            raise ScopeViolation(
                f"'{path}' resolves outside workspace root '{self.root}'"
            )
        return candidate

    def safe(self, path: str | Path) -> Path | None:
        """Like validate() but returns None instead of raising."""
        try:
            return self.validate(path)
        except ScopeViolation:
            return None

    def rel(self, abs_path: Path) -> str:
        """Return display-friendly relative path. Falls back to str."""
        try:
            return str(abs_path.relative_to(self.root))
        except ValueError:
            return str(abs_path)
