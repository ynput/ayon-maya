from collections import namedtuple
from typing import Optional, TYPE_CHECKING

from maya import cmds

from ayon_core.pipeline.create import CreatedInstance
from ayon_maya.api import lib, plugin

from ayon_core.lib import (
    BoolDef,
    NumberDef,
)

if TYPE_CHECKING:
    from pxr import Usd
    import ufe.PyUfe


def _get_animation_attr_defs(create_context):
    """Get Animation generic definitions."""
    defs = lib.collect_animation_defs(create_context=create_context)
    defs.extend(
        [
            BoolDef("farm", label="Submit to Farm"),
            NumberDef("priority", label="Farm job Priority", default=50),
            BoolDef("refresh", label="Refresh viewport during export"),
            BoolDef(
                "includeParentHierarchy",
                label="Include Parent Hierarchy",
                tooltip=(
                    "Whether to include parent hierarchy of nodes in the "
                    "publish instance."
                )
            ),
            BoolDef(
                "includeUserDefinedAttributes",
                label="Include User Defined Attributes",
                tooltip=(
                    "Whether to include all custom maya attributes found "
                    "on nodes as attributes in the Alembic data."
                )
            ),
        ]
    )

    return defs


def convert_legacy_alembic_creator_attributes(node_data, class_name):
    """This is a legacy transfer of creator attributes to publish attributes
    for ExtractAlembic/ExtractAnimation plugin.
    """
    publish_attributes = node_data["publish_attributes"]

    if class_name in publish_attributes:
        return node_data

    attributes = [
        "attr",
        "attrPrefix",
        "visibleOnly",
        "writeColorSets",
        "writeFaceSets",
        "writeNormals",
        "renderableOnly",
        "visibleOnly",
        "worldSpace",
        "renderableOnly"
    ]
    plugin_attributes = {}
    for attr in attributes:
        if attr not in node_data["creator_attributes"]:
            continue
        value = node_data["creator_attributes"].pop(attr)

        plugin_attributes[attr] = value

    publish_attributes[class_name] = plugin_attributes

    return node_data


class CreateAnimation(plugin.MayaHiddenCreator):
    """Animation output for character rigs

    We hide the animation creator from the UI since the creation of it is
    automated upon loading a rig. There's an inventory action to recreate it
    for loaded rigs if by chance someone deleted the animation instance.
    """

    identifier = "io.openpype.creators.maya.animation"
    name = "animationDefault"
    label = "Animation"
    product_type = "animation"
    icon = "male"

    write_color_sets = False
    write_face_sets = False
    include_parent_hierarchy = False
    include_user_defined_attributes = False

    def read_instance_node(self, node):
        node_data = super(CreateAnimation, self).read_instance_node(node)
        node_data = convert_legacy_alembic_creator_attributes(
            node_data, "ExtractAnimation"
        )
        return node_data

    def get_instance_attr_defs(self):
        return _get_animation_attr_defs(self.create_context)


class CreatePointCache(plugin.MayaCreator):
    """Alembic pointcache for animated data"""

    identifier = "io.openpype.creators.maya.pointcache"
    label = "Pointcache"
    product_type = "pointcache"
    icon = "gears"
    write_color_sets = False
    write_face_sets = False
    include_user_defined_attributes = False

    def read_instance_node(self, node):
        node_data = super(CreatePointCache, self).read_instance_node(node)
        node_data = convert_legacy_alembic_creator_attributes(
            node_data, "ExtractAlembic"
        )
        return node_data

    def get_instance_attr_defs(self):
        return _get_animation_attr_defs(self.create_context)

    def create(self, product_name, instance_data, pre_create_data):
        instance = super(CreatePointCache, self).create(
            product_name, instance_data, pre_create_data
        )
        instance_node = instance.get("instance_node")

        # For Arnold standin proxy
        proxy_set = cmds.sets(name=instance_node + "_proxy_SET", empty=True)
        cmds.sets(proxy_set, forceElement=instance_node)


class PulledInfo:
    """Pulled Info result from `mayaUsdUtils.getPulledInfo`"""
    def __init__(
        self,
        full_dag_path: str,
        maya_item: "ufe.PyUfe.SceneItem",
        pulled_path: "ufe.PyUfe.Path",
        prim: "Usd.Prim"
    ):
        self.full_dag_path: str = full_dag_path
        self.maya_item: "ufe.PyUfe.SceneItem" = maya_item
        self.pulled_path: "ufe.PyUfe.Path" = pulled_path
        self.prim: "Usd.Prim" = prim


class CreateAnimationUSD(plugin.MayaAutoCreator):
    """Animation output for character rigs loaded via Maya Usd Proxy shape."""

    identifier = "io.openpype.creators.maya.animation_usd"
    name = "animationDefault"
    label = "Animation"
    product_type = "animation"
    icon = "male"

    write_color_sets = False
    write_face_sets = False
    include_parent_hierarchy = False
    include_user_defined_attributes = False

    def create(self):
        # Do nothing - all logic lives in `collect_instances`
        pass

    def collect_instances(self):
        """Collect the USD animation instance from the scene.

        Search for all loaded MayaReference prims that are currently in an
        editable state and include any persisted instances (objectSets) that
        were previously collected and store in the scene.

        For each, also collect the transient data that stores what their
        individual prim path is in the USD Stage.
        """

        # Detect already persisted instances
        super().collect_instances()

        # Detect any new references that do not have a matching object set
        # yet. First we collect all members of the registered object sets so
        # we can easily filter those already registered.
        existing_instances = [
            instance for instance in self.create_context.instances
            if instance.creator_identifier == self.identifier
        ]
        for instance in existing_instances:
            self._collect_transient_data(instance)

        object_sets = [
            instance.data["instance_node"]
            for instance in existing_instances
        ]
        members_to_object_set = {}
        for object_set in object_sets:
            members = cmds.sets(object_set, query=True) or []
            for member in members:
                members_to_object_set[member] = object_set

        for ref in cmds.ls(type="reference"):
            if ref in members_to_object_set:
                continue

            created_instance = self._process_reference_node(ref)
            if created_instance:
                self._collect_transient_data(created_instance)

    def _process_reference_node(self, reference_node: str):

        dag_path = self.get_pulled_maya_reference_dag_path(reference_node)
        if not dag_path:
            return

        # Check if it is a published rig inside the USD file
        # For now we assume it is if the reference has
        # `out_SET` and `controls_SET` object sets
        # TODO: Perform a more explicit check than this
        members = cmds.referenceQuery(reference_node, nodes=True)
        object_sets = cmds.ls(members, type="objectSet")
        if not any(s.endswith("out_SET") for s in object_sets):
            return
        if not any(s.endswith("controls_SET") for s in object_sets):
            return

        variant: str = cmds.referenceQuery(reference_node,
                                           namespace=True).strip(":")
        product_name = self.get_product_name(
            project_name=self.create_context.get_current_project_name(),
            folder_entity=self.create_context.get_current_folder_entity(),
            task_entity=self.create_context.get_current_task_entity(),
            variant=variant,
            project_entity=self.create_context.get_current_project_entity(),
            # noqa
        )

        # Generate instance node data
        node_data = {
            "id": "pyblish.avalon.instance",
            "creator_identifier": self.identifier,
            "variant": variant,
            "folderPath": self.create_context.get_current_folder_path(),
            "task": self.create_context.get_current_task_name(),
            "productName": product_name,
            "productType": "animation",
            "creator_attributes": {},
            "publish_attributes": {},
        }

        # Collect transient data of where the asset is in the USD Stage
        # hierarchy and the reference node belonging to it.
        created_instance = CreatedInstance.from_existing(node_data, self)
        created_instance.transient_data["reference_node"] = reference_node
        self._add_instance_to_context(created_instance)
        return created_instance

    def _collect_transient_data(self, created_instance):
        import ufe

        # Find the reference node
        reference_node = created_instance.transient_data.get("reference_node")
        if not reference_node:
            # Existing scene instance
            reference_node = created_instance["instance_node"]

        dag_path = self.get_pulled_maya_reference_dag_path(reference_node)
        pulled_info = self.get_pulled_info(dag_path)
        path_string = ufe.PathString.string(pulled_info.pulled_path)
        dag_shape, prim_path = path_string.split(",", 1)

        # TODO: This should instead find the nearest asset instead of assuming
        #   by splitting strings
        # split off /rig/rigMain
        target_prim_path = prim_path.rsplit("/", 2)[0]
        created_instance.transient_data["target_prim_path"] = target_prim_path

    def update_instances(self, update_list):
        # We only generate the persisting layer data into the scene once
        # we save with the UI on e.g. validate or publish
        for instance, _changes in update_list:
            instance_node = instance.data.get("instance_node")

            # Ensure a node exists to persist the data to
            if not instance_node:
                instance_node = self._create_instance_node(instance)
                instance.data["instance_node"] = instance_node

            self.imprint_instance_node(instance_node,
                                       data=instance.data_to_store())

    def _create_instance_node(self, instance):
        """Create object set from product name"""
        reference_node = instance.transient_data.get("reference_node")
        members = [reference_node] if reference_node else []
        return cmds.sets(members, name=instance.data["productName"])

    @staticmethod
    def get_pulled_maya_reference_dag_path(reference_node) -> Optional[str]:
        """Return the maya dag path to the root node of a MayaReference prim
        in a Maya USD Proxy Shape that is currently in edit mode (is currently
        a loaded reference)"""
        try:
            import mayaUsdUtils
        except ImportError:
            # No maya usd plug-in
            return

        associated_nodes = cmds.listConnections(
            f"{reference_node}.associatedNode")
        if not associated_nodes:
            return

        for node in associated_nodes:
            if mayaUsdUtils.isPulledMayaReference(node):
                # Is pulled maya reference
                return node
        return

    @staticmethod
    def get_pulled_info(dag_path: str) -> Optional[PulledInfo]:
        """Return pulled info from a pulled maya reference dag path"""
        try:
            import mayaUsdUtils
        except ImportError:
            # No maya usd plug-in
            return

        return PulledInfo(*mayaUsdUtils.getPulledInfo(dag_path))

    def get_instance_attr_defs(self):
        return _get_animation_attr_defs(self.create_context)
