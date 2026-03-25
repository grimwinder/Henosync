import json
import importlib.util
import logging
from pathlib import Path
from .registry import plugin_registry
from .interfaces import NodePlugin

logger = logging.getLogger(__name__)

REQUIRED_MANIFEST_FIELDS = [
    "id", "name", "version", "author",
    "description", "sdk_version", "node_types", "capabilities"
]


class PluginLoader:
    """
    Discovers and loads plugins from the plugins directory.
    Each plugin is a folder containing:
    - manifest.json
    - plugin.py (must contain a class inheriting NodePlugin)
    """

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir

    def load_all(self) -> int:
        """
        Scan the plugins directory and load all valid plugins.
        Returns the number of successfully loaded plugins.
        """
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory not found: {self.plugins_dir}")
            return 0

        loaded = 0
        for plugin_dir in self.plugins_dir.iterdir():
            if plugin_dir.is_dir():
                if self._load_plugin(plugin_dir):
                    loaded += 1

        logger.info(f"Loaded {loaded} plugins from {self.plugins_dir}")
        return loaded

    def _load_plugin(self, plugin_dir: Path) -> bool:
        """Load a single plugin from a directory."""
        manifest_path = plugin_dir / "manifest.json"
        plugin_path = plugin_dir / "plugin.py"

        if not manifest_path.exists():
            logger.warning(f"No manifest.json in {plugin_dir.name}")
            return False

        if not plugin_path.exists():
            logger.warning(f"No plugin.py in {plugin_dir.name}")
            return False

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid manifest.json in {plugin_dir.name}: {e}")
            return False

        if not self._validate_manifest(manifest, plugin_dir.name):
            return False

        try:
            spec = importlib.util.spec_from_file_location(
                f"henosync_plugin_{manifest['id']}",
                plugin_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Failed to load plugin.py in {plugin_dir.name}: {e}")
            return False

        plugin_class = self._find_plugin_class(module, plugin_dir.name)
        if plugin_class is None:
            return False

        plugin_registry.register(manifest["id"], plugin_class, manifest)
        return True

    def _validate_manifest(self, manifest: dict, name: str) -> bool:
        """Check all required fields are present in the manifest."""
        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                logger.error(
                    f"Plugin {name} manifest missing required field: {field}"
                )
                return False
        return True

    def _find_plugin_class(self, module, plugin_name: str):
        """Find the NodePlugin subclass in a loaded module."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, NodePlugin)
                and attr is not NodePlugin
            ):
                return attr

        logger.error(
            f"No NodePlugin subclass found in {plugin_name}/plugin.py"
        )
        return None