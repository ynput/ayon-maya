"""Script for automatically creating and publishing assets after importing in Maya."""
import json
import os
import argparse

from ayon_core.pipeline import registered_host, tempdir
from ayon_core.pipeline.create import CreateContext
from ayon_core.pipeline.publish import PublishLogic
from ayon_core.pipeline.context_tools import change_current_context
from ayon_api import get_folder_by_name, get_task_by_name
from maya import cmds


def auto_updater(
    filepath: str,
    productBaseType: str,
    folder_name: str,
    task_name: str,
    variant: str
) -> None:
    """Automatically create and publish the assets after importing.

    Args:
        filepath (str): File path of the imported asset.
        folder_name (str): folder name where the asset will be published.
        task_name (str): Task name where the asset will be published.
        productBaseType (str): Product base type for the asset to be published.
        variant (str): Variant of the asset.
    """
    nodes = cmds.file(
        filepath, sharedReferenceFile=False, returnNewNodes=True
    )
    shapes = cmds.ls(nodes, shapes=True, long=True)
    new_nodes = (list(set(nodes) - set(shapes)))

    host = registered_host()
    create_context = CreateContext(host)
    creator_identifier = f"io.openpype.creators.maya.{productBaseType}"
    cmds.select(new_nodes, noExpand=True)
    create_context.create(
        creator_identifier=creator_identifier,
        variant=variant,
        pre_create_data={"use_selection": True}
    )
    project_name = create_context.get_current_project_name()
    folder_entity = get_folder_by_name(project_name, folder_name)
    task_entity = get_task_by_name(project_name, folder_entity["id"], task_name)

    if (
        folder_entity != create_context.get_current_folder_entity() or
        task_entity != create_context.get_current_task_entity()
    ):
        change_current_context(
            folder_entity=folder_entity,
            task_entity=task_entity
        )

    logic = PublishLogic()
    logic.publish()

    if logic.has_finished():
        print("Publish finished successfully.")
    elif logic.has_failed():
        report = logic.get_publish_report()
        print(json.dumps(report, indent=2))
        report_dir = os.path.join(tempdir(), "publish_report.json")
        with open(report_dir, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Publish failed. Report saved to: {report_dir}")

if __name__ == "__main__":
    # Parse command-line arguments
    # Usage: mayapy.exe autoupdater.py <filepath> <folder_name> <task_name> [productBaseType] [variant]
    parser = argparse.ArgumentParser(
        description="Import a file, create a product, and publish in Maya."
    )
    parser.add_argument(
        "--filepath",
        required=True,
        help="Path to the asset file to import (e.g., .abc, .mb, .ma)."
    )
    parser.add_argument(
        "--folderPath",
        required=True,
        help="Folder path where the product will be published."
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task name under which the product will be published (default: Modeling)."
    )
    parser.add_argument(
        "--variant",
        required=True,
        help="Variant name for the product (e.g., 'v001', 'main')."
    )
    parser.add_argument(
        "--product-base-type",
        default="model",
        required=True,
        help="Product base type (e.g., model, camera, rig). Default: model."
    )

    args = parser.parse_args()

    auto_updater(
        filepath=args.filepath,
        folder_name=args.folderPath,
        task_name=args.task,
        productBaseType=args.product_base_type,
        variant=args.variant,
    )
