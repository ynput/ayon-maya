"""Maya Addon Module"""
from typing import Any

from ayon_server.addons import BaseServerAddon

from .settings.main import MayaSettings, DEFAULT_MAYA_SETTING
from .settings.conversion import convert_settings_overrides


class MayaAddon(BaseServerAddon):
    settings_model = MayaSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_MAYA_SETTING)

    async def convert_settings_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        convert_settings_overrides(source_version, overrides)
        # Use super conversion
        return await super().convert_settings_overrides(
            source_version, overrides
        )

