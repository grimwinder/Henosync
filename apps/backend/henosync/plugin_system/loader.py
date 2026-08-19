import importlib.util
import json
import logging
from pathlib import Path

from .interfaces import NodePlugin
from .registry import plugin_registry

logger = logging.getLogger(__name__)

REQUIRED_MANIFEST_FIELDS = [
    "id", "name", "version", "author",
    "description", "sdk_version", "node_types", "capabilities"
]

# Standard command IDs declared in manifests → the NodePlugin method that must handle them.
# If a plugin declares one of these capability IDs but doesn't override the method,
# a warning is logged at load time so the problem surfaces before runtime.
STANDARD_COMMAND_MAP = {
    "move_to": "cmd_move_to",
    "stop": "cmd_stop",
    "return_home": "cmd_return_home",
    "take_photo": "cmd_take_photo",
}


class PluginLoader:
    """
    Discovers and loads plugins from the plugins directory.
    Each plugin is a folder containing:
    - manifest.json
    - plugin.py (must contain a class inheriting NodePlugin or ControlPlugin)
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

        plugin_class, plugin_type = self._find_plugin_class(module, plugin_dir.name)
        if plugin_class is None:
            return False

        if plugin_type == "device":
            self._validate_plugin_commands(plugin_class, manifest, plugin_dir.name)
            plugin_registry.register(manifest["id"], plugin_class, manifest)
            logger.info(f"Device plugin loaded: {manifest['id']}")
        elif plugin_type == "control":
            from ..core.operation_manager import operation_manager
            operation_manager.register_control_plugin(plugin_class)
            logger.info(f"Control plugin loaded: {manifest['id']}")

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

    def _validate_plugin_commands(
        self, plugin_class: type, manifest: dict, name: str
    ) -> None:
        """
        Warn if the manifest declares a standard capability that the plugin
        doesn't implement. Catches the mismatch at load time, not at runtime.
        """
        declared_ids = {cap["id"] for cap in manifest.get("capabilities", [])}
        for cap_id, method_name in STANDARD_COMMAND_MAP.items():
            if cap_id in declared_ids and method_name not in plugin_class.__dict__:
                logger.warning(
                    f"Plugin '{name}' declares capability '{cap_id}' in manifest "
                    f"but does not override '{method_name}()' — "
                    f"this command will return 'not implemented' at runtime"
                )

    def _find_plugin_class(self, module, plugin_name: str):
        """Find a concrete NodePlugin or ControlPlugin subclass in module."""
        from .control_interfaces import ControlPlugin

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if not isinstance(attr, type):
                continue
            # Skip abstract classes — base classes (ROS2Plugin, MAVLinkPlugin, …)
            # are imported into plugin modules and must not be picked up.
            if getattr(attr, "__abstractmethods__", None):
                continue
            if issubclass(attr, NodePlugin) and attr is not NodePlugin:
                return attr, "device"
            if issubclass(attr, ControlPlugin) and attr is not ControlPlugin:
                return attr, "control"

        logger.error(
            f"No NodePlugin or ControlPlugin subclass found in {plugin_name}/plugin.py"
        )
        return None, None
