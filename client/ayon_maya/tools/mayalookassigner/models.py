from collections import defaultdict

from qtpy import QtCore
import qtawesome

from ayon_core.lib import Logger
from ayon_core.style import get_default_entity_icon_color

log = Logger.get_logger(__name__)


class TreeModel(QtCore.QAbstractItemModel):
    Columns = list()
    ItemRole = QtCore.Qt.UserRole + 1
    item_class = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_item = self.ItemClass()

    @property
    def ItemClass(self):
        if self.item_class is not None:
            return self.item_class
        return Item

    def rowCount(self, parent=None):
        if parent is None or not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.childCount()

    def columnCount(self, parent):
        return len(self.Columns)

    def data(self, index, role):
        if not index.isValid():
            return None

        if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
            item = index.internalPointer()
            column = index.column()

            key = self.Columns[column]
            return item.get(key, None)

        if role == self.ItemRole:
            return index.internalPointer()

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        """Change the data on the items.

        Returns:
            bool: Whether the edit was successful
        """

        if index.isValid():
            if role == QtCore.Qt.EditRole:

                item = index.internalPointer()
                column = index.column()
                key = self.Columns[column]
                item[key] = value

                self.dataChanged.emit(index, index, [role])

                # must return true if successful
                return True

        return False

    def setColumns(self, keys):
        assert isinstance(keys, (list, tuple))
        self.Columns = keys

    def headerData(self, section, orientation, role):

        if role == QtCore.Qt.DisplayRole:
            if section < len(self.Columns):
                return self.Columns[section]

        super().headerData(section, orientation, role)

    def flags(self, index):
        flags = QtCore.Qt.ItemIsEnabled

        item = index.internalPointer()
        if item.get("enabled", True):
            flags |= QtCore.Qt.ItemIsSelectable

        return flags

    def parent(self, index):

        item = index.internalPointer()
        parent_item = item.parent()

        # If it has no parents we return invalid
        if parent_item == self._root_item or not parent_item:
            return QtCore.QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def index(self, row, column, parent=None):
        """Return index for row/column under parent"""

        if parent is None or not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QtCore.QModelIndex()

    def add_child(self, item, parent=None):
        if parent is None:
            parent = self._root_item

        parent.add_child(item)

    def column_name(self, column):
        """Return column key by index"""

        if column < len(self.Columns):
            return self.Columns[column]

    def clear(self):
        self.beginResetModel()
        self._root_item = self.ItemClass()
        self.endResetModel()


class Item(dict):
    """An item that can be represented in a tree view using `TreeModel`.

    The item can store data just like a regular dictionary.

    >>> data = {"name": "John", "score": 10}
    >>> item = Item(data)
    >>> assert item["name"] == "John"

    """

    def __init__(self, data=None):
        super(Item, self).__init__()

        self._children = list()
        self._parent = None

        if data is not None:
            assert isinstance(data, dict)
            self.update(data)

    def childCount(self):
        return len(self._children)

    def child(self, row):

        if row >= len(self._children):
            log.warning("Invalid row as child: {0}".format(row))
            return None

        return self._children[row]

    def children(self):
        return self._children

    def parent(self):
        return self._parent

    def row(self):
        """
        Returns:
             int: Index of this item under parent"""
        if self._parent is not None:
            siblings = self.parent().children()
            return siblings.index(self)
        return -1

    def add_child(self, child):
        """Add a child to this item"""
        child._parent = self
        self._children.append(child)


class AssetModel(TreeModel):

    Columns = ["label"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._icon_color = get_default_entity_icon_color()

    def add_items(self, items):
        """
        Add items to model with needed data
        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Add the items sorted by label
        def sorter(x):
            return x["label"]

        for item in sorted(items, key=sorter):

            asset_item = Item()
            asset_item.update(item)
            asset_item["icon"] = "folder"

            # Add namespace children
            namespaces = item["namespaces"]
            for namespace in sorted(namespaces):
                child = Item()
                child.update(item)
                child.update({
                    "label": (namespace if namespace != ":"
                              else "(no namespace)"),
                    "namespace": namespace,
                    "looks": item["looks"],
                    "icon": "folder-o"
                })
                asset_item.add_child(child)

            self.add_child(asset_item)

        self.endResetModel()

    def data(self, index, role):
        if not index.isValid():
            return

        if role == TreeModel.ItemRole:
            node = index.internalPointer()
            return node

        # Add icon
        if role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                node = index.internalPointer()
                icon = node.get("icon")
                if icon:
                    return qtawesome.icon(
                        "fa.{0}".format(icon),
                        color=self._icon_color
                    )

        return super().data(index, role)


class LookModel(TreeModel):
    """Model displaying a list of looks and matches for assets"""

    Columns = ["label", "match"]

    def add_items(self, items):
        """Add items to model with needed data

        An item exists of:
            {
                "product": 'name of product',
                "asset": asset_document
            }

        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Collect the assets per look name (from the items of the AssetModel)
        look_products = defaultdict(list)
        for asset_item in items:
            folder_entity = asset_item["folder_entity"]
            for look in asset_item["looks"]:
                look_products[look["name"]].append(folder_entity)

        for product_name in sorted(look_products.keys()):
            folder_entities = look_products[product_name]

            # Define nice label without "look" prefix for readability
            label = (
                product_name
                if not product_name.startswith("look")
                else product_name[4:]
            )

            item_node = Item()
            item_node["label"] = label
            item_node["product"] = product_name

            # Amount of matching assets for this look
            item_node["match"] = len(folder_entities)

            # Store the assets that have this product available
            item_node["folder_entities"] = folder_entities

            self.add_child(item_node)

        self.endResetModel()
