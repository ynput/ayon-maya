"""Load references of the current scene in a calculated, safe order.

References are loaded one by one, with references another reference depends
on (e.g. is parented under) loaded first, and otherwise the lightest
references loaded first.
"""
import os
import logging

from maya import cmds

log = logging.getLogger(__name__)


def get_reference_info():
    """Gather info about all top-level references in the scene.

    Returns:
        dict[str, dict]: Reference data per reference node.
    """
    refs = cmds.file(query=True, reference=True) or []
    info = {}

    for ref_path in refs:
        try:
            ref_node = cmds.referenceQuery(ref_path, referenceNode=True)
            namespace = cmds.referenceQuery(ref_path, namespace=True)
            is_loaded = cmds.referenceQuery(ref_node, isLoaded=True)
        except RuntimeError as exc:
            log.warning("Failed to query %s: %s", ref_path, exc)
            continue

        # Rough complexity estimate
        nodes = cmds.ls(namespace + ":*", long=True) or []
        node_count = len(nodes)

        poly_count = 0
        shapes = cmds.ls(namespace + ":*", type="mesh", long=True) or []
        for shape in shapes[:50]:  # limit for speed
            try:
                poly_count += cmds.polyEvaluate(shape, face=True) or 0
            except (RuntimeError, TypeError):
                pass

        weight = node_count + (poly_count / 1000.0)
        if not is_loaded:
            # Unloaded references have no nodes in the scene, so fall back
            # to the file size on disk (in MB) as a complexity estimate.
            filepath = cmds.referenceQuery(
                ref_node, filename=True, withoutCopyNumber=True)
            if os.path.exists(filepath):
                weight = os.path.getsize(filepath) / (1024.0 * 1024.0)

        info[ref_node] = {
            "path": ref_path,
            "namespace": namespace,
            "loaded": is_loaded,
            "weight": weight,
            "node_count": node_count,
            "deps": set()
        }

    return info


def detect_dependencies(info):
    """Detect simple cross-reference dependencies (mainly parenting).

    Only detectable for references whose nodes exist in the scene.
    """
    for ref_node, data in info.items():
        namespace = data["namespace"]
        # Look for nodes in this namespace parented to another reference
        nodes = cmds.ls(namespace + ":*", long=True, type="transform") or []
        for node in nodes[:200]:  # limit for performance
            parent = cmds.listRelatives(node, parent=True, fullPath=True)
            if not parent:
                continue
            parent_name = parent[0].rsplit("|", 1)[-1]
            for other_ref, other_data in info.items():
                if other_ref == ref_node:
                    continue
                if parent_name.startswith(other_data["namespace"] + ":"):
                    data["deps"].add(other_ref)
                    break


def get_load_order(info):
    """Topological sort by dependencies, lightest references first.

    Returns:
        list[str]: Reference nodes in the order they should be loaded.
    """
    ordered = []
    visited = set()
    visiting = set()

    def visit(node):
        if node in visited or node in visiting:
            return  # already handled or cycle
        visiting.add(node)
        deps = [dep for dep in info[node]["deps"] if dep in info]
        for dep in sorted(deps, key=lambda n: info[n]["weight"]):
            visit(dep)
        visiting.remove(node)
        visited.add(node)
        ordered.append(node)

    for node in sorted(info, key=lambda n: info[n]["weight"]):
        visit(node)

    return ordered


def load_references_safely():
    """Load all unloaded references in a dependency and weight based order.
    """
    log.info("Analyzing references...")
    info = get_reference_info()
    if not info:
        log.info("No references found.")
        return

    log.info("Found %d references", len(info))
    detect_dependencies(info)

    for data in sorted(info.values(), key=lambda d: d["weight"]):
        log.debug(
            "%-30s | weight: %8.1f | deps: %d | loaded: %s",
            data["namespace"], data["weight"],
            len(data["deps"]), data["loaded"]
        )

    for ref_node in get_load_order(info):
        data = info[ref_node]
        if data["loaded"]:
            continue
        log.info(
            "Loading reference: %s (weight: %.1f)",
            data["namespace"], data["weight"]
        )
        try:
            cmds.file(loadReference=ref_node)
        except RuntimeError as exc:
            log.error("Failed to load %s: %s", data["namespace"], exc)

    log.info("Finished loading references.")


def open_file_with_safe_reference_loading(filepath):
    """Open a scene without loading references, then load them safely."""
    cmds.file(filepath, open=True, force=True, loadReferenceDepth="none")
    load_references_safely()
