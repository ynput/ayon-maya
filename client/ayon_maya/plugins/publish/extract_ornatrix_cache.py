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
    targets = ["local", "remote"]

    def process(self, instance):
        cmds.loadPlugin("Ornatrix", quiet=True)
        dirname = self.staging_dir(instance)

        ox_nodes = cmds.ls(instance[:], shapes=True, long=True)
        ox_shape_nodes = cmds.ls(ox_nodes, type="HairShape")
        self.log.debug(
            f"Ornatrix HairShape nodes to extract: {ox_shape_nodes}")

        # Export the Alembic
        ox_abc_path = os.path.join(dirname, f"{instance.name}_ornatrix.abc")
        self._extract(instance, ox_shape_nodes, ox_abc_path)

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

    def _extract(self, instance, ox_shape_nodes, filepath):
        """Export Ornatrix Alembic by using `OxAlembicExport` command.

        Args:
            instance (pyblish.api.Instance): Publish instance.
            filepath (str): output filepath
        """
        attrs = instance.data["creator_attributes"]
        frame_range = get_frame_range(instance.data["taskEntity"])
        frame_start = attrs.get("frameStart", frame_range["frameStart"])
        frame_end = attrs.get("frameEnd", frame_range["frameEnd"])

        options = dict(
            format=attrs.get("format", 0),
            fromTime=frame_start,
            toTime=frame_end,
            step=attrs.get("step", 1.0),
            renderVersion=attrs.get("renderVersion", False),
            upDirection=attrs.get("upDirection", 0),
            useWorldCoordinates=attrs.get("useWorldCoordinates", True),
            exportSurfacePositions=attrs.get("exportSurfacePositions", True),
            exportStrandData=attrs.get("exportStrandData", True),
            exportStrandIds=attrs.get("exportStrandIds", True),
            exportStrandGroups=attrs.get("exportStrandGroups", True),
            exportWidths=attrs.get("exportWidths", True),
            exportTextureCoordinates=attrs.get("exportTextureCoordinates",
                                               True),
            exportNormals=attrs.get("exportNormals", False),
            exportVelocities=attrs.get("exportVelocities", False),
            velocityIntervalCenter=attrs.get("velocityIntervalCenter", 0.0),
            velocityIntervalLength=attrs.get("velocityIntervalLength", 0.5),
            oneObjectPerFile=False,
            unrealEngineExport=False,
            exportEachStrandAsSeparateObject=False
        )
        for key, value in options.items():
            # Pass bool as int
            if isinstance(value, bool):
                options[key] = int(value)

        options_str = ";".join(
            f"{key}={value}" for key, value in options.items()
        )
        self.log.debug("Extracting Ornatrix Alembic with options: %s",
                       options_str)
        with lib.maintained_selection():
            cmds.select(ox_shape_nodes, noExpand=True)
            cmds.file(
                filepath,
                options=options_str,
                type="Ornatrix Alembic",
                exportSelected=True,
                force=True
            )
