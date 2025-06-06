import os
import pyblish.api
from ayon_maya.api import plugin


class CollectDataforCache(plugin.MayaInstancePlugin):
    """Collect data for caching to Deadline."""

    # Run after Collect Frames
    order = pyblish.api.CollectorOrder + 0.4991
    families = ["publish.farm"]
    targets = ["local", "remote"]
    label = "Collect Data for Cache"

    def process(self, instance):
        # Should we implement this in somewhere else?
        tmp_staging_dir = os.path.join(os.environ["AYON_WORKDIR"], "cache", "alembic")
        os.makedirs(tmp_staging_dir, exist_ok=True)
        # TODO: Support format other than alembic
        filename = "{name}.abc".format(**instance.data)
        expected_filepath = os.path.join(tmp_staging_dir, filename)
        files = instance.data.setdefault("files", list())
        files.append(expected_filepath)
        expected_files = instance.data.setdefault("expectedFiles", list())
        expected_files.append({"cache": files})
        instance.data.update({
            # used in MayaCacheSubmitDeadline in ayon-deadline
            "plugin": "MayaBatch",
            "publish": True,
            "byFrameStep": instance.data.get(
                "creator_attributes", {}).get(
                    "step", 1.0)
        })
