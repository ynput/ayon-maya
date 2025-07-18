from pydantic import validator
from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    ensure_unique_names,
)
from .imageio import ImageIOSettings, DEFAULT_IMAGEIO_SETTINGS
from .dirmap import DirmapModel, DEFAULT_DIRMAP_SETTINGS
from .include_handles import IncludeHandlesModel, DEFAULT_INCLUDE_HANDLES
from .explicit_plugins_loading import (
    ExplicitPluginsLoadingModel, DEFAULT_EXPLITCIT_PLUGINS_LOADING_SETTINGS
)
from .scriptsmenu import ScriptsmenuModel, DEFAULT_SCRIPTSMENU_SETTINGS
from .render_settings import RenderSettingsModel, DEFAULT_RENDER_SETTINGS
from .creators import CreatorsModel, DEFAULT_CREATORS_SETTINGS
from .publishers import PublishersModel, DEFAULT_PUBLISH_SETTINGS
from .loaders import LoadersModel, DEFAULT_LOADERS_SETTING
from .workfile_build_settings import ProfilesModel, DEFAULT_WORKFILE_SETTING
from .templated_workfile_settings import (
    TemplatedProfilesModel, DEFAULT_TEMPLATED_WORKFILE_SETTINGS
)


def linear_unit_enum():
    """Get linear units enumerator."""
    return [
        {"label": "millimeter", "value": "mm"},
        {"label": "centimeter", "value": "cm"},
        {"label": "meter", "value": "m"},
        {"label": "kilometer", "value": "km"},
        {"label": "inch", "value": "in"},
        {"label": "foot", "value": "ft"},
        {"label": "yard", "value": "yd"},
        {"label": "mile", "value": "mi"}
    ]


def angular_unit_enum():
    """Get angular units enumerator."""
    return [
        {"label": "degree", "value": "deg"},
        {"label": "radian", "value": "rad"},
    ]


def maya_file_extensions_enum():
    return [
        {"value": "ma", "label": "Maya Ascii (.ma)"},
        {"value": "mb", "label": "Maya Binary (.mb)"}
    ]


class UnitScaleModel(BaseSettingsModel):
    _isGroup: bool = True
    linear_units: str = SettingsField(
        enum_resolver=linear_unit_enum, title="Linear Units"
    )
    angular_units: str = SettingsField(
        enum_resolver=angular_unit_enum, title="Angular units"
    )

class ExtMappingItemModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(title="Product type")
    value: str = SettingsField(
        title="Extension", enum_resolver=maya_file_extensions_enum
    )


class MayaSettings(BaseSettingsModel):
    """Maya Project Settings."""

    use_cbid_workflow: bool = SettingsField(
        True, title="Use cbId workflow",
        description=(
            "When enabled, a per node `cbId` identifier will be created and "
            "validated for many product types. This is then used for look "
            "publishing and many others. By disabling this, the `cbId` "
            "attribute will still be created on scene save but it will not "
            "be validated."))

    open_workfile_post_initialization: bool = SettingsField(
        True, title="Open Workfile Post Initialization")
    explicit_plugins_loading: ExplicitPluginsLoadingModel = SettingsField(
        default_factory=ExplicitPluginsLoadingModel,
        title="Explicit Plugins Loading")
    imageio: ImageIOSettings = SettingsField(
        default_factory=ImageIOSettings, title="Color Management (imageio)")
    mel_workspace: str = SettingsField(
        title="Maya MEL Workspace", widget="textarea"
    )
    ext_mapping: list[ExtMappingItemModel] = SettingsField(
        default_factory=list, title="Extension Mapping")
    scene_units: UnitScaleModel = SettingsField(
        default_factory=UnitScaleModel,
        title="Scene Units",
        description="Set preferred Maya Scene Units"
    )
    dirmap: DirmapModel = SettingsField(
        default_factory=DirmapModel, title="Maya dirmap Settings")
    include_handles: IncludeHandlesModel = SettingsField(
        default_factory=IncludeHandlesModel,
        title="Include/Exclude Handles in default playback & render range"
    )
    scriptsmenu: ScriptsmenuModel = SettingsField(
        default_factory=ScriptsmenuModel,
        title="Scriptsmenu Settings"
    )
    render_settings: RenderSettingsModel = SettingsField(
        default_factory=RenderSettingsModel, title="Render Settings")
    create: CreatorsModel = SettingsField(
        default_factory=CreatorsModel, title="Creators")
    publish: PublishersModel = SettingsField(
        default_factory=PublishersModel, title="Publishers")
    load: LoadersModel = SettingsField(
        default_factory=LoadersModel, title="Loaders")
    workfile_build: ProfilesModel = SettingsField(
        default_factory=ProfilesModel, title="Workfile Build Settings")
    templated_workfile_build: TemplatedProfilesModel = SettingsField(
        default_factory=TemplatedProfilesModel,
        title="Templated Workfile Build Settings")

    @validator("ext_mapping")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


DEFAULT_MEL_WORKSPACE_SETTINGS = "\n".join((
    'workspace -fr "shaders" "renderData/shaders";',
    'workspace -fr "images" "renders/maya";',
    'workspace -fr "particles" "particles";',
    'workspace -fr "mayaAscii" "";',
    'workspace -fr "mayaBinary" "";',
    'workspace -fr "scene" "";',
    'workspace -fr "alembicCache" "cache/alembic";',
    'workspace -fr "renderData" "renderData";',
    'workspace -fr "sourceImages" "sourceimages";',
    'workspace -fr "fileCache" "cache/nCache";',
    'workspace -fr "autoSave" "autosave";',
    '',
))

DEFAULT_MAYA_SETTING = {
    "use_cbid_workflow": True,
    "open_workfile_post_initialization": True,
    "explicit_plugins_loading": DEFAULT_EXPLITCIT_PLUGINS_LOADING_SETTINGS,
    "imageio": DEFAULT_IMAGEIO_SETTINGS,
    "mel_workspace": DEFAULT_MEL_WORKSPACE_SETTINGS,
    "ext_mapping": [
        {"name": "model", "value": "ma"},
        {"name": "mayaScene", "value": "ma"},
        {"name": "camera", "value": "ma"},
        {"name": "rig", "value": "ma"},
        {"name": "workfile", "value": "ma"},
        {"name": "yetiRig", "value": "ma"},
        {"name": "setdress", "value": "ma"},
        {"name": "layout", "value": "ma"},
        {"name": "camerarig", "value": "ma"},
    ],
    "scene_units": {
        "linear_units": "cm",
        "angular_units": "deg",
    },
    # `dirmap` was originally with dash - `maya-dirmap`
    "dirmap": DEFAULT_DIRMAP_SETTINGS,
    "include_handles": DEFAULT_INCLUDE_HANDLES,
    "scriptsmenu": DEFAULT_SCRIPTSMENU_SETTINGS,
    "render_settings": DEFAULT_RENDER_SETTINGS,
    "create": DEFAULT_CREATORS_SETTINGS,
    "publish": DEFAULT_PUBLISH_SETTINGS,
    "load": DEFAULT_LOADERS_SETTING,
    "workfile_build": DEFAULT_WORKFILE_SETTING,
    "templated_workfile_build": DEFAULT_TEMPLATED_WORKFILE_SETTINGS
}
