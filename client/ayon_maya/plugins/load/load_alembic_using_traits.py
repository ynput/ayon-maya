"""Alembic loader using traits."""
from __future__ import annotations
from ayon_core.pipeline import LoaderPlugin
from ayon_maya.api.plugin import MayaLoader


class AlembicTraitLoader(MayaLoader):
    """Alembic loader using traits."""
    label = "Alembic Trait Loader"

    @staticmethod
    def is_compatible_loader(context):
        print("-" * 80)
        print(context)
        return True

    def load(self, context, name=None, namespace=None, options=None):
        print(context, name, namespace, options)
        return None