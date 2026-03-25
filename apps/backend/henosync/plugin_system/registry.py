from typing import Optional
from .interfaces import NodePlugin
import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Keeps track of all loaded plugins.
    Acts as the single source of truth for what plugins
    are available and which plugin handles which node.
    """

    def __init__(self):
        # plugin_id -> plugin class
        self._plugins: dict[str, type[NodePlugin]] = {}
        # plugin_id -> manifest dict
        self._manifests: dict[str, dict] = {}
        # node_id -> plugin instance
        self._node_instances: dict[str, NodePlugin] = {}

    def register(
        self,
        plugin_id: str,
        plugin_class: type[NodePlugin],
        manifest: dict
    ) -> None:
        """Register a plugin class with its manifest."""
        self._plugins[plugin_id] = plugin_class
        self._manifests[plugin_id] = manifest
        logger.info(f"Registered plugin: {plugin_id}")

    def get_plugin_class(
        self,
        plugin_id: str
    ) -> Optional[type[NodePlugin]]:
        """Get the plugin class for a given plugin id."""
        return self._plugins.get(plugin_id)

    def get_manifest(self, plugin_id: str) -> Optional[dict]:
        """Get the manifest for a given plugin id."""
        return self._manifests.get(plugin_id)

    def get_instance(self, node_id: str) -> Optional[NodePlugin]:
        """Get the plugin instance handling a specific node."""
        return self._node_instances.get(node_id)

    def register_instance(
        self,
        node_id: str,
        instance: NodePlugin
    ) -> None:
        """Associate a plugin instance with a node id."""
        self._node_instances[node_id] = instance

    def remove_instance(self, node_id: str) -> None:
        """Remove the plugin instance for a node."""
        self._node_instances.pop(node_id, None)

    def list_plugins(self) -> list[dict]:
        """Return a list of all registered plugin manifests."""
        return list(self._manifests.values())

    def is_registered(self, plugin_id: str) -> bool:
        """Check if a plugin id is registered."""
        return plugin_id in self._plugins


# Global singleton instance
plugin_registry = PluginRegistry()