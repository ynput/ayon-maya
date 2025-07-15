import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.lib import version_up
from ayon_maya.api import plugin


class IncrementCurrentFileMaya(plugin.MayaContextPlugin):
    """Increment the current file.

    Saves the current maya scene with an increased version number."""

    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    families = ["*"]
    optional = True
    targets = ["local"]

    def process(self, context):
        current_filepath = context.data["currentFile"]
        new_filepath = version_up(current_filepath)

        host = registered_host()
        host.save_workfile(new_filepath)
