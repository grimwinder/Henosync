import asyncio
import logging
from typing import Any, Callable
from .base import BaseTransport

logger = logging.getLogger(__name__)

# roslibpy is optional — only needed when ROS2 transport is used
try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    ROSLIBPY_AVAILABLE = False
    logger.warning(
        "roslibpy not installed. ROS2 transport unavailable. "
        "Install with: pip install roslibpy"
    )


class ROS2Transport(BaseTransport):
    """
    Transport for ROS2 robots via rosbridge WebSocket server.

    Requirements:
    - roslibpy installed (pip install roslibpy)
    - rosbridge_server running on the robot:
        ros2 launch rosbridge_server rosbridge_websocket_launch.xml

    Connection config expected in plugin manifest:
        {
            "host": "192.168.1.100",  # Robot IP address
            "port": 9090              # rosbridge port (default 9090)
        }

    Plugin developers building ROS2 plugins use this transport
    to subscribe to topics and call services on their robot.
    """

    SCHEME = "ros2"

    def __init__(self):
        self._client: Any = None
        self._connected = False
        self._host = ""
        self._port = 9090
        self._subscribers: dict[str, Any] = {}
        self._connection_callbacks: list[Callable] = []
        self._disconnection_callbacks: list[Callable] = []

    async def connect(
        self,
        host: str,
        port: int = 9090,
        **kwargs
    ) -> bool:
        """
        Connect to a rosbridge WebSocket server.

        Args:
            host: Robot IP address (e.g. "192.168.1.100")
            port: rosbridge port (default 9090)
        """
        if not ROSLIBPY_AVAILABLE:
            logger.error(
                "roslibpy not installed. "
                "Run: pip install roslibpy"
            )
            return False

        self._host = host
        self._port = port

        try:
            # Run roslibpy connection in thread pool
            # (roslibpy uses blocking calls internally)
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                self._connect_sync,
                host,
                port
            )
            return success

        except Exception as e:
            logger.error(f"ROS2 transport connection error: {e}")
            return False

    def _connect_sync(self, host: str, port: int) -> bool:
        """Synchronous connection — runs in thread pool."""
        try:
            self._client = roslibpy.Ros(host=host, port=port)
            self._client.run()

            # Wait up to 5 seconds for connection
            timeout = 5.0
            elapsed = 0.0
            while not self._client.is_connected and elapsed < timeout:
                import time
                time.sleep(0.1)
                elapsed += 0.1

            if self._client.is_connected:
                self._connected = True
                logger.info(f"ROS2 transport connected to {host}:{port}")
                return True
            else:
                logger.warning(
                    f"ROS2 transport timed out connecting to {host}:{port}"
                )
                return False

        except Exception as e:
            logger.error(f"ROS2 sync connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from rosbridge."""
        self._connected = False

        # Unsubscribe all topics
        for topic in self._subscribers.values():
            try:
                topic.unsubscribe()
            except Exception:
                pass
        self._subscribers.clear()

        # Terminate roslibpy client
        if self._client:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self._client.terminate
                )
            except Exception as e:
                logger.error(f"ROS2 disconnect error: {e}")
            self._client = None

        logger.info("ROS2 transport disconnected")

    async def send(self, data: dict[str, Any]) -> bool:
        """
        ROS2 transport send is handled per-topic by plugins.
        Use publish_to_topic() instead for ROS2.
        """
        return self._connected

    async def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            return self._client.is_connected
        except Exception:
            return False

    # ── ROS2 Specific Methods ─────────────────────────────────────
    # Plugin developers use these methods in their plugins

    def subscribe_topic(
        self,
        topic: str,
        message_type: str,
        callback: Callable
    ) -> None:
        """
        Subscribe to a ROS2 topic.

        Args:
            topic:        ROS2 topic name (e.g. "/battery_state")
            message_type: ROS2 message type (e.g. "sensor_msgs/BatteryState")
            callback:     Called with message dict when data arrives

        Example in a plugin:
            self.transport.subscribe_topic(
                "/battery_state",
                "sensor_msgs/BatteryState",
                self._on_battery
            )
        """
        if not self._client or not self._connected:
            logger.warning(f"Cannot subscribe to {topic} — not connected")
            return

        if topic in self._subscribers:
            return

        try:
            listener = roslibpy.Topic(
                self._client,
                topic,
                message_type
            )
            listener.subscribe(callback)
            self._subscribers[topic] = listener
            logger.debug(f"Subscribed to ROS2 topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to subscribe to {topic}: {e}")

    def unsubscribe_topic(self, topic: str) -> None:
        """Unsubscribe from a ROS2 topic."""
        if topic in self._subscribers:
            try:
                self._subscribers[topic].unsubscribe()
            except Exception:
                pass
            del self._subscribers[topic]

    def publish_to_topic(
        self,
        topic: str,
        message_type: str,
        message: dict
    ) -> bool:
        """
        Publish a message to a ROS2 topic.

        Args:
            topic:        ROS2 topic name (e.g. "/cmd_vel")
            message_type: ROS2 message type (e.g. "geometry_msgs/Twist")
            message:      Message dict matching the ROS2 message format

        Example in a plugin:
            self.transport.publish_to_topic(
                "/cmd_vel",
                "geometry_msgs/Twist",
                {
                    "linear": {"x": 0.5, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
                }
            )
        """
        if not self._client or not self._connected:
            return False

        try:
            publisher = roslibpy.Topic(
                self._client,
                topic,
                message_type
            )
            publisher.publish(roslibpy.Message(message))
            return True
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            return False

    def call_service(
        self,
        service: str,
        service_type: str,
        request: dict,
        callback: Callable
    ) -> None:
        """
        Call a ROS2 service.

        Args:
            service:      Service name (e.g. "/set_mode")
            service_type: Service type (e.g. "std_srvs/SetBool")
            request:      Request dict
            callback:     Called with response dict

        Example in a plugin:
            self.transport.call_service(
                "/set_mode",
                "std_srvs/SetBool",
                {"data": True},
                self._on_mode_set
            )
        """
        if not self._client or not self._connected:
            logger.warning(f"Cannot call service {service} — not connected")
            return

        try:
            svc = roslibpy.Service(
                self._client,
                service,
                service_type
            )
            svc.call(
                roslibpy.ServiceRequest(request),
                callback
            )
        except Exception as e:
            logger.error(f"Failed to call service {service}: {e}")

    @property
    def client(self):
        """Direct access to roslibpy client for advanced use."""
        return self._client