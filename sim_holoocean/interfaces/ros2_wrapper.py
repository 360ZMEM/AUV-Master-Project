class ROS2Wrapper:
    """Placeholder adapter for future real-AUV ROS2 integration.

    This shell intentionally keeps API compatible with sim wrapper style.
    """

    def __init__(self, config):
        self.config = config

    def open(self):
        raise NotImplementedError("ROS2 wrapper shell only. Implement with rclpy.Node in future.")

    def reset_and_tick(self):
        raise NotImplementedError("ROS2 wrapper shell only.")

    def step(self, command5):
        raise NotImplementedError("ROS2 wrapper shell only.")

    def close(self):
        return None
