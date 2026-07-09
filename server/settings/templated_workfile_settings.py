from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
)


class WorkfileBuildProfilesModel(BaseSettingsModel):
    _layout = "expanded"
    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_names: list[str] = SettingsField(
        default_factory=list, title="Task names"
    )
    path: str = SettingsField("", title="Path to template")
    keep_placeholder: bool = SettingsField(
        False,
        title="Keep placeholders")
    create_first_version: bool = SettingsField(
        True,
        title="Create first version"
    )
    execute_on_new_file: bool = SettingsField(
        False,
        title="Always apply to empty scene"
    )
    execute_on_app_launch: bool = SettingsField(
        False,
        title="Apply on application launch"
    )


class TemplatedProfilesModel(BaseSettingsModel):
    profiles: list[WorkfileBuildProfilesModel] = SettingsField(
        default_factory=list,
        title="Profiles"
    )


DEFAULT_TEMPLATED_WORKFILE_SETTINGS = {
    "profiles": []
}
