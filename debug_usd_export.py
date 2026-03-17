#!/usr/bin/env python3
"""Debug script to check USD export output.

This script exports the animation cache and shows exactly what was exported.
"""

import maya.cmds as cmds
from pxr import Sdf, Usd
import os
import json


def debug_export():
    """Export and analyze the USD structure."""

    # Export path
    export_file = "/tmp/debug_animation_cache.usd"

    # Get some animated transforms from the scene
    transforms = cmds.ls(type="transform", long=True)
    animated = []

    for xf in transforms[:5]:  # Test with first 5
        if cmds.keyframe(xf, query=True, name=True):
            animated.append(xf)

    if not animated:
        print("No animated transforms found!")
        return

    print(f"Found {len(animated)} animated transforms")
    print(f"Exporting to: {export_file}")

    # Test export with current options
    print("\n=== EXPORT OPTIONS ===")
    options = {
        "file": export_file,
        "frameRange": (1, 100),
        "frameStride": 1.0,
        "stripNamespaces": True,
        "exportRoots": animated,
        "mergeTransformAndShape": False,
        "exportDisplayColor": False,
        "exportVisibility": False,
        "exportComponentTags": False,
        "staticSingleSample": False,
        "defaultUSDFormat": "usd",
        "filterTypes": [
            "mesh",
            "constraint",
            "camera",
            "light",
            "shader",
            "place2dTexture",
        ]
    }

    for key, val in options.items():
        print(f"  {key}: {val}")

    print("\n=== ATTEMPTING EXPORT ===")
    try:
        # Try with current options
        cmds.select(animated, replace=True, noExpand=True)
        cmds.mayaUSDExport(**options)
        print("✓ Export succeeded")
    except Exception as e:
        print(f"✗ Export failed: {e}")
        print("\nTrying without filterTypes...")

        del options["filterTypes"]
        try:
            cmds.mayaUSDExport(**options)
            print("✓ Export succeeded without filterTypes")
        except Exception as e2:
            print(f"✗ Still failed: {e2}")
            return

    # Analyze exported file
    if not os.path.exists(export_file):
        print(f"\n✗ File not created: {export_file}")
        return

    print(f"\n=== ANALYZING EXPORT ===")
    print(f"File size: {os.path.getsize(export_file)} bytes")
    print(f"File format: {'Binary (.usd)' if not export_file.endswith('.usda') else 'ASCII (.usda)'}")

    # Load and analyze
    stage = Usd.Stage.Open(export_file)
    if not stage:
        print("Could not open stage with Usd.Stage.Open()")
        # Try with Sdf for debugging
        try:
            layer = Sdf.Layer.FindOrOpen(export_file)
            if layer:
                print(f"Opened with Sdf.Layer: {layer.identifier}")
                print(f"Root prims: {[p.name for p in layer.rootPrims]}")
        except Exception as e:
            print(f"Could not open with Sdf either: {e}")
        return

    print(f"Opened stage successfully")
    print(f"Root prims: {[p.GetName() for p in stage.GetRootLayer().rootPrims]}")

    # Analyze structure
    def print_hierarchy(prim, indent=0):
        prefix = "  " * indent
        prim_type = prim.GetTypeName() or "Xform"
        has_anim = "✓ animated" if prim.GetVariantSets().GetNames() or hasattr(prim, 'Get') else ""

        # Check for timeSamples
        has_samples = False
        attrs = prim.GetAttributes()
        for attr in attrs:
            if attr.GetTimeSamples():
                has_samples = True
                break

        anim_marker = " [HAS TIMESAMPLE]" if has_samples else ""
        print(f"{prefix}{prim.GetName()} ({prim_type}){anim_marker}")

        for child in prim.GetChildren():
            print_hierarchy(child, indent + 1)

    print("\n=== HIERARCHY ===")
    for prim in stage.GetRootLayer().rootPrims:
        print_hierarchy(stage.GetPrimAtPath(prim.path))

    # Check for transforms with animation
    print("\n=== TRANSFORM ANIMATION CHECK ===")
    for prim in stage.Traverse():
        if prim.GetTypeName() in ["Xform", "Transform"]:
            # Check xformOp attributes
            xform_attrs = [a for a in prim.GetAttributes() if "xformOp" in a.GetName()]
            if xform_attrs:
                for attr in xform_attrs:
                    samples = attr.GetTimeSamples()
                    if samples:
                        print(f"  {prim.GetPath()}")
                        print(f"    {attr.GetName()}: {len(samples)} samples")
                        print(f"      Times: {sorted(list(samples))[:5]}...")  # First 5 times
                    else:
                        print(f"  {prim.GetPath()} - {attr.GetName()}: NO SAMPLES (static)")

    print("\n=== EXPORT DIAGNOSTICS ===")
    print(f"Check the exported file at: {export_file}")
    if export_file.endswith('.usd'):
        print("File is binary USD - can't read directly")
        print("Try: usdcat /tmp/debug_animation_cache.usd | head -50")
    else:
        print("File is ASCII USDA - can be read directly")
        print("Try: head -50 /tmp/debug_animation_cache.usd")


if __name__ == "__main__":
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    debug_export()
