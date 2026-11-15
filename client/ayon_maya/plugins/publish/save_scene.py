import pyblish.api
from pathlib import Path
from ayon_core.pipeline.workfile.lock_workfile import (
    is_workfile_lock_enabled,
    remove_workfile_lock,
)
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.publish import PublishError
from ayon_maya.api import plugin


class SaveCurrentScene(plugin.MayaContextPlugin):
    """Save current scene."""

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    families = ["renderlayer", "workfile"]
    targets = ["local"]

    def process(self, context):
        host = registered_host()
        context_file = context.data["currentFile"]
        current_file = host.get_current_workfile()
        if Path(context_file) != Path(current_file):
            self.log.error(
                f"Current file in context: {context_file} "
                f"does not match the actual current file: {current_file}"
            )
            raise PublishError(
                "Current file in context does not match the actual current file."
            )
        # If file has no modifications, skip forcing a file save
        if not host.workfile_has_unsaved_changes():
            self.log.debug("Skipping file save as there "
                           "are no modifications..")
            return
        project_name = context.data["projectName"]
        project_settings = context.data["project_settings"]
        # remove lockfile before saving
        if is_workfile_lock_enabled("maya", project_name, project_settings):
            remove_workfile_lock(current_file)

        self.log.info(f"Saving current file: {current_file}")
        host.save_workfile(current_file)
