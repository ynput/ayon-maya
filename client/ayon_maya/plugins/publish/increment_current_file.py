import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.host import IWorkfileHost
from ayon_core.lib import version_up
from ayon_maya.api import plugin


class IncrementCurrentFileMaya(plugin.MayaContextPlugin):
    """Increment the current file.

    Saves the current maya scene with an increased version number."""

    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    families = ["*"]
    targets = ["local"]

    def process(self, context):
        try:
            from ayon_core.pipeline.workfile import save_next_version
            from ayon_core.host.interfaces import SaveWorkfileOptionalData
            save_next_version(
                description="Incremented by publishing.",
                # Optimize the save by reducing needed queries for context
                prepared_data=SaveWorkfileOptionalData(
                    project_entity=context.data["projectEntity"],
                    project_settings=context.data["project_settings"],
                    anatomy=context.data["anatomy"],
                )
            )
        except ImportError:
            # Backwards compatibility before ayon-core 1.5.0
            self.log.debug(
                "Using legacy `version_up`. Update AYON core addon to "
                "use newer `save_next_version` function."
            )
            current_filepath = context.data["currentFile"]
            new_filepath = version_up(current_filepath)
            host: IWorkfileHost = registered_host()
            host.save_workfile(new_filepath)
