import os
import shutil

from ayon_maya.api import plugin
import maya.cmds as cmds
import xgenm
from ayon_maya.api import current_file
from ayon_maya.api.lib import (
    attribute_values,
    get_container_members,
    maintained_selection,
    write_xgen_file,
)
from qtpy import QtWidgets


class XgenLoader(plugin.ReferenceLoader):
    """Load Xgen as reference"""

    product_types = {"xgen"}
    representations = {"ma", "mb"}

    label = "Reference Xgen"
    icon = "code-fork"
    color = "orange"

    def get_xgen_xgd_paths(self, palette):
        _, maya_extension = os.path.splitext(current_file())
        xgen_file = current_file().replace(
            maya_extension,
            "__{}.xgen".format(palette.replace("|", "").replace(":", "__"))
        )
        xgd_file = xgen_file.replace(".xgen", ".xgd")
        return xgen_file, xgd_file

    def process_reference(self, context, name, namespace, options):
        # Validate workfile has a path.
        if current_file() is None:
            QtWidgets.QMessageBox.warning(
                None,
                "",
                "Current workfile has not been saved. Please save the workfile"
                " before loading an Xgen."
            )
            return

        maya_filepath = self.prepare_root_value(
            file_url=self.filepath_from_context(context),
            project_name=context["project"]["name"]
        )

        # Reference xgen. Xgen does not like being referenced in under a group.
        with maintained_selection():
            nodes = cmds.file(
                maya_filepath,
                namespace=namespace,
                sharedReferenceFile=False,
                reference=True,
                returnNewNodes=True
            )

            xgen_palette = cmds.ls(
                nodes, type="xgmPalette", long=True
            )[0].replace("|", "")

            xgen_file, xgd_file = self.get_xgen_xgd_paths(xgen_palette)
            self.set_palette_attributes(xgen_palette, xgen_file, xgd_file)

            # Change the cache and disk values of xgDataPath and xgProjectPath
            # to ensure paths are setup correctly.
            project_path = os.path.dirname(current_file()).replace("\\", "/")
            xgenm.setAttr("xgProjectPath", project_path, xgen_palette)
            data_path = "${{PROJECT}}xgen/collections/{};{}".format(
                xgen_palette.replace(":", "__ns__"),
                xgenm.getAttr("xgDataPath", xgen_palette)
            )
            xgenm.setAttr("xgDataPath", data_path, xgen_palette)

            data = {"xgProjectPath": project_path, "xgDataPath": data_path}
            write_xgen_file(data, xgen_file)

            # This create an expression attribute of float. If we did not add
            # any changes to collection, then Xgen does not create an xgd file
            # on save. This gives errors when launching the workfile again due
            # to trying to find the xgd file.
            name = "custom_float_ignore"
            if name not in xgenm.customAttrs(xgen_palette):
                xgenm.addCustomAttr(
                    "custom_float_ignore", xgen_palette
                )

            shapes = cmds.ls(nodes, shapes=True, long=True)

            new_nodes = (list(set(nodes) - set(shapes)))

            self[:] = new_nodes

        return new_nodes

    def set_palette_attributes(self, xgen_palette, xgen_file, xgd_file):
        cmds.setAttr(
            "{}.xgBaseFile".format(xgen_palette),
            os.path.basename(xgen_file),
            type="string"
        )
        cmds.setAttr(
            "{}.xgFileName".format(xgen_palette),
            os.path.basename(xgd_file),
            type="string"
        )
        cmds.setAttr("{}.xgExportAsDelta".format(xgen_palette), True)

    def update(self, container, context):
        """Workflow for updating Xgen.

        - Export changes to delta file.
        - Copy and overwrite the workspace .xgen file.
        - Set collection attributes to not include delta files.
        - Update xgen maya file reference.
        - Apply the delta file changes.
        - Reset collection attributes to include delta files.

        We have to do this workflow because when using referencing of the xgen
        collection, Maya implicitly imports the Xgen data from the xgen file so
        we dont have any control over when adding the delta file changes.

        There is an implicit increment of the xgen and delta files, due to
        using the workfile basename.
        """
        # Storing current description to try and maintain later.
        current_description = (
            xgenm.xgGlobal.DescriptionEditor.currentDescription()
        )

        container_node = container["objectName"]
        members = get_container_members(container_node)
        xgen_palette = cmds.ls(
            members, type="xgmPalette", long=True
        )[0].replace("|", "")
        xgen_file, xgd_file = self.get_xgen_xgd_paths(xgen_palette)

        # Export current changes to apply later.
        xgenm.createDelta(xgen_palette.replace("|", ""), xgd_file)

        self.set_palette_attributes(xgen_palette, xgen_file, xgd_file)

        maya_file = self.filepath_from_context(context)
        _, extension = os.path.splitext(maya_file)
        new_xgen_file = maya_file.replace(extension, ".xgen")
        data_path = ""
        with open(new_xgen_file, "r") as f:
            for line in f:
                if line.startswith("\txgDataPath"):
                    line = line.rstrip()
                    data_path = line.split("\t")[-1]
                    break

        project_path = os.path.dirname(current_file()).replace("\\", "/")
        data_path = "${{PROJECT}}xgen/collections/{};{}".format(
            xgen_palette.replace(":", "__ns__"),
            data_path
        )
        data = {"xgProjectPath": project_path, "xgDataPath": data_path}
        shutil.copy(new_xgen_file, xgen_file)
        write_xgen_file(data, xgen_file)

        attribute_data = {
            "{}.xgFileName".format(xgen_palette): os.path.basename(xgen_file),
            "{}.xgBaseFile".format(xgen_palette): "",
            "{}.xgExportAsDelta".format(xgen_palette): False
        }
        with attribute_values(attribute_data):
            super().update(container, context)

            xgenm.applyDelta(xgen_palette.replace("|", ""), xgd_file)

        # Restore current selected description if it exists.
        if cmds.objExists(current_description):
            xgenm.xgGlobal.DescriptionEditor.setCurrentDescription(
                current_description
            )
        # Full UI refresh.
        xgenm.xgGlobal.DescriptionEditor.refresh("Full")
