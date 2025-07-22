import pyblish.api

from ayon_core.lib import version_up
from ayon_core.host import IWorkfileHost
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
        if hasattr(host, "save_workfile_with_context"):
            from ayon_core.host.interfaces import SaveWorkfileOptionalData
            host.save_workfile_with_context(
                filepath=new_filepath,
                folder_entity=context.data["folderEntity"],
                task_entity=context.data["taskEntity"],
                description="Incremented by publishing.",
                # Optimize the save by reducing needed queries for context
                prepared_data=SaveWorkfileOptionalData(
                    project_entity=context.data["projectEntity"],
                    project_settings=context.data["project_settings"],
                    anatomy=context.data["anatomy"],
                )
            )
        else:
            # Backwards compatibility before:
            # https://github.com/ynput/ayon-core/pull/1275
            host.save_workfile(new_filepath)