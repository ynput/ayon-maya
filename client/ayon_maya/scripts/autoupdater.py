"""Script for automatically creating and publishing assets after importing in Maya."""
import os
import argparse

from ayon_core.pipeline import registered_host, tempdir
from ayon_core.pipeline.create import CreateContext
from ayon_core.pipeline.publish import PublishLogic
from maya import cmds


def auto_updater(
    filepath: str,
    product_base_type: str,
    variant: str
) -> None:
    """Automatically create and publish the assets after importing.

    Args:
        filepath (str): File path of the imported asset.
        product_base_type (str): Product base type for the asset to be published.
        variant (str): Variant of the asset.
    """
    nodes = cmds.file(
        filepath, sharedReferenceFile=False, returnNewNodes=True
    )
    nodes = cmds.ls(nodes, type="transform", long=True)

    host = registered_host()
    create_context = CreateContext(host)
    creator_identifier = f"io.openpype.creators.maya.{product_base_type}"
    cmds.select(nodes, noExpand=True)
    create_context.create(
        creator_identifier=creator_identifier,
        variant=variant,
        pre_create_data={"use_selection": True}
    )

    logic = PublishLogic()
    logic.publish()

    if logic.has_finished():
        print("Publish finished successfully.")
    elif logic.has_failed():
        staging_dir = tempdir()
        os.makedirs(staging_dir, exist_ok=True)
        report_path = os.path.join(staging_dir, "publish_report.json")
        logic.store_publish_report(report_path)
        print(f"Publish failed. Report saved to: {report_path}")

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
        product_base_type=args.product_base_type,
        variant=args.variant,
    )
