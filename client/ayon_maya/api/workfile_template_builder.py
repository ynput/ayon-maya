import json

from maya import cmds

from ayon_core.pipeline import (
    registered_host,
    get_current_folder_path,
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID,
)
from ayon_core.pipeline.workfile.workfile_template_builder import (
    TemplateAlreadyImported,
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    PlaceholderItem,
)
from ayon_core.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)

from .lib import read, imprint, get_main_window

PLACEHOLDER_SET = "PLACEHOLDERS_SET"


class MayaTemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for maya"""

    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """

        if cmds.objExists(PLACEHOLDER_SET):
            raise TemplateAlreadyImported((
                "Build template already loaded\n"
                "Clean scene if needed (File > New Scene)"
            ))

        cmds.sets(name=PLACEHOLDER_SET, empty=True)
        new_nodes = cmds.file(
            path,
            i=True,
            returnNewNodes=True,
            preserveReferences=True,
            loadReferenceDepth="all",
        )

        # make default cameras non-renderable
        default_cameras = [cam for cam in cmds.ls(cameras=True)
                           if cmds.camera(cam, query=True, startupCamera=True)]
        for cam in default_cameras:
            if not cmds.attributeQuery("renderable", node=cam, exists=True):
                self.log.debug(
                    "Camera {} has no attribute 'renderable'".format(cam)
                )
                continue
            cmds.setAttr("{}.renderable".format(cam), 0)

        cmds.setAttr(PLACEHOLDER_SET + ".hiddenInOutliner", True)

        imported_sets = cmds.ls(new_nodes, set=True)
        if not imported_sets:
            return True

        # update imported sets information
        folder_path = get_current_folder_path()
        for node in imported_sets:
            if not cmds.attributeQuery("id", node=node, exists=True):
                continue
            if cmds.getAttr("{}.id".format(node)) not in {
                AYON_INSTANCE_ID, AVALON_INSTANCE_ID
            }:
                continue
            if not cmds.attributeQuery("folderPath", node=node, exists=True):
                continue

            cmds.setAttr(
                "{}.folderPath".format(node), folder_path, type="string")

        return True


class MayaPlaceholderPlugin(PlaceholderPlugin):
    """Base Placeholder Plugin for Maya with one unified cache.

    Creates a locator as placeholder node, which during populate provide
    all of its attributes defined on the locator's transform in
    `placeholder.data` and where `placeholder.scene_identifier` is the
    full path to the node.

    Inherited classes must still implement `populate_placeholder`

    """

    use_selection_as_parent = True
    item_class = PlaceholderItem

    def _create_placeholder_name(self, placeholder_data):
        return self.identifier.replace(".", "_")

    def _collect_scene_placeholders(self):
        nodes_by_identifier = self.builder.get_shared_populate_data(
            "placeholder_nodes"
        )
        if nodes_by_identifier is None:
            # Cache placeholder data to shared data
            nodes = cmds.ls("*.plugin_identifier", long=True, objectsOnly=True)

            nodes_by_identifier = {}
            for node in nodes:
                identifier = cmds.getAttr("{}.plugin_identifier".format(node))
                nodes_by_identifier.setdefault(identifier, []).append(node)

            # Set the cache
            self.builder.set_shared_populate_data(
                "placeholder_nodes", nodes_by_identifier
            )

        return nodes_by_identifier

    def create_placeholder(self, placeholder_data):

        parent = None
        if self.use_selection_as_parent:
            selection = cmds.ls(selection=True)
            if len(selection) > 1:
                raise ValueError(
                    "More than one node is selected. "
                    "Please select only one to define the parent."
                )
            parent = selection[0] if selection else None

        placeholder_data["plugin_identifier"] = self.identifier
        placeholder_name = self._create_placeholder_name(placeholder_data)

        placeholder = cmds.spaceLocator(name=placeholder_name)[0]
        if parent:
            placeholder = cmds.parent(placeholder, selection[0])[0]

        self.imprint(placeholder, placeholder_data)

    def update_placeholder(self, placeholder_item, placeholder_data):
        node_name = placeholder_item.scene_identifier

        changed_values = {}
        for key, value in placeholder_data.items():
            if value != placeholder_item.data.get(key):
                changed_values[key] = value

        # Delete attributes to ensure we imprint new data with correct type
        for key in changed_values.keys():
            placeholder_item.data[key] = value
            if cmds.attributeQuery(key, node=node_name, exists=True):
                attribute = "{}.{}".format(node_name, key)
                cmds.deleteAttr(attribute)

        self.imprint(node_name, changed_values)

    def collect_placeholders(self):
        placeholders = []
        nodes_by_identifier = self._collect_scene_placeholders()
        for node in nodes_by_identifier.get(self.identifier, []):
            # TODO do data validations and maybe upgrades if they are invalid
            placeholder_data = self.read(node)
            placeholders.append(
                self.item_class(scene_identifier=node,
                                data=placeholder_data,
                                plugin=self)
            )

        return placeholders

    def post_placeholder_process(self, placeholder, failed):
        """Cleanup placeholder after load of its corresponding representations.

        Hide placeholder, add them to placeholder set.
        Used only by PlaceholderCreateMixin and PlaceholderLoadMixin

        Args:
            placeholder (PlaceholderItem): Item which was just used to load
                representation.
            failed (bool): Loading of representation failed.
        """
        # Hide placeholder and add them to placeholder set
        node = placeholder.scene_identifier

        # If we just populate the placeholders from current scene, the
        # placeholder set will not be created so account for that.
        if not cmds.objExists(PLACEHOLDER_SET):
            cmds.sets(name=PLACEHOLDER_SET, empty=True)

        cmds.sets(node, addElement=PLACEHOLDER_SET)
        cmds.hide(node)
        cmds.setAttr("{}.hiddenInOutliner".format(node), True)

    def delete_placeholder(self, placeholder):
        """Remove placeholder if building was successful

        Used only by PlaceholderCreateMixin and PlaceholderLoadMixin.
        """
        node = placeholder.scene_identifier

        # To avoid that deleting a placeholder node will have Maya delete
        # any objectSets the node was a member of we will first remove it
        # from any sets it was a member of. This way the `PLACEHOLDERS_SET`
        # will survive long enough
        sets = cmds.listSets(o=node) or []
        for object_set in sets:
            cmds.sets(node, remove=object_set)

        cmds.delete(node)

    def imprint(self, node, data):
        """Imprint call for placeholder node"""

        # Complicated data that can't be represented as flat maya attributes
        # we write to json strings, e.g. multiselection EnumDef
        for key, value in data.items():
            if isinstance(value, (list, tuple, dict)):
                data[key] = "JSON::{}".format(json.dumps(value))

        imprint(node, data)

    def read(self, node):
        """Read call for placeholder node"""

        data = read(node)

        # Complicated data that can't be represented as flat maya attributes
        # we read from json strings, e.g. multiselection EnumDef
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("JSON::"):
                value = value[len("JSON::"):]   # strip of JSON:: prefix
                data[key] = json.loads(value)

        return data


def build_workfile_template(*args, **kwargs):
    builder = MayaTemplateBuilder(registered_host())
    builder.build_template(*args, **kwargs)


def update_workfile_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.rebuild_template()


def create_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=get_main_window())
    window.show()


def update_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node_name in cmds.ls(selection=True, long=True):
        if node_name in placeholder_items_by_id:
            placeholder_items.append(placeholder_items_by_id[node_name])

    # TODO show UI at least
    if len(placeholder_items) == 0:
        raise ValueError("No node selected")

    if len(placeholder_items) > 1:
        raise ValueError("Too many selected nodes")

    placeholder_item = placeholder_items[0]
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=get_main_window())
    window.set_update_mode(placeholder_item)
    window.exec_()
