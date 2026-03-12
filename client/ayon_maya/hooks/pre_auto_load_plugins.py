from ayon_applications import PreLaunchHook, LaunchTypes


class MayaPreAutoLoadPlugins(PreLaunchHook):
    """Define -noAutoloadPlugins command flag.

    Note: This also relies on `pre_open_workfile_post_initialization.py` to
    ensure workfiles opening on launch open after initialization so we have
    the right control to define what plug-ins to load.
    """

    # Before AddLastWorkfileToLaunchArgs
    order = 9
    app_groups = {"maya"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        maya_settings = self.data["project_settings"]["maya"]
        enabled: bool = maya_settings["explicit_plugins_loading"]["enabled"]
        if not enabled:
            return

        self.log.debug("Explicit plugins loading.")
        self.launch_context.launch_args.append("-noAutoloadPlugins")
