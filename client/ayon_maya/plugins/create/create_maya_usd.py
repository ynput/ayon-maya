from ayon_maya.api import plugin, lib
from ayon_core.lib import (
    BoolDef,
    EnumDef,
    TextDef
)

from maya import cmds


class CreateMayaUsd(plugin.MayaCreator):
    """Create Maya USD Export from maya scene objects"""

    identifier = "io.openpype.creators.maya.mayausd"
    label = "Maya USD"
    product_type = "usd"
    icon = "cubes"
    description = "Create Maya USD Export"
    cache = {}

    allow_animation = True

    def register_callbacks(self):
        self.create_context.add_value_changed_callback(self.on_values_changed)

    def on_values_changed(self, event):
        """Update instance attribute definitions on attribute changes."""

        for instance_change in event["changes"]:
            # First check if there's a change we want to respond to
            instance = instance_change["instance"]
            if instance is None:
                # Change is on context
                continue

            if instance["creator_identifier"] != self.identifier:
                continue

            value_changes = instance_change["changes"]
            if (
                "exportAnimationData"
                not in value_changes.get("creator_attributes", {})
            ):
                continue

            # Update the attribute definitions
            new_attrs = self.get_attr_defs_for_instance(instance)
            instance.set_create_attr_defs(new_attrs)

    def get_publish_families(self):
        return ["usd", "mayaUsd"]

    def get_attr_defs_for_instance(self, instance):

        if "jobContextItems" not in self.cache:
            # Query once instead of per instance
            job_context_items = {}
            try:
                cmds.loadPlugin("mayaUsdPlugin", quiet=True)
                job_context_items = {
                    cmds.mayaUSDListJobContexts(jobContext=name): name
                    for name in cmds.mayaUSDListJobContexts(export=True) or []
                }
            except RuntimeError:
                # Likely `mayaUsdPlugin` plug-in not available
                self.log.warning("Unable to retrieve available job "
                                 "contexts for `mayaUsdPlugin` exports")

            if not job_context_items:
                # enumdef multiselection may not be empty
                job_context_items = ["<placeholder; do not use>"]

            self.cache["jobContextItems"] = job_context_items

        defs = []
        if self.allow_animation:
            defs.append(
                BoolDef("exportAnimationData",
                        label="Export Animation Data",
                        tooltip="When disabled no frame range is exported and "
                                "only the start frame is used to define the "
                                "static export frame.",
                        default=True)
            )
            defs.extend(lib.collect_animation_defs(
                create_context=self.create_context))
        defs.extend([
            EnumDef("defaultUSDFormat",
                    label="File format",
                    items={
                        "usdc": "Binary",
                        "usda": "ASCII"
                    },
                    default="usdc"),
            # TODO: Remove note from tooltip when issue is resolved, see:
            #  https://github.com/Autodesk/maya-usd/issues/3389
            BoolDef("exportRoots",
                    label="Export as roots",
                    tooltip=(
                        "Export the members of the object sets without "
                        "their parents.\n"
                        "Note: There's an export bug that when this is "
                        "enabled MayaUsd fails to export instance meshes"
                    ),
                    default=True),
            BoolDef("stripNamespaces",
                    label="Strip Namespaces",
                    tooltip=(
                        "Remove namespaces during export. By default, "
                        "namespaces are exported to the USD file in the "
                        "following format: nameSpaceExample_pPlatonic1"
                    ),
                    default=True),
            BoolDef("mergeTransformAndShape",
                    label="Merge Transform and Shape",
                    tooltip=(
                        "Combine Maya transform and shape into a single USD"
                        "prim that has transform and geometry, for all"
                        " \"geometric primitives\" (gprims).\n"
                        "This results in smaller and faster scenes. Gprims "
                        "will be \"unpacked\" back into transform and shape "
                        "nodes when imported into Maya from USD."
                    ),
                    default=True),
            BoolDef("includeUserDefinedAttributes",
                    label="Include User Defined Attributes",
                    tooltip=(
                        "Whether to include all custom maya attributes found "
                        "on nodes as metadata (userProperties) in USD."
                    ),
                    default=False),
            TextDef("attr",
                    label="Custom Attributes",
                    default="",
                    placeholder="attr1, attr2"),
            TextDef("attrPrefix",
                    label="Custom Attributes Prefix",
                    default="",
                    placeholder="prefix1, prefix2"),
            EnumDef("jobContext",
                    label="Job Context",
                    items=self.cache["jobContextItems"],
                    tooltip=(
                        "Specifies an additional export context to handle.\n"
                        "These usually contain extra schemas, primitives,\n"
                        "and materials that are to be exported for a "
                        "specific\ntask, a target renderer for example."
                    ),
                    multiselection=True),
        ])

        # Disable the frame range attributes if `exportAnimationData` is
        # disabled.
        use_anim = instance["creator_attributes"].get(
            "exportAnimationData", True)
        if not use_anim:
            anim_defs = {
                "frameStart", "frameEnd", "handleStart", "handleEnd", "step"
            }
            for attr_def in defs:
                if attr_def.key in anim_defs:
                    attr_def.disabled = True

        return defs

    def get_pre_create_attr_defs(self):
        defs = super().get_pre_create_attr_defs()
        defs.extend([
            BoolDef("createAssetTemplateHierarchy",
                    label="Create asset hierarchy",
                    tooltip=(
                        "Create the root hierarchy for '{folder_name}/geo'"
                        " as per the USD Asset Structure guidelines to"
                        " add your geometry into."
                    ),
                    default=False)
        ])
        return defs

    def _create_template_hierarchy(self, folder_name, variant):
        """Create the asset root template to hold the geo for the usd asset.

        Args:
            folder_name: Asset name to use for the group
            variant: Variant name to use as namespace.
                This is needed so separate asset contributions can be
                correctly created from a single scene.

        Returns:
            list: The root node and geometry group.

        """

        def set_usd_type(node, value):
            attr = "USD_typeName"
            if not cmds.attributeQuery(attr, node=node, exists=True):
                cmds.addAttr(node, ln=attr, dt="string")
            cmds.setAttr(f"{node}.{attr}", value, type="string")

        # Ensure simple unique namespace (add trailing number)
        namespace = variant
        name = f"{namespace}:{folder_name}"
        i = 1
        while cmds.objExists(name):
            name = f"{namespace}{i}:{folder_name}"
            i += 1

        # Define template hierarchy {folder_name}/geo
        root = cmds.createNode("transform",
                               name=name,
                               skipSelect=True)
        geo = cmds.createNode("transform",
                              name="geo",
                              parent=root,
                              skipSelect=True)
        set_usd_type(geo, "Scope")
        # Lock + hide transformations since we're exporting as Scope
        for attr in ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"]:
            cmds.setAttr(f"{geo}.{attr}", lock=True, keyable=False)

        return [root, geo]

    def create(self, product_name, instance_data, pre_create_data):

        # Create template hierarchy
        if pre_create_data.get("createAssetTemplateHierarchy", False):
            members = []
            if pre_create_data.get("use_selection"):
                members = cmds.ls(selection=True,
                                  long=True,
                                  type="dagNode")

            folder_path = instance_data["folderPath"]
            folder_name = folder_path.rsplit("/", 1)[-1]

            root, geo = self._create_template_hierarchy(
                folder_name=folder_name,
                variant=instance_data["variant"]
            )

            if members:
                cmds.parent(members, geo)

            # Select root and enable selection just so parent class'
            # create adds it to the created instance
            cmds.select(root, replace=True, noExpand=True)

        super().create(product_name, instance_data, pre_create_data)


class CreateMayaUsdModel(CreateMayaUsd):
    identifier = "io.ayon.creators.maya.mayausd.model"
    label = "Maya USD: Model"
    product_type = "model"
    icon = "cubes"
    description = "Create Model with Maya USD Export"

    allow_animation = False

    def get_pre_create_attr_defs(self):
        attr_defs = super().get_pre_create_attr_defs()

        # Enable by default
        for attr_def in attr_defs:
            if attr_def.key == "createAssetTemplateHierarchy":
                attr_def.default = True

        return attr_defs
