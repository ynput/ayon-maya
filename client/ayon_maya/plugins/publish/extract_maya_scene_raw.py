# -*- coding: utf-8 -*-
"""Extract data as Maya scene (raw)."""
from __future__ import annotations
import os
import contextlib
from ayon_core.lib import BoolDef
from ayon_core.pipeline import AVALON_CONTAINER_ID, AYON_CONTAINER_ID
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
from ayon_maya.api.lib import maintained_selection, shader
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

    # Defined by settings
    add_for_families: list[str] = []

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
                default=True,
            )
        ]

    def process(self, instance):
        """Plugin entry point."""
        maya_settings = instance.context.data["project_settings"]["maya"]
        ext_mapping = {
            item["name"]: item["value"]
            for item in maya_settings["ext_mapping"]
        }
        scene_type: str = self.scene_type

        # Use `families` for lookup in extension mapping and add for families
        families = [instance.data["productType"]]
        families.extend(instance.data.get("families", []))

        # use extension mapping for first family found
        for family in families:
            if family in ext_mapping:
                self.log.debug(
                    f"Using '{scene_type}' as scene type for '{family}'"
                )
                scene_type = ext_mapping[family]
                break
        else:
            self.log.debug(
                f"Using default '{scene_type}' as scene type for "
                f"'{families}' because no extension mapping settings "
                "found for product type."
            )

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.{1}".format(instance.name, scene_type)
        path = os.path.join(dir_path, filename)

        # Whether to include all nodes in the instance (including those from
        # history) or only use the exact set members
        members_only = instance.data.get("exactSetMembersOnly", True)
        if members_only:
            members = instance.data.get("setMembers", list())
            if not members:
                raise RuntimeError(
                    "Can't export 'exact set members only' when set is empty."
                )
        else:
            members = instance[:]

        # For some families, like `layout` we collect the containers so we
        # maintain the containers of the members in the resulting product.
        # However, if `exactSetMembersOnly` is true (which it is for layouts)
        # searching the exact set members for containers doesn't make much
        # sense. We must always search the full hierarchy to actually find
        # the relevant containers
        selection = list(members)  # make a copy to not affect input list
        add_for_families = set(self.add_for_families)
        if add_for_families and add_for_families.intersection(families):
            containers = self._get_loaded_containers(instance[:])
            self.log.debug(f"Collected containers: {containers}")
            selection.extend(containers)

        # Perform extraction
        self.log.debug("Performing extraction ...")
        attribute_values = self.get_attr_values_from_data(instance.data)

        file_type = "mayaAscii" if scene_type == "ma" else "mayaBinary"
        with maintained_selection():
            cmds.select(selection, noExpand=True)
            with contextlib.ExitStack() as stack:
                if not instance.data.get("shader", True):
                    # Fix bug where export without shader may import the
                    # geometry 'green' due to the lack of any shader on import.
                    stack.enter_context(
                        shader(selection, shadingEngine="initialShadingGroup")
                    )

                cmds.file(
                    path,
                    force=True,
                    typ=file_type,
                    exportSelected=True,
                    preserveReferences=attribute_values["preserve_references"],
                    constructionHistory=True,
                    shader=instance.data.get("shader", True),
                    constraints=True,
                    expressions=True,
                )

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            "name": scene_type,
            "ext": scene_type,
            "files": filename,
            "stagingDir": dir_path,
        }
        instance.data["representations"].append(representation)

        self.log.debug(
            "Extracted instance '%s' to: %s" % (instance.name, path)
        )

    @staticmethod
    def _get_loaded_containers(members):
        # type: (list[str]) -> list[str]
        refs_to_include = {
            cmds.referenceQuery(node, referenceNode=True)
            for node in members
            if cmds.referenceQuery(node, isNodeReferenced=True)
        }

        members_with_refs = refs_to_include.union(members)

        obj_sets = cmds.ls(
            "*.id",
            long=True,
            type="objectSet",
            recursive=True,
            objectsOnly=True,
        )

        loaded_containers = []
        for obj_set in obj_sets:
            if not cmds.attributeQuery("id", node=obj_set, exists=True):
                continue

            id_attr = "{}.id".format(obj_set)
            if cmds.getAttr(id_attr) not in {
                AYON_CONTAINER_ID,
                AVALON_CONTAINER_ID,
            }:
                continue

            set_content = set(cmds.sets(obj_set, query=True) or [])
            if set_content.intersection(members_with_refs):
                loaded_containers.append(obj_set)

        return loaded_containers
