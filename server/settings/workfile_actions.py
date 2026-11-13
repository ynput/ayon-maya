from ayon_server.settings import BaseSettingsModel, SettingsField


class WorkfileActionEnabledModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")


class WorkfileActionsModel(BaseSettingsModel):
    OpenWithoutReferencesAction: WorkfileActionEnabledModel = SettingsField(
        default_factory=WorkfileActionEnabledModel,
        title="Open without references",
        description=(
            "Open the selected workfile from the Workfiles tool with all"
            " references unloaded."
        ),
    )


DEFAULT_WORKFILE_ACTIONS_SETTINGS = {
    "OpenWithoutReferencesAction": {
        "enabled": True
    },
}
