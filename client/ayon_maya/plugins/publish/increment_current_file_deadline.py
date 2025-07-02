import pyblish.api

from ayon_core.lib import version_up
from ayon_core.host import IWorkfileHost
from ayon_core.host.interfaces import SaveWorkfileOptionalData
from ayon_core.pipeline import registered_host
from ayon_maya.api import plugin


class IncrementCurrentFileDeadline(plugin.MayaContextPlugin):
    """Saves the current maya scene with an increased version number."""

    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    families = ["workfile"]
    optional = True
    targets = ["local"]

    def process(self, context):
        current_filepath = context.data["currentFile"]
        new_filepath = version_up(current_filepath)

        host: IWorkfileHost = registered_host()
        host.save_workfile_with_context(
            filepath=new_filepath,
            folder_entity=context.data["folderEntity"],
            task_entity=context.data["taskEntity"],
            description=f"Incremented by publishing.",
            # Optimize the save by not reducing needed queries for context
            prepared_data=SaveWorkfileOptionalData(
                project_entity=context.data["projectEntity"],
                project_settings=context.data["project_settings"],
                anatomy=context.data["anatomy"],
            )
        )
