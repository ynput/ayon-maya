"""Host API required Work Files tool"""
import os
import contextlib
from maya import cmds

# Additional `cmds.file` flags used by `open_file`, see `open_file_options`
_open_file_options = {}


def file_extensions():
    return [".ma", ".mb"]


def has_unsaved_changes():
    return cmds.file(query=True, modified=True)


def save_file(filepath):
    cmds.file(rename=filepath)
    ext = os.path.splitext(filepath)[1]
    if ext == ".mb":
        file_type = "mayaBinary"
    else:
        file_type = "mayaAscii"
    cmds.file(save=True, type=file_type)


@contextlib.contextmanager
def open_file_options(**options):
    """Open files with additional `cmds.file` flags within this context.

    Example:
        >>> with open_file_options(loadReferenceDepth="none"):
        ...     open_file(filepath)

    Args:
        **options: Flags passed to `cmds.file` by `open_file`.

    """
    global _open_file_options
    previous_options = _open_file_options
    _open_file_options = {**previous_options, **options}
    try:
        yield
    finally:
        _open_file_options = previous_options


def open_file(filepath):
    return cmds.file(filepath, open=True, force=True, **_open_file_options)


def current_file():

    current_filepath = cmds.file(query=True, sceneName=True)
    if not current_filepath:
        return None

    return current_filepath
