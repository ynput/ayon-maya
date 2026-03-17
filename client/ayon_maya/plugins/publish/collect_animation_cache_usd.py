"""Collect animation cache USD instance data.

This collector enriches the animation cache USD instance with:
- Animation frame range and sampling settings
- Original asset prim path (auto-detected from containers)
- Department/layer information from task context
- Animated members from the instance
"""

import maya.cmds as cmds
import pyblish.api
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
            self.log.debug(
                f"Could not auto-detect asset prim path for {instance.name}. "
                "User should provide it manually if needed."
            )

        instance.data["originalAssetPrimPath"] = asset_prim_path

        # 3. Detect department from task context or use override
        department = self._detect_department(instance)
        instance.data["departmentLayer"] = department

        # 4. Prepare animation sampling settings
        sampling_mode = instance.data["creator_attributes"].get(
            "animationSampling", "sparse"
        )
        custom_step = instance.data["creator_attributes"].get(
            "customStepSize", 1.0
        )

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

        Strategy:
        1. Check loaded containers in scene for asset metadata
        2. Try UFE prim selection
        3. Fall back to manual input from creator attributes

        Returns:
            str: Detected prim path or empty string if not found
        """

        # Strategy 1: Check manual input first (user override)
        manual_input = instance.data["creator_attributes"].get(
            "originalAssetPrimPath", ""
        ).strip()
        if manual_input:
            self.log.debug(f"Using manual asset prim path: {manual_input}")
            return manual_input

        # Strategy 2: Try to find from loaded USD containers
        asset_prim_path = self._detect_from_containers()
        if asset_prim_path:
            self.log.debug(
                f"Auto-detected asset prim path from containers: "
                f"{asset_prim_path}"
            )
            return asset_prim_path

        # Strategy 3: Try UFE selection
        asset_prim_path = self._detect_from_ufe_selection()
        if asset_prim_path:
            self.log.debug(
                f"Auto-detected asset prim path from UFE selection: "
                f"{asset_prim_path}"
            )
            return asset_prim_path

        return ""

    def _detect_from_containers(self):
        """Detect asset prim path from USD containers in the scene.

        Looks for mayaUsdProxyShape nodes with container metadata.

        Returns:
            str: Detected prim path or empty string
        """
        try:
            # Find all mayaUsdProxyShape nodes
            proxy_shapes = cmds.ls(type="mayaUsdProxyShape", long=True) or []

            for proxy_shape in proxy_shapes:
                # Try to get stage and find containers
                try:
                    stage = cmds.mayaUsdProxyShapeStageOutlineHierarchy(
                        proxy_shape
                    )
                    if stage:
                        # Simple heuristic: return the first non-empty stage path
                        # This could be improved to match the actual animated asset
                        stage_path = str(stage)
                        if stage_path and stage_path != "/":
                            return stage_path
                except (RuntimeError, AttributeError):
                    continue

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

            # Get UFE USD selections
            for ufe_path in usdlib.iter_ufe_usd_selection():
                # Extract just the USD prim path part
                if "," in ufe_path:
                    node, prim_path = ufe_path.split(",", 1)
                    if prim_path:
                        return prim_path

        except Exception as e:
            self.log.debug(f"Error detecting from UFE selection: {e}")

        return ""

    def _detect_department(self, instance):
        """Detect department from task context or use override.

        Checks:
        1. Manual override in creator attributes
        2. Current task context from project settings

        Returns:
            str: Department name (animation, layout, cfx, fx, or auto-detected)
        """

        # Check for manual override
        department = instance.data["creator_attributes"].get(
            "department", "auto"
        )

        if department != "auto":
            return department

        # Try to auto-detect from task context
        try:
            create_context = instance.data.get("_create_context")
            if not create_context:
                return "auto"

            task_entity = create_context.get_current_task_entity()
            if not task_entity:
                return "auto"

            task_name = task_entity.get("name", "").lower()

            # Map task names to departments
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
                        f"Auto-detected department: {dept} from task: {task_name}"
                    )
                    return dept

        except Exception as e:
            self.log.debug(f"Error auto-detecting department: {e}")

        return "auto"
