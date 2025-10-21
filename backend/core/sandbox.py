# core/sandbox.py
from __future__ import annotations
import subprocess
import shlex
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import tempfile
import pathlib
import shutil
import logging
import stat

from .security import ResourceLimits, is_safe_path, DEFAULT_ALLOWED_ROOT

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass
class RunResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    killed: bool
    wall_time: float
    extra: Dict[str, Any] = None


class SandboxError(Exception):
    pass


def _posix_preexec_fn(limits: ResourceLimits, working_dir: Optional[str] = None) -> None:
    import resource

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    if limits.cpu_time_seconds:
        soft = int(limits.cpu_time_seconds)
        hard = int(limits.cpu_time_seconds) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))

    if limits.memory_bytes:
        mem = int(limits.memory_bytes)
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))

    # Drop privileges if possible
    try:
        if os.geteuid() == 0:
            import pwd
            import grp
            try:
                nobody = pwd.getpwnam("nobody")
                try:
                    nogroup = grp.getgrnam("nogroup")
                    gid = nogroup.gr_gid
                except Exception:
                    gid = nobody.pw_gid
                os.setgid(gid)
                os.setuid(nobody.pw_uid)
            except Exception:
                pass
    except Exception:
        pass

    if working_dir:
        try:
            os.chdir(working_dir)
        except Exception:
            pass


def run_command(
    command: List[str] | str,
    *,
    limits: Optional[ResourceLimits] = None,
    input_data: Optional[bytes] = None,
    env: Optional[Dict[str, str]] = None,
    working_dir: Optional[str] = None,
    capture_output: bool = True,
    shell: bool = False,
    timeout: Optional[int] = None,
) -> RunResult:
    if not command:
        raise SandboxError("Empty command")

    if working_dir:
        working_dir = os.path.abspath(working_dir)
        if not is_safe_path(working_dir):
            raise SandboxError(f"Unsafe working_dir: {working_dir}")
        if not os.path.exists(working_dir):
            raise SandboxError(f"Working directory does not exist: {working_dir}")

    limits = limits or ResourceLimits()
    start = time.time()

    env_combined = os.environ.copy()
    if env:
        env_combined.update(env)

    popen_kwargs = {
        "stdin": subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
        "stdout": subprocess.PIPE if capture_output else None,
        "stderr": subprocess.PIPE if capture_output else None,
        "env": env_combined,
        "cwd": working_dir or None,
        "shell": shell,
    }

    if sys.platform != "win32":
        popen_kwargs["preexec_fn"] = lambda: _posix_preexec_fn(limits, working_dir=working_dir)

    cmd = command
    if shell:
        if isinstance(command, list):
            cmd = " ".join(shlex.quote(str(p)) for p in command)
        else:
            cmd = str(command)

    proc = None
    timed_out = False
    killed = False
    stdout, stderr = b"", b""
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except Exception as e:
        raise SandboxError(f"Failed to spawn process: {e}")

    try:
        out, err = proc.communicate(input=input_data, timeout=timeout or limits.wall_time_seconds)
        stdout = out or b""
        stderr = err or b""
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            proc.terminate()
            try:
                out, err = proc.communicate(timeout=5)
                stdout += out or b""
                stderr += err or b""
            except subprocess.TimeoutExpired:
                proc.kill()
                killed = True
                out, err = proc.communicate()
                stdout += out or b""
                stderr += err or b""
        except Exception:
            try:
                proc.kill()
                killed = True
            except Exception:
                pass
    finally:
        end = time.time()
        wall_time = end - start
        returncode = proc.returncode if proc else None
        try:
            stdout_s = stdout.decode("utf8", errors="replace") if isinstance(stdout, (bytes, bytearray)) else str(stdout)
        except Exception:
            stdout_s = "<unreadable stdout>"
        try:
            stderr_s = stderr.decode("utf8", errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr)
        except Exception:
            stderr_s = "<unreadable stderr>"

    return RunResult(
        returncode=returncode,
        stdout=stdout_s,
        stderr=stderr_s,
        timed_out=timed_out,
        killed=killed,
        wall_time=wall_time,
        extra={"cmd": command, "limits": limits.__dict__},
    )


def run_python_snippet(
    snippet: str,
    *,
    limits: Optional[ResourceLimits] = None,
    timeout: Optional[int] = None,
    python_executable: str = sys.executable,
) -> RunResult:
    # Ensure allowed root exists and is traversable
    root = pathlib.Path(DEFAULT_ALLOWED_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o755)
    except Exception:
        pass

    workers_root = root / "workers"
    workers_root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(workers_root, 0o755)
    except Exception:
        pass

    tmpdir = tempfile.mkdtemp(prefix="pipewise_worker_", dir=str(workers_root))
    script_name = pathlib.Path(tmpdir) / "worker_snippet.py"

    # Write script
    script_name.write_text(snippet, encoding="utf8")

    # Relax permissions so the dropped user can traverse/read
    try:
        os.chmod(tmpdir, 0o755)           # dir: traverse allowed
        os.chmod(script_name, 0o644)      # file: readable by others
    except Exception:
        pass

    # Force matplotlib to write cache into temp dir and use non-GUI backend
    env = {
        "MPLCONFIGDIR": tmpdir,
        "MPLBACKEND": "Agg",
    }

    try:
        return run_command(
            [python_executable, str(script_name)],
            limits=limits or ResourceLimits(),
            timeout=timeout,
            working_dir=tmpdir,
            capture_output=True,
            shell=False,
            env=env,
        )
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass