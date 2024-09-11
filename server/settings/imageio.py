"""Providing models and setting values for image IO in Maya.

Note: Names were changed to get rid of the versions in class names.
"""
from pydantic import validator

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
)


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class WorkfileImageIOModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")
    renderSpace: str = SettingsField(title="Rendering Space")
    displayName: str = SettingsField(title="Display")
    viewName: str = SettingsField(title="View")


class ImageIOSettings(BaseSettingsModel):
    """Maya color management project settings."""

    _isGroup: bool = True
    activate_host_color_management: bool = SettingsField(
        True, title="Enable Color Management"
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )
    workfile: WorkfileImageIOModel = SettingsField(
        default_factory=WorkfileImageIOModel,
        title="Workfile"
    )


DEFAULT_IMAGEIO_SETTINGS = {
    "activate_host_color_management": True,
    "file_rules": {
        "activate_host_rules": False,
        "rules": []
    },
    "workfile": {
        "enabled": False,
        "renderSpace": "ACES - ACEScg",
        "displayName": "ACES",
        "viewName": "sRGB"
    }
}
