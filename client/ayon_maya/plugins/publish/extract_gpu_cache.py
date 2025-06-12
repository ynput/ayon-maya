import json

from ayon_core.pipeline import publish
from ayon_maya.api import plugin
from maya import cmds


class ExtractGPUCache(plugin.MayaExtractorPlugin,
                      publish.OptionalPyblishPluginMixin):
    """Extract the content of the instance to a GPU cache file."""

    label = "GPU Cache"
    families = ["model", "animation", "pointcache"]
    targets = ["local", "remote"]
    step = 1.0
    stepSave = 1
    optimize = True
    optimizationThreshold = 40000
    optimizeAnimationsForMotionBlur = True
    writeMaterials = True
    useBaseTessellation = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if instance.data.get("farm"):
            self.log.debug("Should be processed on farm, skipping.")
            return

        cmds.loadPlugin("gpuCache", quiet=True)

        staging_dir = self.staging_dir(instance)
        filename = "{}_gpu_cache".format(instance.name)

        # Write out GPU cache file.
        kwargs = {
            "directory": staging_dir,
            "fileName": filename,
            "saveMultipleFiles": False,
            "simulationRate": self.step,
            "sampleMultiplier": self.stepSave,
            "optimize": self.optimize,
            "optimizationThreshold": self.optimizationThreshold,
            "optimizeAnimationsForMotionBlur": (
                self.optimizeAnimationsForMotionBlur
            ),
            "writeMaterials": self.writeMaterials,
            "useBaseTessellation": self.useBaseTessellation
        }
        self.log.debug(
            "Extract {} with:\n{}".format(
                instance[:], json.dumps(kwargs, indent=4, sort_keys=True)
            )
        )
        cmds.gpuCache(instance[:], **kwargs)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            "name": "gpu_cache",
            "ext": "abc",
            "files": filename + ".abc",
            "stagingDir": staging_dir,
            "outputName": "gpu_cache"
        }

        instance.data["representations"].append(representation)

        self.log.debug(
            "Extracted instance {} to: {}".format(instance.name, staging_dir)
        )
