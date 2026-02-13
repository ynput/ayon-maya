import runpy
from pathlib import Path
from typing import Optional

from ayon_maya.api import plugin
from maya import cmds


class MatchmoveLoader(plugin.Loader):
    """
    This will run matchmove script to create track in scene.

    Supported script types are .py and .mel
    """

    product_base_types = {"matchmove"}
    product_types = product_base_types
    representations = {"py", "mel"}
    defaults = ["Camera", "Object", "Mocap"]

    label = "Run matchmove script"
    icon = "empire"
    color = "orange"

    def load(self,
             context: dict,
             name: Optional[str] = None,
             namespace: Optional[str] = None,
             options: Optional[dict] = None) -> None:
        """Load the matchmove script."""
        path = Path(self.filepath_from_context(context))
        if path.suffix.lower() == ".py":
            runpy.run_path(path.as_posix(), run_name="__main__")

        elif path.suffix.lower() == ".mel":
            cmds.file(
                path.as_posix(), type="mel",
                renameAll=True, i=True, ignoreVersion=True,
                importTimeRange="override",
                options="v=0;", pr=True, loadReferenceDepth="all")
        else:
            self.log.error("Unsupported script type %s", path.suffix)
