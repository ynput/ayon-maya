from ayon_maya.api import (
    plugin,
    lib
)
from ayon_core.lib import (
    BoolDef,
    TextDef
)


class CreateLook(plugin.MayaCreator):
    """Shader connections defining shape look"""

    identifier = "io.openpype.creators.maya.look"
    label = "Look"
    product_type = "look"
    product_base_type = "look"

    icon = "paint-brush"

    make_tx = True
    rs_tex = False
    include_texture_reference_objects = False

    def create(self, product_name, instance_data, pre_create_data):
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        for key in [
            "maketx",
            "rstex",
            "includeTextureReferenceObjects"
        ]:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]
        return super().create(product_name, instance_data, pre_create_data)

    def get_instance_attr_defs(self):

        return [
            # TODO: This value should actually get set on create!
            TextDef("renderLayer",
                    # TODO: Bug: Hidden attribute's label is still shown in UI?
                    hidden=True,
                    default=lib.get_current_renderlayer(),
                    label="Renderlayer",
                    tooltip="Renderlayer to extract the look from"),
            BoolDef("maketx",
                    label="MakeTX",
                    tooltip="Whether to generate .tx files for your textures",
                    default=self.make_tx),
            BoolDef("rstex",
                    label="Convert textures to .rstex",
                    tooltip="Whether to generate Redshift .rstex files for "
                            "your textures",
                    default=self.rs_tex),
            BoolDef("includeTextureReferenceObjects",
                    label="Texture Reference Objects",
                    tooltip=(
                        "Whether to include texture reference objects "
                        "with the published look to reconnect to geometry "
                        "when assigning the look."
                    ),
                    default=self.include_texture_reference_objects)
        ]

    def get_pre_create_attr_defs(self):
        # Show same attributes on create but include use selection
        defs = list(super().get_pre_create_attr_defs())
        defs.extend(self.get_instance_attr_defs())
        return defs
