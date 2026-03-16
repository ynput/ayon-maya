# USD Add Reference Loader - User Guide

## Overview

The **USD Add Reference Loader** is a powerful tool for importing USD assets into your Maya USD Proxy stages. It allows you to organize imported assets in different hierarchies and place them relative to selected prims.

## Quick Start

1. **Right-click** on a USD asset in the AYON Asset Manager
2. Select **USD Add Reference**
3. Choose your **Prim Path Mode** from the dialog
4. Click **Load**

## Prim Path Modes

### 1. Folder Path *(default)*
Imports using the full folder structure from AYON.

**Example:** If your asset is at `/assets/character/cone_character/usd`

```
Result: /assets/character/cone_character
```

**Use case:** When you want to preserve your full organizational structure in USD.

---

### 2. Flat
Imports using only the asset name, no hierarchy.

**Example:** If your asset is `cone_character`

```
Result: /cone_character
```

**Use case:** Quick imports when you don't need organizational structure.

---

### 3. By Folder Type
Creates a hierarchy based on the content type extracted from the folder path.

**Example:** Asset at `/assets/character/cone_character` extracts `character`

```
Result: /character/cone_character
```

**Folder type examples:**
- `/assets/character/hero` → `/character/hero`
- `/assets/environment/forest` → `/environment/forest`
- `/assets/props/sword` → `/props/sword`

**Use case:** Organizing assets by their type (character, environment, props, etc).

---

### 4. Folder+Product
Combines folder path with product (subset) name.

**Example:** Asset `cone_character` with product `usdMain`

```
Result: /assets/character/cone_character/usdMain
```

**Use case:** When you need to include the product/version information in the hierarchy.

---

### 5. Custom
Define your own path with powerful variable support.

See the **Custom Paths** section below for details.

## Selection Behavior

### No Selection
Assets are imported at the root of the stage (or in `/` paths).

```
Flat mode → /cone_character
By Type   → /character/cone_character
```

### USD Prim Selected
Assets are imported as children of the selected prim.

```
Selected: /assets
Flat mode → /assets/cone_character
```

```
Selected: /props
By Type   → /props/character/cone_character
```

## Custom Paths

Custom paths give you complete control over asset placement using variables.

### Available Variables

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `{name}` | `cone_character` | The asset/folder name |
| `{folder_name}` | `cone_character` | Folder name |
| `{folder_path}` | `/assets/character/cone_character` | Full folder path |
| `{folder_type}` | `character` | Content type from path |
| `{product_name}` | `usdMain` | Product/variant name |
| `{parent_folder}` | `character` | Parent folder name |

### Absolute vs Relative Paths

**Absolute paths** (starting with `/`) ignore the selected prim:

```
Path: /props/{name}
Selected prim: /assets
Result: /props/cone_character  ← ignores /assets selection
```

**Relative paths** (not starting with `/`) append to the selected prim:

```
Path: props/{name}
Selected prim: /assets
Result: /assets/props/cone_character  ← uses /assets
```

### Custom Path Examples

#### Animation Setup
Place animated assets in a separate hierarchy:

```
Path: /anim/{folder_type}/{name}
Result: /anim/character/hero
```

#### Props Organization
Organize props by type under a common container:

```
Path: props/{folder_type}_{name}
Result: /props/sword_medieval
```

#### Single Folder Placement
Put everything in a specific folder:

```
Path: /environment/{name}
Selected: /root
Result: /environment/forest_01  ← always at /environment
```

#### Relative to Selection
Use the selected prim as a container:

```
Path: {name}
Selected: /assets
Result: /assets/cone_character
```

## Common Workflows

### 1. Building a Scene with Multiple Asset Types

1. Create prim containers for organization:
   - Select stage → Create `/characters` prim
   - Select stage → Create `/environments` prim
   - Select stage → Create `/props` prim

2. Load assets:
   - **Characters:** Select `/characters` → Load with Flat mode
   - **Environments:** Select `/environments` → Load with Flat mode
   - **Props:** Select `/props` → Load with Flat mode

Result: Organized hierarchy without duplicated folder paths.

### 2. Animation Export Structure

1. Load base character with `Folder Path` mode
2. Create animation prim: `/animations`
3. Load animation using Custom path: `animations/{name}`

Result: Clean separation between model and animation data.

### 3. Environment with Multiple Props

1. Load environment using `By Folder Type` → `/environment/forest`
2. Load props inside environment:
   - Select `/environment/forest` prim
   - Use Custom path: `props/{name}`
   - Load props (will create `/environment/forest/props/sword`, etc)

Result: Props organized within environment hierarchy.

## Troubleshooting

### Asset imports to wrong location
- Check if a prim is accidentally selected in the outliner
- Use Custom path with `/` prefix to force absolute placement

### Variables not expanding
- Check for typos in variable names (they're case-sensitive)
- Make sure variable syntax is exactly `{variable_name}`

### Duplicate paths (e.g., `/assets/assets/...`)
- This happens with relative paths when folder already contains the type
- Use absolute paths with `/` prefix to control exact placement
- Or use simpler variables like `{name}`

## Tips & Tricks

✨ **Pro Tips**

- Use **By Folder Type** for automatic organization by asset category
- Use **Custom** with variables for complex setups
- Start with a prim selection for relative placement
- Use Custom absolute paths (`/folder/`) to override selection

🔄 **Consistency**

- All paths are automatically cleaned up (invalid characters replaced with `_`)
- Path separators are consistent (forward slashes)
- Leading/trailing spaces in custom paths are automatically trimmed

📝 **File Organization**

- Prim names follow USD naming conventions (alphanumeric + underscore)
- Special characters in asset names are sanitized automatically
- Folder structure from AYON is preserved in path names

