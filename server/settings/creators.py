from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    task_types_enum,
)


class CreateWorkfileModel(BaseSettingsModel):
    is_mandatory: bool = SettingsField(
        False,
        title="Mandatory workfile",
        description=(
            "Workfile cannot be disabled by user in UI."
            " Requires core addon 1.4.1 or newer."
        )
    )


class CreateLookModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    make_tx: bool = SettingsField(title="Make tx files")
    rs_tex: bool = SettingsField(title="Make Redshift texture files")
    include_texture_reference_objects: bool = SettingsField(title="Texture Reference Objects")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default Products"
    )


class BasicCreatorModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )


class CreateUnrealStaticMeshModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )
    static_mesh_prefix: str = SettingsField("S", title="Static Mesh Prefix")
    collision_prefixes: list[str] = SettingsField(
        default_factory=list,
        title="Collision Prefixes"
    )


class CreateUnrealSkeletalMeshModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default Products")
    joint_hints: str = SettingsField("jnt_org", title="Joint root hint")


class CreateMultiverseLookModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    publish_mip_map: bool = SettingsField(title="publish_mip_map")


class BasicExportMeshModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    write_face_sets: bool = SettingsField(title="Write Face Sets")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )
    include_shaders: bool = SettingsField(title="Include Shaders")


class CreateAnimationModel(BaseSettingsModel):
    include_parent_hierarchy: bool = SettingsField(
        title="Include Parent Hierarchy")
    include_user_defined_attributes: bool = SettingsField(
        title="Include User Defined Attributes")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )


class CreatePointCacheModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    include_user_defined_attributes: bool = SettingsField(
        title="Include User Defined Attributes"
    )
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )


class CreateProxyAlembicModel(BaseSettingsModel):
    enabled: bool = SettingsField(title="Enabled")
    write_color_sets: bool = SettingsField(title="Write Color Sets")
    write_face_sets: bool = SettingsField(title="Write Face Sets")
    default_variants: list[str] = SettingsField(
        default_factory=list,
        title="Default Products"
    )


class CreateAssModel(BasicCreatorModel):
    expandProcedurals: bool = SettingsField(title="Expand Procedurals")
    motionBlur: bool = SettingsField(title="Motion Blur")
    motionBlurKeys: int = SettingsField(2, title="Motion Blur Keys")
    motionBlurLength: float = SettingsField(0.5, title="Motion Blur Length")
    maskOptions: bool = SettingsField(title="Export Options")
    maskCamera: bool = SettingsField(title="Export Cameras")
    maskLight: bool = SettingsField(title="Export Lights")
    maskShape: bool = SettingsField(title="Export Shapes")
    maskShader: bool = SettingsField(title="Export Shaders")
    maskOverride: bool = SettingsField(title="Export Override Nodes")
    maskDriver: bool = SettingsField(title="Export Drivers")
    maskFilter: bool = SettingsField(title="Export Filters")
    maskColor_manager: bool = SettingsField(title="Export Color Managers")
    maskOperator: bool = SettingsField(title="Export Operators")
    maskImager: bool = SettingsField(title="Export Imagers")
    boundingBox: bool = SettingsField(title="Export Bounding Box")
    compressed: bool = SettingsField(title="Use gzip Compression (.ass.gz)")


class CreateReviewModel(BasicCreatorModel):
    useMayaTimeline: bool = SettingsField(
        title="Use Maya Timeline for Frame Range."
    )


class CreateVrayProxyModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    vrmesh: bool = SettingsField(title="VrMesh")
    alembic: bool = SettingsField(title="Alembic")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default Products")


class CreateSetDressModel(BaseSettingsModel):
    enabled: bool = SettingsField(True)
    exactSetMembersOnly: bool = SettingsField(title="Exact Set Members Only")
    shader: bool = SettingsField(title="Include shader")
    default_variants: list[str] = SettingsField(
        default_factory=list, title="Default Products")


class CreatorsModel(BaseSettingsModel):
    use_entity_attributes_as_defaults: bool = SettingsField(
        False,
        title="Use current context entity attributes as frame range defaults",
        description=(
            "For frame range attributes on the created instances, use the "
            "current context's task entity as the default value. When "
            "disabled it will default to Maya's current timeline."
        )
    )
    CreateAnimation: CreateAnimationModel = SettingsField(
        default_factory=CreateAnimationModel,
        title="Create Animation"
    )
    CreateAss: CreateAssModel = SettingsField(
        default_factory=CreateAssModel,
        title="Create Arnold Scene Source",
    )
    CreateAssembly: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Assembly"
    )
    CreateCamera: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Camera"
    )
    CreateCameraRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Camera Rig"
    )
    CreateLayout: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Layout"
    )
    CreateLook: CreateLookModel = SettingsField(
        default_factory=CreateLookModel,
        title="Create Look"
    )
    CreateMatchmove: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Matchmove"
    )
    CreateMayaScene: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Maya Scene"
    )
    CreateMayaUsd: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Maya USD"
    )
    CreateMayaUsdLayer: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Maya USD Export Layer"
    )
    CreateModel: BasicExportMeshModel = SettingsField(
        default_factory=BasicExportMeshModel,
        title="Create Model"
    )
    CreateMultishotLayout: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Multi-shot Layout"
    )
    CreateMultiverseLook: CreateMultiverseLookModel = SettingsField(
        default_factory=CreateMultiverseLookModel,
        title="Create Multiverse Look"
    )
    CreateMultiverseUsd: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Multiverse USD"
    )
    CreateMultiverseUsdComp: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Multiverse USD Composition"
    )
    CreateMultiverseUsdOver: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Multiverse USD Override"
    )
    CreateOxCache: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Ornatrix Cache"
    )
    CreateOxRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Ornatrix Rig"
    )
    CreatePointCache: CreatePointCacheModel = SettingsField(
        default_factory=CreatePointCacheModel,
        title="Create Point Cache"
    )
    CreateProxyAlembic: CreateProxyAlembicModel = SettingsField(
        default_factory=CreateProxyAlembicModel,
        title="Create Proxy Alembic"
    )
    CreateRedshiftProxy: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Redshift Proxy"
    )
    CreateRender: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Render"
    )
    CreateRenderSetup: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Render Setup Preset"
    )
    CreateReview: CreateReviewModel = SettingsField(
        default_factory=CreateReviewModel,
        title="Create Review"
    )
    CreateRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Rig"
    )
    CreateSetDress: CreateSetDressModel = SettingsField(
        default_factory=CreateSetDressModel,
        title="Create Set Dress"
    )
    CreateUnrealSkeletalMesh: CreateUnrealSkeletalMeshModel = SettingsField(
        default_factory=CreateUnrealSkeletalMeshModel,
        title="Create Unreal- Skeletal Mesh"
    )
    CreateUnrealStaticMesh: CreateUnrealStaticMeshModel = SettingsField(
        default_factory=CreateUnrealStaticMeshModel,
        title="Create Unreal - Static Mesh"
    )
    CreateUnrealYetiCache: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Unreal - Yeti Cache"
    )
    CreateVrayProxy: CreateVrayProxyModel = SettingsField(
        default_factory=CreateVrayProxyModel,
        title="Create VRay Proxy"
    )
    CreateVRayScene: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create VRay Scene"
    )
    CreateWorkfile: CreateWorkfileModel = SettingsField(
        default_factory=CreateWorkfileModel,
        title="Create Workfile"
    )
    CreateXgen: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Xgen"
    )
    CreateYetiCache: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Yeti Cache"
    )
    CreateYetiRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Yeti Rig"
    )


DEFAULT_CREATORS_SETTINGS = {
    "use_entity_attributes_as_defaults": False,
    "CreateAnimation": {
        "default_variants": ["Main"],
        "include_parent_hierarchy": False,
        "include_user_defined_attributes": False,
    },
    "CreateAss": {
        "boundingBox": True,
        "compressed": False,
        "default_variants": ["Main"],
        "enabled": True,
        "expandProcedurals": False,
        "maskCamera": False,
        "maskColor_manager": False,
        "maskDriver": False,
        "maskFilter": False,
        "maskImager": False,
        "maskLight": False,
        "maskOperator": False,
        "maskOptions": False,
        "maskOverride": False,
        "maskShader": False,
        "maskShape": False,
        "motionBlur": True,
        "motionBlurKeys": 2,
        "motionBlurLength": 0.5,
    },
    "CreateAssembly": {"default_variants": ["Main"], "enabled": True},
    "CreateCamera": {"default_variants": ["Main"], "enabled": True},
    "CreateCameraRig": {"default_variants": ["Main"], "enabled": True},
    "CreateLayout": {"default_variants": ["Main"], "enabled": True},
    "CreateLook": {
        "default_variants": ["Main"],
        "enabled": True,
        "include_texture_reference_objects": False,
        "make_tx": True,
        "rs_tex": False,
    },
    "CreateMatchmove": {"default_variants": ["Main"], "enabled": True},
    "CreateMayaScene": {"default_variants": ["Main"], "enabled": True},
    "CreateMayaUsd": {"default_variants": ["Main"], "enabled": True},
    "CreateMayaUsdLayer": {"default_variants": ["Main"], "enabled": True},
    "CreateModel": {
        "default_variants": ["Main", "Proxy", "Sculpt"],
        "enabled": True,
        "include_shaders": False,
        "write_face_sets": True,
    },
    "CreateMultishotLayout": {"default_variants": ["Main"], "enabled": True},
    "CreateMultiverseLook": {"enabled": True, "publish_mip_map": True},
    "CreateMultiverseUsd": {"default_variants": ["Main"], "enabled": True},
    "CreateMultiverseUsdComp": {"default_variants": ["Main"], "enabled": True},
    "CreateMultiverseUsdOver": {"default_variants": ["Main"], "enabled": True},
    "CreateOxCache": {"default_variants": ["Main"], "enabled": False},
    "CreateOxRig": {"default_variants": ["Main"], "enabled": False},
    "CreatePointCache": {
        "default_variants": ["Main"],
        "enabled": True,
        "include_user_defined_attributes": False,
    },
    "CreateProxyAlembic": {
        "default_variants": ["Main"],
        "enabled": True,
        "write_color_sets": False,
        "write_face_sets": False,
    },
    "CreateRender": {"default_variants": ["Main"], "enabled": True},
    "CreateRenderSetup": {"default_variants": ["Main"], "enabled": True},
    "CreateReview": {
        "default_variants": ["Main"],
        "enabled": True,
        "useMayaTimeline": True,
    },
    "CreateRig": {
        "default_variants": ["Main", "Sim", "Cloth"],
        "enabled": True,
    },
    "CreateSetDress": {
        "default_variants": ["Main", "Anim"],
        "enabled": True,
        "exactSetMembersOnly": True,
        "shader": True,
    },
    "CreateUnrealSkeletalMesh": {
        "default_variants": ["Main"],
        "enabled": True,
        "joint_hints": "jnt_org",
    },
    "CreateUnrealStaticMesh": {
        "collision_prefixes": ["UBX", "UCP", "USP", "UCX"],
        "default_variants": ["", "_Main"],
        "enabled": True,
        "static_mesh_prefix": "S",
    },
    "CreateUnrealYetiCache": {
        "default_variants": ["Main", "Sim", "Cloth"],
        "enabled": True,
    },
    "CreateVrayProxy": {
        "alembic": True,
        "default_variants": ["Main"],
        "enabled": True,
        "vrmesh": True,
    },
    "CreateVRayScene": {"default_variants": ["Main"], "enabled": True},
    "CreateYetiRig": {"default_variants": ["Main"], "enabled": True},
}
