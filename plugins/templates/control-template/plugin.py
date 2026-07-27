# Henosync Control Plugin Template
# ==================================
# Copy this folder into plugins/control/, rename it, and build your plugin.
# The auto-navigate plugin in plugins/control/auto-navigate/ is a worked
# example — refer to it alongside this file.
#
# ── Imports ────────────────────────────────────────────────────────────────────
#
# from henosync_sdk import (
#     ControlPlugin,
#     OperationStatus,
#     OperationState,
#     UIContribution,
#     CapabilityRequirement,
#     DeviceCapability,
#     DeviceCategory,
# )
#
# ── Class declaration ──────────────────────────────────────────────────────────
#
# class MyOperationPlugin(ControlPlugin):
#
#     PLUGIN_ID           = "my-operation"   # must match manifest.json id
#     PLUGIN_NAME         = "My Operation"
#     PLUGIN_VERSION      = "0.1.0"
#     PLUGIN_AUTHOR       = "Your Name"
#     OPERATION_NAME      = "My Operation"
#     OPERATION_DESCRIPTION = "What this operation does"
#
#     # Devices this operation requires. Empty = accepts any device.
#     REQUIRED_CAPABILITIES = [
#         CapabilityRequirement(capability=DeviceCapability.GPS, required=True),
#     ]
#
#     # Limit to specific robot categories. Empty = accepts any category.
#     SUPPORTED_CATEGORIES = [
#         DeviceCategory.AGV,
#     ]
#
#     PRIORITY = 0   # higher number wins device conflicts
#
# ── __init__ ───────────────────────────────────────────────────────────────────
#
#     def __init__(self):
#         super().__init__()
#         # Declare state variables used by get_status() here.
#         # _stop_requested, _config, _context are provided by the base class.
#
# ── start(context) ─────────────────────────────────────────────────────────────
#
#     async def start(self, context):
#         # Runs as a background asyncio.Task until stop() is called.
#         # context.devices  — list of DeviceProxy objects matched at startup
#         # self._config     — operator config from get_ui_contribution() schema
#         # self._stop_requested — check this in your main loop to exit cleanly
#         #
#         # Interact with devices only through DeviceProxy:
#         #   device.move_to(lat, lon)
#         #   device.stop()
#         #   device.return_home()
#         #   device.get_gps_data()
#         #   device.get_battery_data()
#         #
#         # Notify the operator via:
#         #   context.send_alert(title, message, severity)
#
# ── stop() ─────────────────────────────────────────────────────────────────────
#
#     async def stop(self):
#         # Signal start() to exit. Must complete within 3 seconds.
#         # Set self._stop_requested = True and update your state.
#
# ── get_status() ───────────────────────────────────────────────────────────────
#
#     def get_status(self):
#         # Called frequently — must be non-blocking (no awaits).
#         # Return OperationStatus(state=..., status_text=...).
#
# ── get_ui_contribution() ──────────────────────────────────────────────────────
#
#     def get_ui_contribution(self):
#         # Describes the operator config form shown in the Mission Planner.
#         # Return UIContribution(display_name, description, icon, config_schema).
#         #
#         # config_schema field types: "string", "number", "boolean", "select"
#         # For "select" include: "options": [{"label": "...", "value": "..."}]
#         # Optional per field: "required", "default", "min", "max", "placeholder"
#
# ── Optional event handlers ────────────────────────────────────────────────────
#
#     async def on_device_joined(self, device):
#         # Called when a new device is recruited mid-operation.
#
#     async def on_device_left(self, device):
#         # Called when an assigned device disconnects or is released.
#         # Decide here whether to abort or continue with remaining devices.
#
#     async def on_message(self, sender_id, message):
#         # Called when another control plugin sends a message to this one.
#
#     async def on_operator_input(self, prompt, response):
#         # Called when the operator responds to a request_operator_input() prompt.
