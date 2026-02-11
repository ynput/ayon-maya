from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
)


class ContextItemModel(BaseSettingsModel):
    _layout = "expanded"
    product_name_filters: list[str] = SettingsField(
        default_factory=list, title="Product name Filters")
    product_base_types: list[str] = SettingsField(
        default_factory=list, title="Product base types")
    repre_names: list[str] = SettingsField(
        default_factory=list, title="Repre Names")
    loaders: list[str] = SettingsField(
        default_factory=list, title="Loaders")


class WorkfileSettingModel(BaseSettingsModel):
    _layout = "expanded"
    task_types: list[str] = SettingsField(
        default_factory=list,
        enum_resolver=task_types_enum,
        title="Task types")
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names")
    current_context: list[ContextItemModel] = SettingsField(
        default_factory=list,
        title="Current Context")
    linked_folders: list[ContextItemModel] = SettingsField(
        default_factory=list,
        title="Linked Assets")


class ProfilesModel(BaseSettingsModel):
    profiles: list[WorkfileSettingModel] = SettingsField(
        default_factory=list,
        title="Profiles"
    )


DEFAULT_WORKFILE_SETTING = {
    "profiles": [
        {
            "task_types": [],
            "task_names": [
                "Lighting"
            ],
            "current_context": [
                {
                    "product_name_filters": [
                        ".+[Mm]ain"
                    ],
                    "product_base_types": [
                        "model"
                    ],
                    "repre_names": [
                        "abc",
                        "ma"
                    ],
                    "loaders": [
                        "ReferenceLoader"
                    ]
                },
                {
                    "product_name_filters": [],
                    "product_base_types": [
                        "animation",
                        "pointcache",
                        "proxyAbc"
                    ],
                    "repre_names": [
                        "abc"
                    ],
                    "loaders": [
                        "ReferenceLoader"
                    ]
                },
                {
                    "product_name_filters": [],
                    "product_base_types": [
                        "rendersetup"
                    ],
                    "repre_names": [
                        "json"
                    ],
                    "loaders": [
                        "RenderSetupLoader"
                    ]
                },
                {
                    "product_name_filters": [],
                    "product_base_types": [
                        "camera"
                    ],
                    "repre_names": [
                        "abc"
                    ],
                    "loaders": [
                        "ReferenceLoader"
                    ]
                }
            ],
            "linked_folders": [
                {
                    "product_name_filters": [],
                    "product_base_types": [
                        "setdress"
                    ],
                    "repre_names": [
                        "ma"
                    ],
                    "loaders": [
                        "ReferenceLoader"
                    ]
                },
                {
                    "product_name_filters": [],
                    "product_base_types": [
                        "ArnoldStandin"
                    ],
                    "repre_names": [
                        "ass"
                    ],
                    "loaders": [
                        "assLoader"
                    ]
                }
            ]
        }
    ]
}
