import os

from ayon_applications import PreLaunchHook, LaunchTypes


class MayaPreOpenWorkfilePostInitialization(PreLaunchHook):
    """Define whether open last workfile should run post initialize."""

    # Before AddLastWorkfileToLaunchArgs.
    order = 9
    app_groups = {"maya"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        # Do nothing if post workfile initialization is disabled.
        maya_settings = self.data["project_settings"]["maya"]
        if not maya_settings["open_workfile_post_initialization"]:
            return

        # Force disable the `AddLastWorkfileToLaunchArgs`.
        start_last_workfile = self.data.pop("start_last_workfile")

        # Ignore if there's no last workfile to start.
        if not start_last_workfile:
            return

        # Ignore if the last workfile path does not exist, this may be the case
        # when starting a context that has no workfiles yet.
        last_workfile_path: str = self.data.get("last_workfile_path")
        if not last_workfile_path or not os.path.exists(last_workfile_path):
            self.log.info("Current context does not have any workfile yet.")
            return

        self.log.debug("Opening workfile post initialization.")
        key = "AYON_OPEN_WORKFILE_POST_INITIALIZATION"
        self.launch_context.env[key] = "1"
