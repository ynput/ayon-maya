# USD Add Reference Loader - Developer Guide

## Architecture Overview

The loader is implemented in `load_maya_usd_add_reference.py` and handles USD reference importing with flexible prim path generation.

### Key Components

1. **Prim Path Builders** - Functions that generate USD paths based on context
2. **Path Mode Resolution** - Logic to resolve user selections to builder functions
3. **Custom Path Expansion** - Variable substitution for dynamic paths
4. **Stage Resolution** - Finding or creating USD stages
5. **Prim Hierarchy Creation** - Building missing prim ancestors

## Data Flow

```
User Input (Prim Path Mode + Custom Path)
    ↓
_lookup_mode() → Get builder function
    ↓
_resolve_prim_path() → Generate prim path
    ├─ For custom: expand variables via _expand_custom_path()
    └─ For other modes: call builder function
    ↓
Selection Check (UFE prim selected?)
    ├─ Absolute custom paths: use as-is
    ├─ Relative custom paths: prepend selected prim path
    └─ Other modes: prepend selected prim path
    ↓
_define_prim_hierarchy() → Create prims in stage
    ↓
Add reference to final prim
    ↓
Containerise and return
```

## Prim Path Builders

### Structure

Each builder function:
- Takes `context` dict from AYON load context
- Returns a path string (always starting with `/`)
- Sanitizes path components using `_sanitize()`

### Available Builders

```python
_prim_path_folder(context)      # /assets/character/cone_character
_prim_path_flat(context)        # /cone_character
_prim_path_by_type(context)     # /character/cone_character
_prim_path_folder_product(context)  # /assets/character/cone_character/usdMain
```

### Adding a New Builder

1. Create the builder function:

```python
def _prim_path_custom_rule(context):
    """Your description here."""
    folder = context.get("folder", {})
    name = folder.get("name", context.get("asset", "asset"))
    # Your logic here
    return "/your/path/{}".format(_sanitize(name))
```

2. Add to `_PRIM_PATH_BUILDERS`:

```python
_PRIM_PATH_BUILDERS = [
    ("Folder Path",    "folder_path",    _prim_path_folder),
    ("Your Mode",      "your_key",       _prim_path_custom_rule),
    # ... others
]
```

3. It will automatically appear in the UI dropdown.

## Custom Path Variables

### Implementation

Variables are expanded in `_expand_custom_path()`:

```python
variables = {
    "name": folder.get("name", context.get("asset", "asset")),
    "folder_name": folder.get("name", ""),
    "folder_path": folder.get("path", ""),
    "folder_type": folder_type,  # extracted from path
    "product_name": product.get("name", context.get("subset", "")),
    "parent_folder": parent_folder,
}

expanded = custom_path
for var_name, var_value in variables.items():
    expanded = expanded.replace("{" + var_name + "}", str(var_value))
```

### Adding a New Variable

1. Extract/calculate the value:

```python
my_value = context.get("some", {}).get("field", "default")
```

2. Add to `variables` dict:

```python
variables = {
    # ... existing
    "my_var": my_value,
}
```

3. Update documentation with the new variable.

## Context Dictionary Structure

The `context` parameter is the AYON load context:

```python
context = {
    "folder": {
        "name": "cone_character",
        "path": "/assets/character/cone_character",
        "folderType": "Asset",  # AYON type, not content type
        "id": "...",
        "parentId": "...",
        # other fields...
    },
    "product": {
        "name": "usdMain",
        "type": "usd",
        # other fields...
    },
    "asset": "cone_character",  # fallback if folder.name missing
    "subset": "usdMain",  # fallback if product.name missing
    "representation": {...},
    # other fields...
}
```

## Selection Resolution

### Priority Order

1. **UFE USD prim selected** → Get stage from prim, use as base
2. **mayaUsdProxyShape selected** → Get stage from shape
3. **No selection** → Find any proxy in scene
4. **No proxy** → Create new stage

### Prim Path Concatenation

```python
if base_prim is selected:
    if custom_mode and absolute_path:
        final_path = resolved_path  # /props/asset
    else:
        final_path = base_prim_path + resolved_path  # /base + /asset
```

### Absolute vs Relative Custom Paths

Determined from **original input** before variable expansion:

```python
custom_path_strip = (custom_path or "").strip()
is_absolute_custom = custom_path_strip.startswith("/")
```

**Why before expansion?** To avoid changing semantics due to variables that might start with `/`.

## USD Stage Handling

### Stage Resolution

```python
_get_selected_proxy_shape()      # From selection
_find_any_proxy_stage()          # Existing in scene
_create_new_proxy_stage()        # New stage creation
_get_stage_from_proxy_shape()    # Extract stage from shape
```

### Stage Modification

- Gets or creates layer via `stage.GetRootLayer()`
- Sets `defaultPrim` if not already set
- Creates prims with `UsdGeom.Xform.Define()`

## Prim Hierarchy Creation

### `_define_prim_hierarchy(stage, prim_path)`

```python
# Splits path and creates all ancestors
parts = prim_path.strip("/").split("/")
for part in parts:
    # Creates Xform prim at each level
    UsdGeom.Xform.Define(stage, current_path)
```

**Important:**
- Validates path is valid USD naming
- Ensures all ancestors exist before target
- Returns the final prim object
- Raises RuntimeError if creation fails

## Reference Addition

```python
references = prim.GetReferences()
reference = Sdf.Reference(
    assetPath=path,
    customData={self.identifier_key: identifier}
)
success = references.AddReference(reference)
```

**Custom Data:**
- Stores unique identifier for update/remove operations
- Format: `{prim_path}:{uuid}`
- Used to track which reference belongs to which container

## Testing Considerations

### Unit Tests Should Cover

- Each prim path builder with various context states
- Custom path variable expansion with edge cases
- Mode lookup with different input formats
- Selection resolution (prim, proxy, no selection)
- Absolute vs relative custom path handling
- Prim hierarchy creation with deep paths
- Reference addition and containerization

### Integration Tests Should Cover

- Full load workflow with different prim path modes
- Custom paths with all variable types
- Selection scenarios (prim, proxy, none)
- Multiple references on same prim
- Update and remove operations

### Manual Testing Checklist

- [ ] Flat mode with/without prim selection
- [ ] By Type with different folder structures
- [ ] Custom absolute and relative paths
- [ ] Variable expansion in custom paths
- [ ] Large path hierarchies (5+ levels)
- [ ] Special characters in asset names
- [ ] Reference updates preserve customData

## Performance Notes

### Path Lookup
- Uses dict lookups for mode resolution: O(1)
- Minimal string operations

### Stage Operations
- Reuses existing prims when possible
- Single pass for hierarchy creation
- No redundant stage modifications

### Custom Path Expansion
- Simple string.replace() for each variable
- Only happens for custom mode
- Variables are extracted once, not repeatedly

## Common Pitfalls & Solutions

### Issue: Relative custom paths not concatenating

**Cause:** Path had leading `/` after variable expansion

**Solution:** Check original path before expansion (already implemented)

### Issue: Wrong prim selected in UFE

**Cause:** User selected wrong prim before loading

**Solution:** Clear selection or use absolute custom paths

### Issue: Stage not found

**Cause:** Multiple proxy shapes in scene

**Solution:** Select specific proxy or use custom mode

### Issue: Invalid prim names

**Cause:** Special characters in folder/asset names

**Solution:** `_sanitize()` automatically replaces invalid chars

## Debugging

To add debug logging:

1. Modify `_lookup_mode()` to log mode resolution
2. Modify `_expand_custom_path()` to log variable expansion
3. Modify `load()` to log final path resolution

**Don't commit debug prints** - use the help text and error messages for user feedback.

## Related Files

- `ayon_maya/api/usdlib.py` - USD utility functions
- `ayon_maya/api/pipeline.py` - Container functions
- `/plugins/create/create_maya_usd.py` - USD creation counterpart

## References

- [USD Documentation](https://graphics.pixar.com/usd/release/index.html)
- [MayaUSD Documentation](https://github.com/Autodesk/maya-usd)
- [AYON Loader Plugin](https://github.com/ayon-fork/ayon-core)

