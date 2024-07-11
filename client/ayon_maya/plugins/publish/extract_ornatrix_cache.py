import os
import json
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel
from ayon_maya.api.lib import get_frame_range


class ExtractOxCache(plugin.MayaExtractorPlugin):
    """Producing Ornatrix cache files using scene time range.

    This will extract Ornatrix cache file sequence and fur settings.
    """

    label = "Extract Ornatrix Cache"
    families = ["oxrig", "oxcache"]

    def process(self, instance):
        cmds.loadPlugin("Ornatrix", quiet=True)
        # Define extract output file path
        ox_nodes = cmds.ls(instance[:], shapes=True, long=True)
        ox_shape_nodes = cmds.ls(ox_nodes, type="HairShape")
        self.log.debug(f"{ox_shape_nodes}")
        dirname = self.staging_dir(instance)
        # Start writing the files for snap shot
        ox_abc_path = os.path.join(dirname, f"{instance.name}ornatrix.abc")
        with lib.maintained_selection():
            cmds.select(ox_shape_nodes)
            self._extract(instance, ox_abc_path)
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
        """Export Ornatrix Alembic by Mel Script.

        Args:
            filepath (str): output filepath
            attr_values (dict): creator attributes data
        """
        attr_values = instance.data["creator_attributes"]
        filepath = filepath.replace("\\", "/")
        frame_range = get_frame_range(instance.data["taskEntity"])
        frameStart = attr_values.get("frameStart", frame_range["frameStart"])
        frameEnd = attr_values.get("frameEnd", frame_range["frameEnd"])
        frameStep = attr_values.get("step", 1.0)
        exp_format = attr_values.get("format", 0)
        ox_base_command = f'OxAlembicExport "{filepath}" -ft "{frameStart}" -tt "{frameEnd}" -s {frameStep} -f {exp_format}'        # noqa
        ox_export_options = [ox_base_command]
        if attr_values.get("renderVersion", False):
            ox_export_options.append("-r")
        up_axis_command = "-up {upDirection}".format(
            upDirection=attr_values.get("upDirection", 0))
        ox_export_options.append(up_axis_command)
        if attr_values.get("exportVelocities", False):
            ox_export_options.append("-v")
        interval_velocity_cmd = "-vic {int_center} -vil {int_len}".format(
            int_center=attr_values.get("velocityIntervalCenter", 0.0),
            int_len=attr_values.get("velocityIntervalLength", 0.5)
        )
        ox_export_options.append(interval_velocity_cmd)
        ox_export_cmd = " ".join(ox_export_options)
        return mel.eval(f"{ox_export_cmd};")
