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


class CreateMultishotLayout(BasicCreatorModel):
    shotParent: str = SettingsField(title="Shot Parent Folder")
    groupLoadedAssets: bool = SettingsField(title="Group Loaded Assets")
    task_type: list[str] = SettingsField(
        title="Task types",
        enum_resolver=task_types_enum
    )
    task_name: str = SettingsField(title="Task name (regex)")


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

    CreateWorkfile: CreateWorkfileModel = SettingsField(
        default_factory=CreateWorkfileModel,
        title="Create Workfile"
    )
    CreateLook: CreateLookModel = SettingsField(
        default_factory=CreateLookModel,
        title="Create Look"
    )
    CreateRender: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Render"
    )
    # "-" is not compatible in the new model
    CreateUnrealStaticMesh: CreateUnrealStaticMeshModel = SettingsField(
        default_factory=CreateUnrealStaticMeshModel,
        title="Create Unreal_Static Mesh"
    )
    # "-" is not compatible in the new model
    CreateUnrealSkeletalMesh: CreateUnrealSkeletalMeshModel = SettingsField(
        default_factory=CreateUnrealSkeletalMeshModel,
        title="Create Unreal_Skeletal Mesh"
    )
    CreateMultiverseLook: CreateMultiverseLookModel = SettingsField(
        default_factory=CreateMultiverseLookModel,
        title="Create Multiverse Look"
    )
    CreateAnimation: CreateAnimationModel = SettingsField(
        default_factory=CreateAnimationModel,
        title="Create Animation"
    )
    CreateModel: BasicExportMeshModel = SettingsField(
        default_factory=BasicExportMeshModel,
        title="Create Model"
    )
    CreatePointCache: CreatePointCacheModel = SettingsField(
        default_factory=CreatePointCacheModel,
        title="Create Point Cache"
    )
    CreateProxyAlembic: CreateProxyAlembicModel = SettingsField(
        default_factory=CreateProxyAlembicModel,
        title="Create Proxy Alembic"
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
    CreateAss: CreateAssModel = SettingsField(
        default_factory=CreateAssModel,
        title="Create Ass"
    )
    CreateAssembly: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Assembly"
    )
    CreateCamera: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Camera"
    )
    CreateLayout: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Layout"
    )
    CreateMayaScene: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Maya Scene"
    )
    CreateOxRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Ornatrix Rig"
    )
    CreateOxCache: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Ornatrix Cache"
    )
    CreateRenderSetup: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Render Setup"
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
    CreateVrayProxy: CreateVrayProxyModel = SettingsField(
        default_factory=CreateVrayProxyModel,
        title="Create VRay Proxy"
    )
    CreateVRayScene: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create VRay Scene"
    )
    CreateYetiRig: BasicCreatorModel = SettingsField(
        default_factory=BasicCreatorModel,
        title="Create Yeti Rig"
    )


DEFAULT_CREATORS_SETTINGS = {
    "use_entity_attributes_as_defaults": False,
    "CreateLook": {
        "enabled": True,
        "make_tx": True,
        "rs_tex": False,
        "include_texture_reference_objects": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateRender": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateUnrealStaticMesh": {
        "enabled": True,
        "default_variants": [
            "",
            "_Main"
        ],
        "static_mesh_prefix": "S",
        "collision_prefixes": [
            "UBX",
            "UCP",
            "USP",
            "UCX"
        ]
    },
    "CreateUnrealSkeletalMesh": {
        "enabled": True,
        "default_variants": [
            "Main",
        ],
        "joint_hints": "jnt_org"
    },
    "CreateMultiverseLook": {
        "enabled": True,
        "publish_mip_map": True
    },
    "CreateAnimation": {
        "include_parent_hierarchy": False,
        "include_user_defined_attributes": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateModel": {
        "enabled": True,
        "write_face_sets": True,
        "default_variants": [
            "Main",
            "Proxy",
            "Sculpt"
        ],
        "include_shaders": False,
    },
    "CreatePointCache": {
        "enabled": True,
        "include_user_defined_attributes": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateProxyAlembic": {
        "enabled": True,
        "write_color_sets": False,
        "write_face_sets": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateMultiverseUsd": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateMultiverseUsdComp": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateMultiverseUsdOver": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateAss": {
        "enabled": True,
        "default_variants": [
            "Main"
        ],
        "expandProcedurals": False,
        "motionBlur": True,
        "motionBlurKeys": 2,
        "motionBlurLength": 0.5,
        "maskOptions": False,
        "maskCamera": False,
        "maskLight": False,
        "maskShape": False,
        "maskShader": False,
        "maskOverride": False,
        "maskDriver": False,
        "maskFilter": False,
        "maskColor_manager": False,
        "maskOperator": False,
        "maskImager": False,
        "boundingBox": True,
        "compressed": False
    },
    "CreateAssembly": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateCamera": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateLayout": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateMayaScene": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateOxRig": {
        "enabled": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateOxCache": {
        "enabled": False,
        "default_variants": [
            "Main"
        ]
    },
    "CreateRenderSetup": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateReview": {
        "enabled": True,
        "default_variants": [
            "Main"
        ],
        "useMayaTimeline": True
    },
    "CreateRig": {
        "enabled": True,
        "default_variants": [
            "Main",
            "Sim",
            "Cloth"
        ]
    },
    "CreateSetDress": {
        "enabled": True,
        "exactSetMembersOnly": True,
        "shader": True,
        "default_variants": [
            "Main",
            "Anim"
        ]
    },
    "CreateVrayProxy": {
        "enabled": True,
        "vrmesh": True,
        "alembic": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateVRayScene": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    },
    "CreateYetiRig": {
        "enabled": True,
        "default_variants": [
            "Main"
        ]
    }
}
