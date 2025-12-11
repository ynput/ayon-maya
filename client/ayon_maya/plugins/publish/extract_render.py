from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel


class ExtractLocalRender(plugin.MayaExtractorPlugin):
    """Extract local render

    Note that we do not target the 'render.local' instances here. That's
    because a single layer may have multiple AOV file outputs but we never
    want to trigger multiple renders for the same layer. Instead, we only
    target the 'renderlayer' instances here which represent a single layer
    to be rendered. But we still need to respect the local render flag in that
    case.
    """

    label = "Extract Local Render"
    families = ["renderlayer"]

    def process(self, instance):
        # Skip if explicitly marked for farm
        if instance.data.get("farm"):
            self.log.debug("Instance marked for farm, skipping local render.")
            return

        if instance.data.get("creator_attributes", {}).get(
            "render_target"
        ) != "local":
            self.log.debug(
                "Instance render target is not local, skipping local render."
            )
            return

        frame_start: int = instance.data["frameStartHandle"]
        frame_end: int = instance.data["frameEndHandle"]
        step: int = int(instance.data.get("step", 1))

        # Get the render layer from the instance data using the legacy layer
        # node name
        layer: str = instance.data["setMembers"]

        with lib.maintained_time():
            for t in range(frame_start, frame_end + 1, step):
                cmds.currentTime(t)
                mel.eval(
                    f'mayaBatchRenderProcedure(0, "", "{layer}", "", "");'
                )
