# backend/core/security.py
"""
Security and sandboxing helpers.

This module provides helper functions for validating paths, sanitizing inputs,
and constructing resource limits. Heavy lifting (actual enforcement) is performed
in sandbox.py where processes are spawned.

Functions:
- is_safe_path: ensure file paths live under allowed root
- sanitize_filename: basic sanitization for filenames
- resource_limits_for_run: convenience factory for CPU/time/memory limits
"""

from __future__ import annotations
from typing import Optional, Tuple
import os
import re
from dataclasses import dataclass


# Default allowed storage root for payloads and artifacts
DEFAULT_ALLOWED_ROOT = os.path.abspath(os.getenv("PIPEWISE_ALLOWED_ROOT", "/tmp/pipewise_storage"))


class SecurityError(Exception):
    pass


_filename_re = re.compile(r"^[A-Za-z0-9_.\-]+$")


def sanitize_filename(name: str, fallback: str = "payload.json") -> str:
    """
    Return a sanitized filename containing only safe characters.

    If sanitized result is empty, return fallback.
    """
    base = os.path.basename(name)
    if _filename_re.match(base):
        return base
    # remove unsafe characters
    cleaned = re.sub(r"[^A-Za-z0-9_.\-]", "_", base)
    return cleaned or fallback


def is_safe_path(path: str, allowed_root: str = DEFAULT_ALLOWED_ROOT) -> bool:
    """
    Determine whether the provided path is inside the allowed_root directory.
    Prevents path traversal attacks.
    """
    try:
        allowed_root = os.path.abspath(allowed_root)
        real_path = os.path.abspath(path)
        return os.path.commonpath([real_path, allowed_root]) == allowed_root
    except Exception:
        return False


@dataclass
class ResourceLimits:
    """
    Resource limits used by the sandbox runner.

    - cpu_time_seconds: soft CPU time limit (seconds)
    - memory_bytes: maximum resident set size in bytes
    - wall_time_seconds: wall-clock timeout (enforced by parent process)
    """
    cpu_time_seconds: Optional[int] = None
    memory_bytes: Optional[int] = None
    wall_time_seconds: Optional[int] = None


def resource_limits_for_run(cpu_seconds: Optional[int] = 10, memory_mb: Optional[int] = 512, wall_seconds: Optional[int] = 30) -> ResourceLimits:
    """
    Simple helper to build ResourceLimits for typical analysis tasks.
    """
    return ResourceLimits(cpu_time_seconds=cpu_seconds, memory_bytes=(memory_mb * 1024 * 1024) if memory_mb else None, wall_time_seconds=wall_seconds)


# TODO: implement additional checks for command whitelisting, capability dropping, uid/gid mapping, seccomp profiles, etc.
