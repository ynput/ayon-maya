"""Collect animation cache USD instance data.

This collector enriches the animation cache USD instance with:
- Animation frame range and sampling settings
- Original asset prim path (auto-detected from containers)
- Department/layer information from task context
- Animated members from the instance
"""

import maya.cmds as cmds
import pyblish.api
from ayon_core.pipeline.constants import AVALON_CONTAINER_ID
from ayon_maya.api import plugin


class CollectAnimationCacheUsd(plugin.MayaInstancePlugin):
    """Collect animation cache USD instance data.

    Prepares instance data for animation cache USD publishing by:
    1. Validating animated members exist
    2. Detecting original asset prim path from loaded containers
    3. Setting up animation frame range and sampling
    4. Determining department from task context
    """

    order = pyblish.api.CollectorOrder + 0.5
    families = ["animationCacheUsd"]
    label = "Collect Animation Cache USD"

    def process(self, instance):
        """Collect and prepare animation cache USD instance data."""

        # 1. Validate animated members exist
        set_members = instance.data.get("setMembers", [])
        if not set_members:
            self.log.warning(
                f"Instance {instance.name} has no members selected. "
                "Please select the animated nodes."
            )

        # 2. Detect original asset prim path via smart detection
        #    Try: container metadata → UFE selection → manual input
        asset_prim_path = self._detect_asset_prim_path(instance)
        if not asset_prim_path:
            self.log.warning(
                f"Could not auto-detect asset prim path for {instance.name}. "
                "The contribution layer may not be placed correctly. "
                "Set 'Original Asset Prim Path' manually if auto-detection "
                "fails."
            )

        instance.data["originalAssetPrimPath"] = asset_prim_path

        # 3. Detect department from task context or use override
        department = self._detect_department(instance)
        instance.data["departmentLayer"] = department

        # 4. Prepare animation sampling settings
        creator_attrs = instance.data.get("creator_attributes", {})
        sampling_mode = creator_attrs.get("animationSampling", "sparse")
        custom_step = creator_attrs.get("customStepSize", 1.0)

        instance.data["samplingMode"] = sampling_mode
        instance.data["customStepSize"] = custom_step

        # 5. Log collected information
        self.log.info(
            f"Collected animation cache USD: "
            f"prim_path={asset_prim_path}, "
            f"department={department}, "
            f"sampling={sampling_mode}"
        )

    def _detect_asset_prim_path(self, instance):
        """Detect original asset prim path via smart detection.

        Strategy order:
        1. Manual input from creator attributes (user override)
        2. Match setMembers namespaces against USD container prims
        3. UFE prim selection fallback

        Returns:
            str: Detected prim path or empty string if not found
        """

        creator_attrs = instance.data.get("creator_attributes", {})

        # Strategy 1: Check manual input first (user override)
        manual_input = creator_attrs.get(
            "originalAssetPrimPath", ""
        ).strip()
        if manual_input:
            self.log.debug(f"Using manual asset prim path: {manual_input}")
            return manual_input

        # Strategy 2: Match containers by namespace of animated members
        set_members = instance.data.get("setMembers", [])
        asset_prim_path = self._detect_from_containers(set_members)
        if asset_prim_path:
            self.log.info(
                f"Auto-detected asset prim path from containers: "
                f"{asset_prim_path}"
            )
            return asset_prim_path

        # Strategy 3: Try UFE selection
        asset_prim_path = self._detect_from_ufe_selection()
        if asset_prim_path:
            self.log.info(
                f"Auto-detected asset prim path from UFE selection: "
                f"{asset_prim_path}"
            )
            return asset_prim_path

        return ""

    def _extract_namespaces(self, members):
        """Extract unique Maya namespaces from member node names.

        When 'Edit as Maya Data' loads a .mb, nodes are created under
        a namespace (e.g., 'myNamespace:pCube1'). We extract these to
        match against container metadata.

        Args:
            members: List of Maya DAG node paths

        Returns:
            set: Unique namespaces found in member names
        """
        namespaces = set()
        for member in members:
            # Get the short name (last component of long path)
            short_name = member.rsplit("|", 1)[-1]
            if ":" in short_name:
                ns = short_name.rsplit(":", 1)[0]
                # Handle nested namespaces - get the root namespace
                root_ns = ns.split(":")[0]
                namespaces.add(root_ns)
                namespaces.add(ns)
        return namespaces

    def _detect_from_containers(self, set_members):
        """Detect asset prim path from USD containers in the scene.

        Uses the proper mayaUsd Python API to get stages from proxy shapes,
        then traverses all prims looking for ones with Ayon container
        metadata (ayon:id custom data).

        When multiple containers are found, matches against the
        setMembers' Maya namespaces to find the correct asset.

        Args:
            set_members: List of Maya DAG node paths (animated members)

        Returns:
            str: Detected prim path or empty string
        """
        try:
            import mayaUsd

            # Extract namespaces from selected members for matching
            member_namespaces = self._extract_namespaces(set_members)

            # Find all mayaUsdProxyShape nodes
            proxy_shapes = (
                cmds.ls(type="mayaUsdProxyShape", long=True) or []
            )

            all_containers = []

            for proxy_shape in proxy_shapes:
                try:
                    stage = mayaUsd.ufe.getStage(proxy_shape)
                    if not stage:
                        continue

                    # Traverse all prims looking for containers
                    for prim in stage.Traverse():
                        container_id = prim.GetCustomDataByKey("ayon:id")
                        if container_id == AVALON_CONTAINER_ID:
                            prim_path = str(prim.GetPath())
                            container_ns = (
                                prim.GetCustomDataByKey("ayon:namespace") or ""
                            )
                            container_name = (
                                prim.GetCustomDataByKey("ayon:name") or ""
                            )
                            all_containers.append({
                                "prim_path": prim_path,
                                "namespace": container_ns,
                                "name": container_name,
                            })
                except (RuntimeError, AttributeError) as e:
                    self.log.debug(
                        f"Could not get stage from {proxy_shape}: {e}"
                    )
                    continue

            if not all_containers:
                self.log.debug("No USD containers found in scene")
                return ""

            # If only one container, use it directly
            if len(all_containers) == 1:
                prim_path = all_containers[0]["prim_path"]
                self.log.debug(
                    f"Single container found: {prim_path}"
                )
                return prim_path

            # Multiple containers: try to match by namespace
            if member_namespaces:
                for container in all_containers:
                    container_ns = container["namespace"]
                    container_name = container["name"]
                    # Check if any member namespace matches the container
                    if container_ns and container_ns in member_namespaces:
                        self.log.debug(
                            f"Matched container by namespace "
                            f"'{container_ns}': {container['prim_path']}"
                        )
                        return container["prim_path"]
                    if container_name and container_name in member_namespaces:
                        self.log.debug(
                            f"Matched container by name "
                            f"'{container_name}': {container['prim_path']}"
                        )
                        return container["prim_path"]

            # Fallback: return the first container found
            prim_path = all_containers[0]["prim_path"]
            self.log.debug(
                f"Multiple containers found, using first: {prim_path}"
            )
            return prim_path

        except ImportError:
            self.log.debug(
                "mayaUsd module not available, cannot detect containers"
            )
        except Exception as e:
            self.log.debug(f"Error detecting from containers: {e}")

        return ""

    def _detect_from_ufe_selection(self):
        """Detect asset prim path from UFE USD prim selection.

        Returns:
            str: Detected prim path or empty string
        """
        try:
            from ayon_maya.api import usdlib

            for ufe_path in usdlib.iter_ufe_usd_selection():
                if "," in ufe_path:
                    _node, prim_path = ufe_path.split(",", 1)
                    if prim_path:
                        return prim_path

        except Exception as e:
            self.log.debug(f"Error detecting from UFE selection: {e}")

        return ""

    def _detect_department(self, instance):
        """Detect department from task context or use override.

        Returns:
            str: Department name (animation, layout, cfx, fx, or auto)
        """

        creator_attrs = instance.data.get("creator_attributes", {})
        department = creator_attrs.get("department", "auto")

        if department != "auto":
            return department

        # Try to auto-detect from task context
        try:
            task_entity = instance.data.get("taskEntity")
            if not task_entity:
                return "auto"

            task_name = task_entity.get("name", "").lower()

            dept_mapping = {
                "anim": "animation",
                "animation": "animation",
                "layout": "layout",
                "cfx": "cfx",
                "fx": "fx",
            }

            for key, dept in dept_mapping.items():
                if key in task_name:
                    self.log.debug(
                        f"Auto-detected department: {dept} "
                        f"from task: {task_name}"
                    )
                    return dept

        except Exception as e:
            self.log.debug(f"Error auto-detecting department: {e}")

        return "auto"
