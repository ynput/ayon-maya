"""Public API

Anything that isn't defined here is INTERNAL and unreliable for external use.

"""

from .pipeline import (
    uninstall,

    ls,
    containerise,
    MayaHost,
)
from .plugin import (
    Creator,
    Loader
)

from .workio import (
    open_file,
    save_file,
    current_file,
    has_unsaved_changes,
    file_extensions,
    work_root
)

from .lib import (
    lsattr,
    lsattrs,
    read,

    apply_shaders,
    maintained_selection,
    suspended_refresh,

    unique_namespace,
)


__all__ = [
    "uninstall",

    "ls",
    "containerise",
    "MayaHost",

    "Creator",
    "Loader",

    # Workfiles API
    "open_file",
    "save_file",
    "current_file",
    "has_unsaved_changes",
    "file_extensions",
    "work_root",

    # Utility functions
    "lsattr",
    "lsattrs",
    "read",

    "unique_namespace",

    "apply_shaders",
    "maintained_selection",
    "suspended_refresh",

]

# Backwards API compatibility
open = open_file
save = save_file
