import ayon_api

from ayon_core.pipeline.create.creator_plugins import ProductConvertorPlugin
from ayon_maya.api import plugin
from ayon_maya.api.lib import read

from maya import cmds
from maya.app.renderSetup.model import renderSetup


class MayaLegacyConvertor(ProductConvertorPlugin,
                          plugin.MayaCreatorBase):
    """Find and convert any legacy products in the scene.

    This Converter will find all legacy products in the scene and will
    transform them to the current system. Since the old products doesn't
    retain any information about their original creators, the only mapping
    we can do is based on their families.

    Its limitation is that you can have multiple creators creating product
    of the same type and there is no way to handle it. This code should
    nevertheless cover all creators that came with AYON.

    """
    identifier = "io.ayon.creators.maya.legacy"

    # Cases where the identifier or new product type doesn't correspond to the
    # original family on the legacy instances
    product_base_type_mapping = {
        "rendering": "io.ayon.creators.maya.renderlayer",
    }

    # Creator identifiers were renamed from the OpenPype namespace to the AYON
    # one (see the creators in `ayon_maya.plugins.create`). Instances stored
    # before the rename still carry the OpenPype identifier, so it has to be
    # mapped to the current one for them to be converted.
    # `MayaCreatorBase.cache_instance_data` detects those instances with
    # `LEGACY_CREATOR_IDENTIFIER_PREFIX` and caches them as legacy instances.
    creator_identifier_mapping = {
        "io.openpype.creators.maya.animation": "io.ayon.creators.maya.animation",
        "io.openpype.creators.maya.ass": "io.ayon.creators.maya.ass",
        "io.openpype.creators.maya.assproxy": "io.ayon.creators.maya.assproxy",
        "io.openpype.creators.maya.camera": "io.ayon.creators.maya.camera",
        "io.openpype.creators.maya.camerarig": "io.ayon.creators.maya.camerarig",
        "io.openpype.creators.maya.layout": "io.ayon.creators.maya.layout",
        "io.openpype.creators.maya.look": "io.ayon.creators.maya.look",
        "io.openpype.creators.maya.matchmove": "io.ayon.creators.maya.matchmove",
        "io.openpype.creators.maya.mayascene": "io.ayon.creators.maya.mayascene",
        "io.openpype.creators.maya.mayausd": "io.ayon.creators.maya.mayausd",
        "io.openpype.creators.maya.mayausdlayer": (
            "io.ayon.creators.maya.mayausdlayer"
        ),
        "io.openpype.creators.maya.model": "io.ayon.creators.maya.model",
        "io.openpype.creators.maya.multishotlayout": (
            "io.ayon.creators.maya.multishotlayout"
        ),
        "io.openpype.creators.maya.mvlook": "io.ayon.creators.maya.mvlook",
        "io.openpype.creators.maya.mvusdasset": (
            "io.ayon.creators.maya.mvusdasset"
        ),
        "io.openpype.creators.maya.mvusdcomposition": (
            "io.ayon.creators.maya.mvusdcomposition"
        ),
        "io.openpype.creators.maya.mvusdoverride": (
            "io.ayon.creators.maya.mvusdoverride"
        ),
        "io.openpype.creators.maya.oxcache": "io.ayon.creators.maya.oxcache",
        "io.openpype.creators.maya.oxrig": "io.ayon.creators.maya.oxrig",
        "io.openpype.creators.maya.pointcache": (
            "io.ayon.creators.maya.pointcache"
        ),
        "io.openpype.creators.maya.proxyabc": "io.ayon.creators.maya.proxyabc",
        "io.openpype.creators.maya.redshiftproxy": (
            "io.ayon.creators.maya.redshiftproxy"
        ),
        "io.openpype.creators.maya.renderlayer": (
            "io.ayon.creators.maya.renderlayer"
        ),
        "io.openpype.creators.maya.rendersetup": (
            "io.ayon.creators.maya.rendersetup"
        ),
        "io.openpype.creators.maya.review": "io.ayon.creators.maya.review",
        "io.openpype.creators.maya.rig": "io.ayon.creators.maya.rig",
        "io.openpype.creators.maya.setdress": "io.ayon.creators.maya.setdress",
        "io.openpype.creators.maya.unrealskeletalmesh": (
            "io.ayon.creators.maya.unrealskeletalmesh"
        ),
        "io.openpype.creators.maya.unrealstaticmesh": (
            "io.ayon.creators.maya.unrealstaticmesh"
        ),
        "io.openpype.creators.maya.unrealyeticache": (
            "io.ayon.creators.maya.unrealyeticache"
        ),
        "io.openpype.creators.maya.vrayproxy": "io.ayon.creators.maya.vrayproxy",
        "io.openpype.creators.maya.vrayscene": "io.ayon.creators.maya.vrayscene",
        "io.openpype.creators.maya.workfile": "io.ayon.creators.maya.workfile",
        "io.openpype.creators.maya.xgen": "io.ayon.creators.maya.xgen",
        "io.openpype.creators.maya.yeticache": "io.ayon.creators.maya.yeticache",
        "io.openpype.creators.maya.yetirig": "io.ayon.creators.maya.yetirig",
    }


    def find_instances(self):

        self.cache_instance_data(self.collection_shared_data)
        legacy = self.collection_shared_data.get(
            "maya_cached_legacy_instances"
        )
        if not legacy:
            return

        self.add_convertor_item("Convert legacy instances")

    def convert(self):
        self.remove_convertor_item()

        # We can't use the collected shared data cache here
        # we re-query it here directly to convert all found.
        cache = {}
        self.cache_instance_data(cache)
        legacy = cache.get("maya_cached_legacy_instances")
        if not legacy:
            return

        # From all current new style manual creators find the mapping
        # from product type to identifier
        product_base_type_to_id = {}
        for identifier, creator in self.create_context.creators.items():
            product_base_type = creator.product_base_type
            if not product_base_type:
                continue

            if product_base_type in product_base_type_to_id:
                # We have a clash of product type -> identifier. Multiple
                # new style creators use the same product type
                self.log.warning(
                    f"Clash on product type->identifier: {identifier}"
                )
            product_base_type_to_id[product_base_type] = identifier

        product_base_type_to_id.update(self.product_base_type_mapping)

        # We also embed the current 'task' into the instance since legacy
        # instances didn't store that data on the instances. The old style
        # logic was thus to be live to the current task to begin with.
        data = dict()
        data["task"] = self.create_context.get_current_task_name()
        for legacy_key, instance_nodes in legacy.items():
            creator_id = (
                self.creator_identifier_mapping.get(legacy_key)
                or product_base_type_to_id.get(legacy_key)
            )
            if creator_id is None:
                self.log.warning((
                    "Unable to convert legacy instance with family '{}'"
                    " because there is no matching new creator"
                ).format(legacy_key))
                continue

            creator = self.create_context.creators.get(creator_id)
            if creator is None:
                self.log.warning((
                    "Unable to convert legacy instance with family '{}'"
                    " because creator '{}' is not available"
                ).format(legacy_key, creator_id))
                continue

            self.log.info(
                "Converting legacy instance '{}' to creator '{}'",
                legacy_key, creator_id
            )
            data["creator_identifier"] = creator_id
            if isinstance(creator, plugin.RenderlayerCreator):
                self._convert_per_renderlayer(instance_nodes, data, creator)
            else:
                self._convert_regular(instance_nodes, data)

        # The scene changed while converting; drop the cached instance data so
        # that the creators collect the converted instances during this
        # publish instead of the legacy ones cached before the conversion.
        try:
            shared_data = self.collection_shared_data
        except Exception:  # noqa: BLE001
            # Not in a collection phase (e.g. driven by a script or a test):
            # there is no cache to clear.
            shared_data = None
        if shared_data is not None:
            shared_data.pop("maya_cached_instance_data", None)
            shared_data.pop("maya_cached_legacy_instances", None)

    def _convert_regular(self, instance_nodes, data):
        # We only imprint the creator identifier for it to identify
        # as the new style creator
        for instance_node in instance_nodes:
            self.imprint_instance_node(instance_node,
                                       data=data.copy())

    def _convert_per_renderlayer(self, instance_nodes, data, creator):
        # Split the instance into an instance per layer
        rs = renderSetup.instance()
        layers = rs.getRenderLayers()
        if not layers:
            self.log.error(
                "Can't convert legacy renderlayer instance because no existing"
                " renderSetup layers exist in the scene."
            )
            return

        creator_attribute_names = {
            attr_def.key for attr_def in creator.get_instance_attr_defs()
        }

        for instance_node in instance_nodes:

            # Ensure we have the new style singleton node generated
            # TODO: Make function public
            singleton_node = creator._get_singleton_node()
            if singleton_node:
                self.log.error(
                    "Can't convert legacy renderlayer instance '{}' because"
                    " new style instance '{}' already exists".format(
                        instance_node,
                        singleton_node
                    )
                )
                continue

            creator.create_singleton_node()

            # We are creating new nodes to replace the original instance
            # Copy the attributes of the original instance to the new node
            original_data = read(instance_node)

            # The product type gets converted to the new product type (this
            # is due to "rendering" being converted to "renderlayer")
            original_data["productBaseType"] = creator.product_base_type

            # recreate product name as without it would be
            # `renderingMain` vs correct `renderMain`
            project_name = self.create_context.get_current_project_name()
            folder_entities = list(ayon_api.get_folders(
                project_name, folder_names=[original_data["asset"]]
            ))
            if not folder_entities:
                cmds.delete(instance_node)
                continue
            folder_entity = folder_entities[0]
            task_entity = ayon_api.get_task_by_name(
                project_name, folder_entity["id"], data["task"]
            )

            product_name = creator.get_product_name(
                project_name,
                folder_entity,
                task_entity,
                original_data["variant"],
            )
            original_data["productName"] = product_name

            # Convert to creator attributes when relevant
            creator_attributes = {}
            for key in list(original_data.keys()):
                # Iterate in order of the original attributes to preserve order
                # in the output creator attributes
                if key in creator_attribute_names:
                    creator_attributes[key] = original_data.pop(key)
            original_data["creator_attributes"] = creator_attributes

            # For layer in maya layers
            for layer in layers:
                layer_instance_node = creator.find_layer_instance_node(layer)
                if not layer_instance_node:
                    # TODO: Make function public
                    layer_instance_node = creator._create_layer_instance_node(
                        layer
                    )

                # Transfer the main attributes of the original instance
                layer_data = original_data.copy()
                layer_data.update(data)

                self.imprint_instance_node(layer_instance_node,
                                           data=layer_data)

            # Delete the legacy instance node
            cmds.delete(instance_node)
