from typing import Any


def _convert_dirmap_0_4_3(overrides):
    """maya_dirmap key was renamed to dirmap in 0.4.3"""
    if "maya_dirmap" not in overrides:
        # Legacy settings not found
        return

    if "dirmap" in overrides:
        # Already new settings
        return

    overrides["dirmap"] = overrides.pop("maya_dirmap")


def _convert_scene_unit(overrides):
    """Related unit scale keys have been moved to
    have individual settings in 0.4.9"""
    if "unit_scale" in overrides:
        # Already new settings
        return

    publish_settings = overrides.get("publish")
    if publish_settings is None:
        return

    maya_units_settings = publish_settings.get("ValidateMayaUnits")
    if maya_units_settings is None:
        return
    
    linear_settings = maya_units_settings.pop("linear_units", None)
    angular_settings = maya_units_settings.pop("angular_units", None)
    if linear_settings is None and angular_settings is None:
        # No old overrides
        return

    # Apply overrides to the new unit scale settings if found in the old way
    overrides["unit_scale"] = unit_scale = {}
    if linear_settings is not None:
        unit_scale["linear_units"] = linear_settings
    if angular_settings is not None:
        unit_scale["linear_units"] = angular_settings


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
    _convert_scene_unit(overrides)
    _convert_redshift_render_settings_gi_0_4_4(overrides)
    return overrides
