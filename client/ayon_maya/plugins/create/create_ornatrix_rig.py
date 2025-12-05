import inspect
from ayon_maya.api import plugin


class CreateOxRig(plugin.MayaCreator):
    """Output for Ornatrix nodes"""

    identifier = "io.ayon.creators.maya.oxrig"
    label = "Ornatrix Rig"
    product_type = "oxrig"
    product_base_type = "oxrig"
    icon = "usb"
    description = "Ornatrix Rig"

    def get_detail_description(self):
        return inspect.cleandoc("""
            ### Ornatrix Rig
            
            The Ornatrix rig creator allows you to publish a re-usable rig to
            easily load your prepared Ornatrix hair/fur for an asset and apply
            them elsewhere for simulation or rendering by connecting it to 
            the animated pointcaches.
            
            The Ornatrix Rig instance object set should include the meshes with
            the connected Ornatrix hairs, usually the `HairShape` with the 
            `EditGuidesShape`.
            
            For more details, see the [AYON Maya Ornatrix Artist documentation](https://ayon.ynput.io/docs/addon_maya_ornatrix_artist/).
        """  # noqa
        )
