# -*- coding: utf-8 -*-
import os

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ExtractObj(plugin.MayaExtractorPlugin,
                 OptionalPyblishPluginMixin):
    """Extract OBJ from Maya.

    This extracts reproducible OBJ exports ignoring any of the settings
    set on the local machine in the OBJ export options window.

    """
    order = pyblish.api.ExtractorOrder
    label = "Extract OBJ"
    families = ["model"]

    # Default OBJ export options.
    obj_options = {
        "groups": 1,
        "ptgroups": 1,
        "materials": 0,
        "smoothing": 1,
        "normals": 1,
    }

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Define output path

        staging_dir = self.staging_dir(instance)
        filename = "{0}.obj".format(instance.name)
        path = os.path.join(staging_dir, filename)

        # The export requires forward slashes because we need to
        # format it into a string in a mel expression

        self.log.debug("Extracting OBJ to: {0}".format(path))

        members = instance.data("setMembers")
        members = cmds.ls(members,
                          dag=True,
                          shapes=True,
                          type=("mesh", "nurbsCurve"),
                          noIntermediate=True,
                          long=True)
        self.log.debug("Members: {0}".format(members))
        self.log.debug("Instance: {0}".format(instance[:]))

        if not cmds.pluginInfo('objExport', query=True, loaded=True):
            cmds.loadPlugin('objExport')

        # Check if shaders should be included as part of the model export. If
        # False, the default shader is assigned to the geometry.
        include_shaders = instance.data.get("include_shaders", False)
        options = self.obj_options.copy()
        if include_shaders:
            options["materials"] = 1

            # Materials for `.obj` files are exported to a `.mtl` file that
            # usually lives next to the `.obj` and is referenced to by filename
            # from the `.obj` file itself, like:
            # mtllib modelMain.mtl
            # We want to copy the file over and preserve the filename for
            # the materials to load correctly for the obj file, so we add it
            # as explicit file transfer
            mtl_source = path[:-len(".obj")] + ".mtl"
            mtl_filename = os.path.basename(mtl_source)
            mtl_destination = os.path.join(instance.data["publishDir"],
                                           mtl_filename)
            transfers = instance.data.setdefault("transfers", [])
            transfers.append((mtl_source, mtl_destination))

        # Format options for the OBJexport command.
        options_str = ';'.join(
            f"{key}={val}" for key, val in options.items()
        )

        # Export    
        with lib.no_display_layers(instance):
            with lib.displaySmoothness(members,
                                       divisionsU=0,
                                       divisionsV=0,
                                       pointsWire=4,
                                       pointsShaded=1,
                                       polygonObject=1):
                with lib.maintained_selection():
                    cmds.select(members, noExpand=True)
                    cmds.file(path,
                              exportSelected=True,
                              type='OBJexport',
                              op=options_str,
                              preserveReferences=True,
                              force=True)

        if "representation" not in instance.data:
            instance.data["representation"] = []

        representation = {
            'name': 'obj',
            'ext': 'obj',
            'files': filename,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extract OBJ successful to: {0}".format(path))
