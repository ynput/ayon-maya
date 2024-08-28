# -*- coding: utf-8 -*-
import os

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


def get_textures_from_mtl(mtl_filepath: str) -> "set[str]":
    """Return all textures from a OBJ `.mtl` sidecar file.
    
    Each line has a separate entry, like `map_Ka`, where the filename is the
    last argument on that line.

    Notes:
        Filenames with spaces in them are saved along with the `.obj` but with
        spaces replaced to underscores in the `.mtl` file so they can be
        detected as the single argument.
    
    Also see:
        https://paulbourke.net/dataformats/mtl/

    Arguments:
        mtl_filepath (str): Full path to `.mtl` file to parse.

    Returns:
        set[str]: Set of files referenced in the MTL file.
    """
    
    map_prefixes = (
        "map_Ka ", 
        "map_Kd ", 
        "map_Ks ", 
        "map_Ns ", 
        "map_d ", 
        "disp ", 
        "decal ",
        "bump ", 
        "refl "
    )

    folder = os.path.dirname(mtl_filepath)
    filepaths = set()
    with open(mtl_filepath, "r", encoding='utf-8') as f:
        for line in f.readlines():
            if line.startswith(map_prefixes):
                line = line.strip()  # strip of end of line
                filename = line.rsplit(" ", 1)[-1]
                filepath = os.path.join(folder, filename)
                filepaths.add(filepath)

    return filepaths


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

        if include_shaders:
            # Materials for `.obj` files are exported to a `.mtl` file that
            # usually lives next to the `.obj` and is referenced to by filename
            # from the `.obj` file itself, like:
            # mtllib modelMain.mtl
            # We want to copy the file over and preserve the filename for
            # the materials to load correctly for the obj file, so we add it
            # as explicit file transfer
            mtl_source = path[:-len(".obj")] + ".mtl"
            mtl_filename = os.path.basename(mtl_source)
            publish_dir = instance.data["publishDir"]
            mtl_destination = os.path.join(publish_dir, mtl_filename)
            transfers = instance.data.setdefault("transfers", [])
            transfers.append((mtl_source, mtl_destination))
            self.log.debug(f"Including .mtl file: {mtl_filename}")

            # Include any images from the obj export
            textures = get_textures_from_mtl(mtl_source)
            for texture_src in textures:
                texture_dest = os.path.join(publish_dir,
                                            os.path.basename(texture_src))
                self.log.debug(f"Including texture: {texture_src}")
                transfers.append((texture_src, texture_dest))

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
