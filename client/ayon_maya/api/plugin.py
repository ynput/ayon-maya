import json
import os
from abc import ABCMeta

import ayon_api
import qargparse
import six

from ayon_core.lib import BoolDef, Logger
from ayon_core.pipeline import (
    AVALON_CONTAINER_ID,
    AVALON_INSTANCE_ID,
    AYON_CONTAINER_ID,
    AYON_INSTANCE_ID,
    Anatomy,
    AutoCreator,
    CreatedInstance,
    Creator as NewCreator,
    CreatorError,
    HiddenCreator,
    LegacyCreator,
    LoaderPlugin,
    get_current_project_name,
    get_representation_path,
    publish,
)
from ayon_core.pipeline.create import get_product_name
from ayon_core.pipeline.load import LoadError
from ayon_core.settings import get_project_settings
from maya import cmds
from maya.app.renderSetup.model import renderSetup
from pyblish.api import ContextPlugin, InstancePlugin

from . import lib
from .lib import imprint, read
from .pipeline import containerise

log = Logger.get_logger()
SETTINGS_CATEGORY = "maya"


def _get_attr(node, attr, default=None):
    """Helper to get attribute which allows attribute to not exist."""
    if not cmds.attributeQuery(attr, node=node, exists=True):
        return default
    return cmds.getAttr("{}.{}".format(node, attr))


# Backwards compatibility: these functions has been moved to lib.
def get_reference_node(*args, **kwargs):
    """Get the reference node from the container members

    Deprecated:
        This function was moved and will be removed in 3.16.x.
    """
    msg = "Function 'get_reference_node' has been moved."
    log.warning(msg)
    cmds.warning(msg)
    return lib.get_reference_node(*args, **kwargs)


def get_reference_node_parents(*args, **kwargs):
    """
    Deprecated:
        This function was moved and will be removed in 3.16.x.
    """
    msg = "Function 'get_reference_node_parents' has been moved."
    log.warning(msg)
    cmds.warning(msg)
    return lib.get_reference_node_parents(*args, **kwargs)


class Creator(LegacyCreator):
    defaults = ['Main']

    def process(self):
        nodes = list()

        with lib.undo_chunk():
            if (self.options or {}).get("useSelection"):
                nodes = cmds.ls(selection=True)

            instance = cmds.sets(nodes, name=self.name)
            lib.imprint(instance, self.data)

        return instance


@six.add_metaclass(ABCMeta)
class MayaCreatorBase(object):

    @staticmethod
    def cache_instance_data(shared_data):
        """Cache instances for Creators to shared data.

        Create `maya_cached_instance_data` key when needed in shared data and
        fill it with all collected instances from the scene under its
        respective creator identifiers.

        If legacy instances are detected in the scene, create
        `maya_cached_legacy_instances` there and fill it with
        all legacy products under product type as a key.

        Args:
            Dict[str, Any]: Shared data.

        """
        if shared_data.get("maya_cached_instance_data") is None:
            cache = dict()
            cache_legacy = dict()

            for node in cmds.ls(type="objectSet"):

                if _get_attr(node, attr="id") not in {
                    AYON_INSTANCE_ID, AVALON_INSTANCE_ID
                }:
                    continue

                creator_id = _get_attr(node, attr="creator_identifier")
                if creator_id is not None:
                    # creator instance
                    cache.setdefault(creator_id, []).append(node)
                else:
                    # legacy instance
                    family = _get_attr(node, attr="family")
                    if family is None:
                        # must be a broken instance
                        continue

                    cache_legacy.setdefault(family, []).append(node)

            shared_data["maya_cached_instance_data"] = cache
            shared_data["maya_cached_legacy_instances"] = cache_legacy
        return shared_data

    def get_publish_families(self):
        """Return families for the instances of this creator.

        Allow a Creator to define multiple families so that a creator can
        e.g. specify `usd` and `usdMaya` and another USD creator can also
        specify `usd` but apply different extractors like `usdMultiverse`.

        There is no need to override this method if you only have the
        'product_type' required for publish filtering.

        Returns:
            list: families for instances of this creator

        """
        return []

    def imprint_instance_node(self, node, data):

        # We never store the instance_node as value on the node since
        # it's the node name itself
        data.pop("instance_node", None)
        data.pop("instance_id", None)

        # Don't store `families` since it's up to the creator itself
        # to define the initial publish families - not a stored attribute of
        # `families`
        data.pop("families", None)

        # We store creator attributes at the root level and assume they
        # will not clash in names with `product`, `task`, etc. and other
        # default names. This is just so these attributes in many cases
        # are still editable in the maya UI by artists.
        # note: pop to move to end of dict to sort attributes last on the node
        creator_attributes = data.pop("creator_attributes", {})

        # We only flatten value types which `imprint` function supports
        json_creator_attributes = {}
        for key, value in dict(creator_attributes).items():
            if isinstance(value, (list, tuple, dict)):
                creator_attributes.pop(key)
                json_creator_attributes[key] = value

        # Flatten remaining creator attributes to the node itself
        data.update(creator_attributes)

        # We know the "publish_attributes" will be complex data of
        # settings per plugins, we'll store this as a flattened json structure
        # pop to move to end of dict to sort attributes last on the node
        data["publish_attributes"] = json.dumps(
            data.pop("publish_attributes", {})
        )

        # Persist the non-flattened creator attributes (special value types,
        # like multiselection EnumDef)
        data["creator_attributes"] = json.dumps(json_creator_attributes)

        # Since we flattened the data structure for creator attributes we want
        # to correctly detect which flattened attributes should end back in the
        # creator attributes when reading the data from the node, so we store
        # the relevant keys as a string
        data["__creator_attributes_keys"] = ",".join(creator_attributes.keys())

        # Kill any existing attributes just so we can imprint cleanly again
        for attr in data.keys():
            if cmds.attributeQuery(attr, node=node, exists=True):
                cmds.deleteAttr("{}.{}".format(node, attr))

        return imprint(node, data)

    def read_instance_node(self, node):
        node_data = read(node)

        # Never care about a cbId attribute on the object set
        # being read as 'data'
        node_data.pop("cbId", None)

        # Make sure we convert any creator attributes from the json string
        creator_attributes = node_data.get("creator_attributes")
        if creator_attributes:
            node_data["creator_attributes"] = json.loads(creator_attributes)
        else:
            node_data["creator_attributes"] = {}

        # Move the relevant attributes into "creator_attributes" that
        # we flattened originally
        creator_attribute_keys = node_data.pop("__creator_attributes_keys",
                                               "").split(",")
        for key in creator_attribute_keys:
            if key in node_data:
                node_data["creator_attributes"][key] = node_data.pop(key)

        # Make sure we convert any publish attributes from the json string
        publish_attributes = node_data.get("publish_attributes")
        if publish_attributes:
            node_data["publish_attributes"] = json.loads(publish_attributes)

        # Explicitly re-parse the node name
        node_data["instance_node"] = node
        node_data["instance_id"] = node

        # If the creator plug-in specifies
        families = self.get_publish_families()
        if families:
            node_data["families"] = families

        return node_data

    def _default_collect_instances(self):
        self.cache_instance_data(self.collection_shared_data)
        cached_instances = (
            self.collection_shared_data["maya_cached_instance_data"]
        )
        for node in cached_instances.get(self.identifier, []):
            node_data = self.read_instance_node(node)

            created_instance = CreatedInstance.from_existing(node_data, self)
            self._add_instance_to_context(created_instance)

    def _default_update_instances(self, update_list):
        for created_inst, _changes in update_list:
            data = created_inst.data_to_store()
            node = data.get("instance_node")

            self.imprint_instance_node(node, data)

    def _default_remove_instances(self, instances):
        """Remove specified instance from the scene.

        This is only removing `id` parameter so instance is no longer
        instance, because it might contain valuable data for artist.

        """
        for instance in instances:
            node = instance.data.get("instance_node")
            if node:
                cmds.delete(node)

            self._remove_instance_from_context(instance)


@six.add_metaclass(ABCMeta)
class MayaCreator(NewCreator, MayaCreatorBase):

    settings_category = "maya"

    def create(self, product_name, instance_data, pre_create_data):

        members = list()
        if pre_create_data.get("use_selection"):
            members = cmds.ls(selection=True)

        # Allow a Creator to define multiple families
        publish_families = self.get_publish_families()
        if publish_families:
            families = instance_data.setdefault("families", [])
            for family in self.get_publish_families():
                if family not in families:
                    families.append(family)

        with lib.undo_chunk():
            instance_node = cmds.sets(members, name=product_name)
            instance_data["instance_node"] = instance_node
            instance = CreatedInstance(
                self.product_type,
                product_name,
                instance_data,
                self)
            self._add_instance_to_context(instance)

            self.imprint_instance_node(instance_node,
                                       data=instance.data_to_store())
            return instance

    def collect_instances(self):
        return self._default_collect_instances()

    def update_instances(self, update_list):
        return self._default_update_instances(update_list)

    def remove_instances(self, instances):
        return self._default_remove_instances(instances)

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection",
                    label="Use selection",
                    default=True)
        ]


class MayaAutoCreator(AutoCreator, MayaCreatorBase):
    """Automatically triggered creator for Maya.

    The plugin is not visible in UI, and 'create' method does not expect
        any arguments.
    """

    settings_category = "maya"

    def collect_instances(self):
        return self._default_collect_instances()

    def update_instances(self, update_list):
        return self._default_update_instances(update_list)

    def remove_instances(self, instances):
        return self._default_remove_instances(instances)


class MayaHiddenCreator(HiddenCreator, MayaCreatorBase):
    """Hidden creator for Maya.

    The plugin is not visible in UI, and it does not have strictly defined
        arguments for 'create' method.
    """

    settings_category = "maya"

    def create(self, *args, **kwargs):
        return MayaCreator.create(self, *args, **kwargs)

    def collect_instances(self):
        return self._default_collect_instances()

    def update_instances(self, update_list):
        return self._default_update_instances(update_list)

    def remove_instances(self, instances):
        return self._default_remove_instances(instances)


def ensure_namespace(namespace):
    """Make sure the namespace exists.

    Args:
        namespace (str): The preferred namespace name.

    Returns:
        str: The generated or existing namespace

    """
    exists = cmds.namespace(exists=namespace)
    if exists:
        return namespace
    else:
        return cmds.namespace(add=namespace)


class RenderlayerCreator(NewCreator, MayaCreatorBase):
    """Creator which creates an instance per renderlayer in the workfile.

    Create and manages renderlayer product per renderLayer in workfile.
    This generates a singleton node in the scene which, if it exists, tells the
    Creator to collect Maya rendersetup renderlayers as individual instances.
    As such, triggering create doesn't actually create the instance node per
    layer but only the node which tells the Creator it may now collect
    an instance per renderlayer.

    """

    # These are required to be overridden in subclass
    singleton_node_name = ""

    # These are optional to be overridden in subclass
    layer_instance_prefix = None

    def _get_singleton_node(self, return_all=False):
        nodes = lib.lsattr("pre_creator_identifier", self.identifier)
        if nodes:
            return nodes if return_all else nodes[0]

    def create(self, product_name, instance_data, pre_create_data):
        # A Renderlayer is never explicitly created using the create method.
        # Instead, renderlayers from the scene are collected. Thus "create"
        # would only ever be called to say, 'hey, please refresh collect'
        self.create_singleton_node()

        # if no render layers are present, create default one with
        # asterisk selector
        rs = renderSetup.instance()
        if not rs.getRenderLayers():
            render_layer = rs.createRenderLayer("Main")
            collection = render_layer.createCollection("defaultCollection")
            collection.getSelector().setPattern('*')

        # By RenderLayerCreator.create we make it so that the renderlayer
        # instances directly appear even though it just collects scene
        # renderlayers. This doesn't actually 'create' any scene contents.
        return self.collect_instances()

    def create_singleton_node(self):
        if self._get_singleton_node():
            raise CreatorError("A Render instance already exists - only "
                               "one can be configured.")

        with lib.undo_chunk():
            node = cmds.sets(empty=True, name=self.singleton_node_name)
            lib.imprint(node, data={
                "pre_creator_identifier": self.identifier
            })

        return node

    def collect_instances(self):

        # We only collect if the global render instance exists
        if not self._get_singleton_node():
            return

        host_name = self.create_context.host_name
        rs = renderSetup.instance()
        layers = rs.getRenderLayers()
        instances = []
        for layer in layers:
            layer_instance_node = self.find_layer_instance_node(layer)
            if layer_instance_node:
                data = self.read_instance_node(layer_instance_node)
                instance = CreatedInstance.from_existing(data, creator=self)
            else:
                # No existing scene instance node for this layer. Note that
                # this instance will not have the `instance_node` data yet
                # until it's been saved/persisted at least once.
                project_name = self.create_context.get_current_project_name()
                folder_path = self.create_context.get_current_folder_path()
                task_name = self.create_context.get_current_task_name()
                instance_data = {
                    "folderPath": folder_path,
                    "task": task_name,
                    "variant": layer.name(),
                }
                folder_entity = ayon_api.get_folder_by_path(
                    project_name, folder_path
                )
                task_entity = ayon_api.get_task_by_name(
                    project_name, folder_entity["id"], task_name
                )
                product_name = self.get_product_name(
                    project_name,
                    folder_entity,
                    task_entity,
                    layer.name(),
                    host_name,
                )

                instance = CreatedInstance(
                    product_type=self.product_type,
                    product_name=product_name,
                    data=instance_data,
                    creator=self
                )

            instance.transient_data["layer"] = layer
            self._add_instance_to_context(instance)
            instances.append(instance)

        return instances

    def find_layer_instance_node(self, layer):
        connected_sets = cmds.listConnections(
            "{}.message".format(layer.name()),
            source=False,
            destination=True,
            type="objectSet"
        ) or []

        for node in connected_sets:
            if not cmds.attributeQuery("creator_identifier",
                                       node=node,
                                       exists=True):
                continue

            creator_identifier = cmds.getAttr(node + ".creator_identifier")
            if creator_identifier == self.identifier:
                self.log.info("Found node: {}".format(node))
                return node

    def _create_layer_instance_node(self, layer):

        # We only collect if a CreateRender instance exists
        create_render_set = self._get_singleton_node()
        if not create_render_set:
            raise CreatorError("Creating a renderlayer instance node is not "
                               "allowed if no 'CreateRender' instance exists")

        namespace = "_{}".format(self.singleton_node_name)
        namespace = ensure_namespace(namespace)

        name = "{}:{}".format(namespace, layer.name())
        render_set = cmds.sets(name=name, empty=True)

        # Keep an active link with the renderlayer so we can retrieve it
        # later by a physical maya connection instead of relying on the layer
        # name
        cmds.addAttr(render_set, longName="renderlayer", at="message")
        cmds.connectAttr("{}.message".format(layer.name()),
                         "{}.renderlayer".format(render_set), force=True)

        # Add the set to the 'CreateRender' set.
        cmds.sets(render_set, forceElement=create_render_set)

        return render_set

    def update_instances(self, update_list):
        # We only generate the persisting layer data into the scene once
        # we save with the UI on e.g. validate or publish
        for instance, _changes in update_list:
            instance_node = instance.data.get("instance_node")

            # Ensure a node exists to persist the data to
            if not instance_node:
                layer = instance.transient_data["layer"]
                instance_node = self._create_layer_instance_node(layer)
                instance.data["instance_node"] = instance_node

            self.imprint_instance_node(instance_node,
                                       data=instance.data_to_store())

    def imprint_instance_node(self, node, data):
        # Do not ever try to update the `renderlayer` since it'll try
        # to remove the attribute and recreate it but fail to keep it a
        # message attribute link. We only ever imprint that on the initial
        # node creation.
        # TODO: Improve how this is handled
        data.pop("renderlayer", None)
        data.get("creator_attributes", {}).pop("renderlayer", None)

        return super(RenderlayerCreator, self).imprint_instance_node(node,
                                                                     data=data)

    def remove_instances(self, instances):
        """Remove specified instances from the scene.

        This is only removing `id` parameter so instance is no longer
        instance, because it might contain valuable data for artist.

        """
        # Instead of removing the single instance or renderlayers we instead
        # remove the CreateRender node this creator relies on to decide whether
        # it should collect anything at all.
        nodes = self._get_singleton_node(return_all=True)
        if nodes:
            cmds.delete(nodes)

        # Remove ALL the instances even if only one gets deleted
        for instance in list(self.create_context.instances):
            if instance.get("creator_identifier") == self.identifier:
                self._remove_instance_from_context(instance)

                # Remove the stored settings per renderlayer too
                node = instance.data.get("instance_node")
                if node and cmds.objExists(node):
                    cmds.delete(node)

    def get_product_name(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name=None,
        instance=None
    ):
        if host_name is None:
            host_name = self.create_context.host_name
        dynamic_data = self.get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            instance
        )
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        # creator.product_type != 'render' as expected
        return get_product_name(
            project_name,
            task_name,
            task_type,
            host_name,
            self.layer_instance_prefix or self.product_type,
            variant,
            dynamic_data=dynamic_data,
            project_settings=self.project_settings
        )


def get_load_color_for_product_type(product_type, settings=None):
    """Get color for product type from settings.

    Args:
        product_type (str): Family name.
        settings (Optional[dict]): Settings dictionary.

    Returns:
        Union[tuple[float, float, float], None]: RGB color.

    """
    if settings is None:
        settings = get_project_settings(get_current_project_name())

    colors = settings["maya"]["load"]["colors"]
    color = colors.get(product_type)
    if not color:
        return None

    if len(color) == 3:
        red, green, blue = color
    elif len(color) == 4:
        red, green, blue, _ = color
    else:
        raise ValueError("Invalid color definition {}".format(str(color)))

    if isinstance(red, int):
        red = red / 255.0
        green = green / 255.0
        blue = blue / 255.0
    return red, green, blue


class Loader(LoaderPlugin):
    hosts = ["maya"]
    settings_category = SETTINGS_CATEGORY
    load_settings = {}  # defined in settings

    @classmethod
    def apply_settings(cls, project_settings):
        super(Loader, cls).apply_settings(project_settings)
        cls.load_settings = project_settings['maya']['load']

    def get_custom_namespace_and_group(self, context, options, loader_key):
        """Queries Settings to get custom template for namespace and group.

        Group template might be empty >> this forces to not wrap imported items
        into separate group.

        Args:
            context (dict)
            options (dict): artist modifiable options from dialog
            loader_key (str): key to get separate configuration from Settings
                ('reference_loader'|'import_loader')
        """

        options["attach_to_root"] = True
        custom_naming = self.load_settings[loader_key]

        if not custom_naming["namespace"]:
            raise LoadError("No namespace specified in "
                            "Maya ReferenceLoader settings")
        elif not custom_naming["group_name"]:
            self.log.debug("No custom group_name, no group will be created.")
            options["attach_to_root"] = False

        folder_entity = context["folder"]
        product_entity = context["product"]
        product_name = product_entity["name"]
        product_type = product_entity["productType"]
        formatting_data = {
            "asset_name": folder_entity["name"],
            "asset_type": "asset",
            "folder": {
                "name": folder_entity["name"],
            },
            "subset": product_name,
            "product": {
                "name": product_name,
                "type": product_type,
            },
            "family": product_type
        }

        custom_namespace = custom_naming["namespace"].format(
            **formatting_data
        )

        custom_group_name = custom_naming["group_name"].format(
            **formatting_data
        )

        return custom_group_name, custom_namespace, options


class ReferenceLoader(Loader):
    """A basic ReferenceLoader for Maya

    This will implement the basic behavior for a loader to inherit from that
    will containerize the reference and will implement the `remove` and
    `update` logic.

    """

    options = [
        qargparse.Integer(
            "count",
            label="Count",
            default=1,
            min=1,
            help="How many times to load?"
        ),
        qargparse.Double3(
            "offset",
            label="Position Offset",
            help="Offset loaded models for easier selection."
        ),
        qargparse.Boolean(
            "attach_to_root",
            label="Group imported asset",
            default=True,
            help="Should a group be created to encapsulate"
                 " imported representation ?"
        )
    ]

    def load(
        self,
        context,
        name=None,
        namespace=None,
        options=None
    ):
        path = self.filepath_from_context(context)
        assert os.path.exists(path), "%s does not exist." % path

        custom_group_name, custom_namespace, options = \
            self.get_custom_namespace_and_group(context, options,
                                                "reference_loader")

        count = options.get("count") or 1

        loaded_containers = []
        for c in range(0, count):
            namespace = lib.get_custom_namespace(custom_namespace)
            group_name = "{}:{}".format(
                namespace,
                custom_group_name
            )

            options['group_name'] = group_name

            # Offset loaded product
            if "offset" in options:
                offset = [i * c for i in options["offset"]]
                options["translate"] = offset

            self.log.info(options)

            self.process_reference(
                context=context,
                name=name,
                namespace=namespace,
                options=options
            )

            # Only containerize if any nodes were loaded by the Loader
            nodes = self[:]
            if not nodes:
                return

            ref_node = lib.get_reference_node(nodes, self.log)
            container = containerise(
                name=name,
                namespace=namespace,
                nodes=[ref_node],
                context=context,
                loader=self.__class__.__name__
            )
            loaded_containers.append(container)
            self._organize_containers(nodes, container)
            c += 1

        return loaded_containers

    def process_reference(self, context, name, namespace, options):
        """To be implemented by subclass"""
        raise NotImplementedError("Must be implemented by subclass")

    def update(self, container, context):
        from ayon_maya.api.lib import get_container_members
        from maya import cmds

        node = container["objectName"]

        project_name = context["project"]["name"]
        repre_entity = context["representation"]

        path = get_representation_path(repre_entity)

        # Get reference node from container members
        members = get_container_members(node)
        reference_node = lib.get_reference_node(members, self.log)
        namespace = cmds.referenceQuery(reference_node, namespace=True)

        file_type = {
            "ma": "mayaAscii",
            "mb": "mayaBinary",
            "abc": "Alembic",
            "fbx": "FBX",
            "usd": "USD Import"
        }.get(repre_entity["name"])

        assert file_type, "Unsupported representation: %s" % repre_entity

        assert os.path.exists(path), "%s does not exist." % path

        # Need to save alembic settings and reapply, cause referencing resets
        # them to incoming data.
        alembic_attrs = ["speed", "offset", "cycleType", "time"]
        alembic_data = {}
        if repre_entity["name"] == "abc":
            alembic_nodes = cmds.ls(
                "{}:*".format(namespace), type="AlembicNode"
            )
            if alembic_nodes:
                for attr in alembic_attrs:
                    node_attr = "{}.{}".format(alembic_nodes[0], attr)
                    data = {
                        "input": lib.get_attribute_input(node_attr),
                        "value": cmds.getAttr(node_attr)
                    }

                    alembic_data[attr] = data
            else:
                self.log.debug("No alembic nodes found in {}".format(members))

        try:
            path = self.prepare_root_value(path, project_name)
            content = cmds.file(path,
                                loadReference=reference_node,
                                type=file_type,
                                returnNewNodes=True)
        except RuntimeError as exc:
            # When changing a reference to a file that has load errors the
            # command will raise an error even if the file is still loaded
            # correctly (e.g. when raising errors on Arnold attributes)
            # When the file is loaded and has content, we consider it's fine.
            if not cmds.referenceQuery(reference_node, isLoaded=True):
                raise

            content = cmds.referenceQuery(reference_node,
                                          nodes=True,
                                          dagPath=True)
            if not content:
                raise

            self.log.warning("Ignoring file read error:\n%s", exc)

        self._organize_containers(content, container["objectName"])

        # Reapply alembic settings.
        if repre_entity["name"] == "abc" and alembic_data:
            alembic_nodes = cmds.ls(
                "{}:*".format(namespace), type="AlembicNode"
            )
            if alembic_nodes:
                alembic_node = alembic_nodes[0]  # assume single AlembicNode
                for attr, data in alembic_data.items():
                    node_attr = "{}.{}".format(alembic_node, attr)
                    input = lib.get_attribute_input(node_attr)
                    if data["input"]:
                        if data["input"] != input:
                            cmds.connectAttr(
                                data["input"], node_attr, force=True
                            )
                    else:
                        if input:
                            cmds.disconnectAttr(input, node_attr)
                        cmds.setAttr(node_attr, data["value"])

        # Fix PLN-40 for older containers created with AYON that had the
        # `.verticesOnlySet` set to True.
        if cmds.getAttr("{}.verticesOnlySet".format(node)):
            self.log.info("Setting %s.verticesOnlySet to False", node)
            cmds.setAttr("{}.verticesOnlySet".format(node), False)

        # Remove any placeHolderList attribute entries from the set that
        # are remaining from nodes being removed from the referenced file.
        members = cmds.sets(node, query=True)
        invalid = [x for x in members if ".placeHolderList" in x]
        if invalid:
            cmds.sets(invalid, remove=node)

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     repre_entity["id"],
                     type="string")

        # When an animation or pointcache gets connected to an Xgen container,
        # the compound attribute "xgenContainers" gets created. When animation
        # containers gets updated we also need to update the cacheFileName on
        # the Xgen collection.
        compound_name = "xgenContainers"
        if cmds.objExists("{}.{}".format(node, compound_name)):
            import xgenm
            container_amount = cmds.getAttr(
                "{}.{}".format(node, compound_name), size=True
            )
            # loop through all compound children
            for i in range(container_amount):
                attr = "{}.{}[{}].container".format(node, compound_name, i)
                objectset = cmds.listConnections(attr)[0]
                reference_node = cmds.sets(objectset, query=True)[0]
                palettes = cmds.ls(
                    cmds.referenceQuery(reference_node, nodes=True),
                    type="xgmPalette"
                )
                for palette in palettes:
                    for description in xgenm.descriptions(palette):
                        xgenm.setAttr(
                            "cacheFileName",
                            path.replace("\\", "/"),
                            palette,
                            description,
                            "SplinePrimitive"
                        )

            # Refresh UI and viewport.
            de = xgenm.xgGlobal.DescriptionEditor
            de.refresh("Full")

    def remove(self, container):
        """Remove an existing `container` from Maya scene

        Deprecated; this functionality is replaced by `api.remove()`

        Arguments:
            container (openpype:container-1.0): Which container
                to remove from scene.

        """
        from maya import cmds

        node = container["objectName"]

        # Assume asset has been referenced
        members = cmds.sets(node, query=True)
        reference_node = lib.get_reference_node(members, self.log)

        assert reference_node, ("Imported container not supported; "
                                "container must be referenced.")

        self.log.info("Removing '%s' from Maya.." % container["name"])

        namespace = cmds.referenceQuery(reference_node, namespace=True)
        fname = cmds.referenceQuery(reference_node, filename=True)
        cmds.file(fname, removeReference=True)

        try:
            cmds.delete(node)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

        try:
            # If container is not automatically cleaned up by May (issue #118)
            cmds.namespace(removeNamespace=namespace,
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass

    def prepare_root_value(self, file_url, project_name):
        """Replace root value with env var placeholder.

        Use ${AYON_PROJECT_ROOT_WORK} (or any other root) instead of proper
        root value when storing referenced url into a workfile.
        Useful for remote workflows with SiteSync.

        Args:
            file_url (str)
            project_name (dict)
        Returns:
            (str)
        """
        settings = get_project_settings(project_name)
        use_env_var_as_root = (settings["maya"]
                                       ["maya_dirmap"]
                                       ["use_env_var_as_root"])
        if use_env_var_as_root:
            anatomy = Anatomy(project_name)
            file_url = anatomy.replace_root_with_env_key(file_url, '${{{}}}')

        return file_url

    @staticmethod
    def _organize_containers(nodes, container):
        # type: (list, str) -> None
        """Put containers in loaded data to correct hierarchy."""
        for node in nodes:
            id_attr = "{}.id".format(node)
            if not cmds.attributeQuery("id", node=node, exists=True):
                continue
            if cmds.getAttr(id_attr) not in {
                AYON_CONTAINER_ID, AVALON_CONTAINER_ID
            }:
                cmds.sets(node, forceElement=container)


class MayaLoader(LoaderPlugin):
    """Base class for loader plugins."""

    settings_category = SETTINGS_CATEGORY


class MayaInstancePlugin(InstancePlugin):
    """Base class for instance publish plugins."""

    settings_category = SETTINGS_CATEGORY
    hosts = ["maya"]


class MayaContextPlugin(ContextPlugin):
    """Base class for context publish plugins."""

    settings_category = SETTINGS_CATEGORY
    hosts = ["maya"]


class MayaExtractorPlugin(publish.Extractor):
    """Base class for extract plugins."""

    settings_category = SETTINGS_CATEGORY
    hosts = ["maya"]
