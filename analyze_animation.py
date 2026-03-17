#!/usr/bin/env python3
"""Find and select only animated transforms in the selection.

Run this before publishing to identify which transforms should be exported.
"""

import maya.cmds as cmds


def find_animated_transforms(nodes):
    """Find transforms that have animation (keyframes or curves).

    Args:
        nodes: List of node names/paths

    Returns:
        List of animated transform paths
    """
    animated = []

    for node in nodes:
        # Check if it's a transform
        if not cmds.objExists(node):
            continue

        node_type = cmds.nodeType(node)
        if node_type != "transform":
            continue

        # Check for keyframes on transform attributes
        has_keyframes = False
        for attr in ["translate", "rotate", "scale"]:
            for axis in ["X", "Y", "Z"]:
                full_attr = f"{node}.{attr}{axis}"
                if cmds.keyframe(full_attr, query=True, name=True):
                    has_keyframes = True
                    break
            if has_keyframes:
                break

        # Also check for animated curves connected
        if not has_keyframes:
            for attr in ["translate", "rotate", "scale"]:
                full_attr = f"{node}.{attr}"
                connections = cmds.listConnections(full_attr, type="animCurve") or []
                if connections:
                    has_keyframes = True
                    break

        if has_keyframes:
            animated.append(node)

    return animated


def analyze_selection():
    """Analyze current selection for animation."""
    selection = cmds.ls(selection=True, long=True)

    if not selection:
        print("No selection! Please select the rig or asset group.")
        return

    print("\n" + "="*70)
    print("ANIMATION ANALYSIS")
    print("="*70)

    print(f"\nSelected nodes ({len(selection)}):")
    for node in selection:
        print(f"  - {node}")

    # Get all descendants
    all_nodes = cmds.ls(selection, long=True, dagObjects=True)
    all_transforms = cmds.ls(all_nodes, type="transform", long=True)

    print(f"\nTotal transforms under selection: {len(all_transforms)}")

    # Find animated ones
    animated_transforms = find_animated_transforms(all_transforms)

    print(f"\nAnimated transforms ({len(animated_transforms)}):")
    for xf in animated_transforms:
        # Show short name for readability
        short_name = xf.split("|")[-1]
        print(f"  ✓ {short_name}")
        print(f"    Full path: {xf}")

    if not animated_transforms:
        print("  ❌ No animated transforms found!")
        return

    # Ask if should select animated only
    print("\n" + "="*70)
    print("RECOMMENDATION FOR EXPORT:")
    print("="*70)
    print(f"\nSelect ONLY the animated transforms ({len(animated_transforms)} nodes)")
    print("instead of the whole /rig group.")
    print("\nThis will:")
    print("  - Export ONLY animated data")
    print("  - Avoid including geometry/controls/etc")
    print("  - Create a clean animation cache")

    # Offer to select them
    result = cmds.confirmDialog(
        title="Select Animated Transforms?",
        message=f"Found {len(animated_transforms)} animated transform(s).\n\nSelect these for export?",
        button=["Yes, select them", "No, keep current"],
        defaultButton="Yes, select them",
        cancelButton="No, keep current"
    )

    if result == "Yes, select them":
        cmds.select(animated_transforms, replace=True, noExpand=True)
        print(f"\n✓ Selected {len(animated_transforms)} animated transforms")

    print("\n" + "="*70)
    print("Now publish with these selected transforms only!")
    print("="*70 + "\n")


if __name__ == "__main__":
    analyze_selection()
