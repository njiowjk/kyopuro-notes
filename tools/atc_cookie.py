"""Read an atc-rs session without managing its credential store."""

from contextlib import ExitStack
from dataclasses import dataclass, field
import errno
import os
from pathlib import Path
import re
import stat
import sys


MAX_COOKIE_LINE_BYTES = 4096
COOKIE_LINE = re.compile(rb"REVEL_SESSION=[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]+")


@dataclass(frozen=True)
class SessionCookie:
    state: str
    header: str | None = field(default=None, repr=False)


def cookie_location():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        directories = ("atc", "state")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", ""))
        if not base.is_absolute():
            base = Path.home() / ".local" / "state"
        directories = ("atc",)
    if not base.is_absolute() or ".." in base.parts or "\0" in str(base):
        raise OSError(errno.EINVAL, "invalid state directory")
    if sys.platform == "win32" and base.drive.startswith(("\\\\.\\", "\\\\?\\")):
        raise OSError(errno.EINVAL, "invalid Windows state namespace")
    return base, directories


def check_unix_cookie_file(info):
    if not stat.S_ISREG(info.st_mode):
        raise OSError(errno.EINVAL, "cookie is not a regular file")
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PermissionError("unsafe cookie permissions")


def read_unix_cookie(base, directories):
    # The platform base can be redirected. Pin the application's own
    # directories and read the exact file whose metadata was validated.
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY
        parent = os.open(base, flags)
        stack.callback(os.close, parent)
        for name in directories:
            parent = os.open(name, flags | os.O_NOFOLLOW, dir_fd=parent)
            stack.callback(os.close, parent)
            info = os.fstat(parent)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise PermissionError("unsafe directory permissions")
        check_unix_cookie_file(os.stat("cookie", dir_fd=parent, follow_symlinks=False))
        fd = os.open("cookie", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        stack.callback(os.close, fd)
        check_unix_cookie_file(os.fstat(fd))
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(MAX_COOKIE_LINE_BYTES + 3)


def is_reparse_point(info):
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def read_windows_cookie(base, directories):
    # Like atc-rs, rely on the profile's Windows permissions and reject
    # junctions and other reparse points in the application's own path.
    path = base
    parents = []
    for name in directories:
        path = path / name
        info = path.lstat()
        if is_reparse_point(info) or not stat.S_ISDIR(info.st_mode):
            raise OSError(errno.EINVAL, "unsafe cookie directory")
        parents.append((path, info))
    path = path / "cookie"
    before = path.lstat()
    if is_reparse_point(before) or not stat.S_ISREG(before.st_mode):
        raise OSError(errno.EINVAL, "unsafe cookie path")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            is_reparse_point(opened)
            or not stat.S_ISREG(opened.st_mode)
            or not os.path.samestat(before, opened)
        ):
            raise OSError(errno.EINVAL, "cookie changed while opening")
        for parent, previous in parents:
            current = parent.lstat()
            if is_reparse_point(current) or not os.path.samestat(previous, current):
                raise OSError(errno.EINVAL, "cookie directory changed while opening")
        return stream.read(MAX_COOKIE_LINE_BYTES + 3)


def load_session_cookie():
    try:
        base, directories = cookie_location()
        reader = read_windows_cookie if sys.platform == "win32" else read_unix_cookie
        raw = reader(base, directories)
    except FileNotFoundError:
        return SessionCookie("missing")
    except PermissionError:
        return SessionCookie("permissions")
    except OSError as error:
        state = "path" if error.errno in (errno.EINVAL, errno.ELOOP, errno.ENOTDIR) else "read"
        return SessionCookie(state)
    except RuntimeError:
        # pathlib cannot determine the home directory.
        return SessionCookie("path")

    line = raw[:-2] if raw.endswith(b"\r\n") else raw.removesuffix(b"\n")
    if len(line) > MAX_COOKIE_LINE_BYTES or not COOKIE_LINE.fullmatch(line):
        return SessionCookie("format")
    return SessionCookie("loaded", line.decode("ascii"))
