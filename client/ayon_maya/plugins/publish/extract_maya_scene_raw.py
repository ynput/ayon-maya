# -*- coding: utf-8 -*-
"""Extract data as Maya scene (raw)."""
import os

from ayon_core.lib import BoolDef
from ayon_core.pipeline import AVALON_CONTAINER_ID, AYON_CONTAINER_ID
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_maya.api.lib import maintained_selection
from ayon_maya.api import plugin
from maya import cmds


class ExtractMayaSceneRaw(plugin.MayaExtractorPlugin, AYONPyblishPluginMixin):
    """Extract as Maya Scene (raw).

    This will preserve all references, construction history, etc.
    """

    label = "Maya Scene (Raw)"
    families = ["mayaAscii",
                "mayaScene",
                "setdress",
                "layout",
                "camerarig"]
    scene_type = "ma"

    @classmethod
    def get_attribute_defs(cls):
        return [
            BoolDef(
                "preserve_references",
                label="Preserve References",
                tooltip=(
                    "When enabled references will still be references "
                    "in the published file.\nWhen disabled the references "
                    "are imported into the published file generating a "
                    "file without references."
                ),
                default=True
            )
        ]

    def process(self, instance):
        """Plugin entry point."""
        maya_settings = instance.context.data["project_settings"]["maya"]
        ext_mapping = {
            item["name"]: item["value"]
            for item in maya_settings["ext_mapping"]
        }
        if ext_mapping:
            self.log.debug("Looking in settings for scene type ...")
            # use extension mapping for first family found
            for family in self.families:
                try:
                    self.scene_type = ext_mapping[family]
                    self.log.debug(
                        "Using {} as scene type".format(self.scene_type))
                    break
                except KeyError:
                    # no preset found
                    pass
        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.{1}".format(instance.name, self.scene_type)
        path = os.path.join(dir_path, filename)

        # Whether to include all nodes in the instance (including those from
        # history) or only use the exact set members
        members_only = instance.data.get("exactSetMembersOnly", False)
        if members_only:
            members = instance.data.get("setMembers", list())
            if not members:
                raise RuntimeError("Can't export 'exact set members only' "
                                   "when set is empty.")
        else:
            members = instance[:]

        selection = members
        if set(self.add_for_families).intersection(
                set(instance.data.get("families", []))) or \
                instance.data.get("productType") in self.add_for_families:
            selection += self._get_loaded_containers(members)

        # Perform extraction
        self.log.debug("Performing extraction ...")
        attribute_values = self.get_attr_values_from_data(
            instance.data
        )
        with maintained_selection():
            cmds.select(selection, noExpand=True)
            cmds.file(path,
                      force=True,
                      typ="mayaAscii" if self.scene_type == "ma" else "mayaBinary",  # noqa: E501
                      exportSelected=True,
                      preserveReferences=attribute_values[
                          "preserve_references"
                      ],
                      constructionHistory=True,
                      shader=True,
                      constraints=True,
                      expressions=True)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': self.scene_type,
            'ext': self.scene_type,
            'files': filename,
            "stagingDir": dir_path
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extracted instance '%s' to: %s" % (instance.name,
                                                           path))

    @staticmethod
    def _get_loaded_containers(members):
        # type: (list) -> list
        refs_to_include = {
            cmds.referenceQuery(node, referenceNode=True)
            for node in members
            if cmds.referenceQuery(node, isNodeReferenced=True)
        }

        members_with_refs = refs_to_include.union(members)

        obj_sets = cmds.ls("*.id", long=True, type="objectSet", recursive=True,
                           objectsOnly=True)

        loaded_containers = []
        for obj_set in obj_sets:

            if not cmds.attributeQuery("id", node=obj_set, exists=True):
                continue

            id_attr = "{}.id".format(obj_set)
            if cmds.getAttr(id_attr) not in {
                AYON_CONTAINER_ID, AVALON_CONTAINER_ID
            }:
                continue

            set_content = set(cmds.sets(obj_set, query=True))
            if set_content.intersection(members_with_refs):
                loaded_containers.append(obj_set)

        return loaded_containers
