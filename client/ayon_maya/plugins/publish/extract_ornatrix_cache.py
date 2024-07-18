import os
import json
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds
from ayon_maya.api.lib import get_frame_range


class ExtractOxCache(plugin.MayaExtractorPlugin):
    """Producing Ornatrix cache files using scene time range.

    This will extract Ornatrix cache file sequence and fur settings.
    """

    label = "Extract Ornatrix Cache"
    families = ["oxrig", "oxcache"]

    def process(self, instance):
        cmds.loadPlugin("Ornatrix", quiet=True)
        dirname = self.staging_dir(instance)

        ox_nodes = cmds.ls(instance[:], shapes=True, long=True)
        ox_shape_nodes = cmds.ls(ox_nodes, type="HairShape")
        self.log.debug(
            f"Ornatrix HairShape nodes to extract: {ox_shape_nodes}")

        # Export the Alembic
        ox_abc_path = os.path.join(dirname, f"{instance.name}_ornatrix.abc")
        with lib.maintained_selection():
            cmds.select(ox_shape_nodes, replace=True, noExpand=True)
            self._extract(instance, ox_abc_path)

        # Export the .cachesettings
        settings = instance.data["cachesettings"]
        self.log.debug("Writing metadata file")
        cachesettings_path = os.path.join(dirname, "ornatrix.cachesettings")
        with open(cachesettings_path, "w") as fp:
            json.dump(settings, fp, ensure_ascii=False)

        # build representations
        if "representations" not in instance.data:
            instance.data["representations"] = []

        instance.data["representations"].append(
            {
                'name': 'abc',
                'ext': 'abc',
                'files': os.path.basename(ox_abc_path),
                'stagingDir': dirname
            }
        )

        instance.data["representations"].append(
            {
                'name': 'cachesettings',
                'ext': 'cachesettings',
                'files': os.path.basename(cachesettings_path),
                'stagingDir': dirname
            }
        )

        self.log.debug("Extracted {} to {}".format(instance, dirname))

    def _extract(self, instance, filepath):
        """Export Ornatrix Alembic by using `OxAlembicExport` command.

        Args:
            instance (pyblish.api.Instance): Publish instance.
            filepath (str): output filepath
        """
        attr_values = instance.data["creator_attributes"]
        frame_range = get_frame_range(instance.data["taskEntity"])
        frame_start = attr_values.get("frameStart", frame_range["frameStart"])
        frame_end = attr_values.get("frameEnd", frame_range["frameEnd"])
        return cmds.OxAlembicExport(
            filepath,
            format=attr_values.get("format", 0),
            fromTime=frame_start,
            toTime=frame_end,
            step=attr_values.get("step", 1.0),
            renderVersion=attr_values.get("renderVersion", False),
            upDirection=attr_values.get("upDirection", 0),
            exportVelocities=attr_values.get("exportVelocities", False),
            velocityIntervalCenter=attr_values.get("velocityIntervalCenter",
                                                   0.0),
            velocityIntervalLength=attr_values.get("velocityIntervalLength",
                                                   0.5),
        )
