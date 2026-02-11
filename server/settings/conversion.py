from typing import Any


def _convert_product_base_types_0_6_0(overrides):
    publish_override = overrides.get("publish", {})
    if "ValidateAnimationProductTypePublish" in publish_override:
        publish_override["ValidateAnimationProductBaseTypePublish"] = (
            publish_override.pop("ValidateAnimationProductTypePublish")
        )

    validate_frame_range = publish_override.get("ValidateFrameRange", {})
    if "exclude_product_types" in validate_frame_range:
        validate_frame_range["exclude_product_base_types"] = (
            validate_frame_range.pop("exclude_product_types")
        )


def _convert_workfile_builder_0_6_0(overrides):
    profiles = overrides.get("workfile_builder", {}).get("profiles")
    if not profiles:
        return

    opts = []
    for profile in profiles:
        if "tasks" in profile:
            profile["task_names"] = profile.pop("tasks")

        if "linked_assets" in profile:
            profile["linked_folders"] = profile.pop("linked_assets")
        if "linked_folders" in profile:
            opts.append(profile["linked_folders"])
        if "current_context" in profile:
            opts.append(profile["current_context"])

    for opt in opts:
        if "product_base_types" not in opt and "product_types" in opt:
            opt["product_base_types"] = opt.pop("product_types")


def _convert_dirmap_0_4_3(overrides):
    """maya_dirmap key was renamed to dirmap in 0.4.3"""
    if "maya_dirmap" not in overrides:
        # Legacy settings not found
        return

    if "dirmap" in overrides:
        # Already new settings
        return

    overrides["dirmap"] = overrides.pop("maya_dirmap")


def _convert_scene_units(overrides):
    """Related scene units keys have been moved to
    have individual settings in 0.4.9"""
    if "scene_units" in overrides:
        # Already new settings
        return

    publish_settings = overrides.get("publish")
    if publish_settings is None:
        return

    maya_units_settings = publish_settings.get("ValidateMayaUnits")
    if maya_units_settings is None:
        return

    linear_units = maya_units_settings.pop("linear_units", None)
    angular_units = maya_units_settings.pop("angular_units", None)
    if linear_units is None and angular_units is None:
        # No old overrides
        return

    # Apply overrides to the new scene units settings if found in the old way
    overrides["scene_units"] = {}
    if linear_units is not None:
        overrides["scene_units"]["linear_units"] = linear_units
    if angular_units is not None:
        overrides["scene_units"]["angular_units"] = angular_units


def _convert_redshift_render_settings_gi_0_4_4(overrides):
    """The `render_settings.redshift_renderer` got a new `gi_enabled` key
     that was previously assumed enabled if either:
      - `primary_gi_engine` was not equal to "0" or
      - `secondary_gi_engine` was not equal to "0"
     """
    render_settings = overrides.get("render_settings")
    if render_settings is None:
        return

    redshift_settings = render_settings.get("redshift_renderer")
    if redshift_settings is None:
        return

    if "gi_enabled" in redshift_settings:
        # Already new settings
        return

    primary_gi_engine = redshift_settings.get("primary_gi_engine", "0")
    secondary_gi_engine = redshift_settings.get("secondary_gi_engine", "0")
    if primary_gi_engine != "0" or secondary_gi_engine != "0":
        redshift_settings["gi_enabled"] = True


def convert_settings_overrides(
    source_version: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    _convert_dirmap_0_4_3(overrides)
    _convert_redshift_render_settings_gi_0_4_4(overrides)
    _convert_scene_units(overrides)
    _convert_workfile_builder_0_6_0(overrides)
    _convert_product_base_types_0_6_0(overrides)
    return overrides
