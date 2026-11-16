from ayon_server.settings import BaseSettingsModel, SettingsField


class DirmapPathsSubmodel(BaseSettingsModel):
    _layout = "compact"
    source_path: list[str] = SettingsField(
        default_factory=list, title="Source Paths"
    )
    destination_path: list[str] = SettingsField(
        default_factory=list, title="Destination Paths"
    )


class DirmapModel(BaseSettingsModel):
    """Maya dirmap settings."""
    # _layout = "expanded"
    _isGroup: bool = True

    enabled: bool = SettingsField(title="enabled")
    # Use ${} placeholder instead of absolute value of a root in
    #   referenced filepaths.
    use_env_var_as_root: bool = SettingsField(
        title="Use env var placeholder in referenced paths"
    )
    paths: DirmapPathsSubmodel = SettingsField(
        default_factory=DirmapPathsSubmodel,
        title="Dirmap Paths"
    )


DEFAULT_DIRMAP_SETTINGS = {
    "use_env_var_as_root": False,
    "enabled": False,
    "paths": {
        "source-path": [],
        "destination-path": []
    }
}
