"""
GPS map visualization widget
C# Reference: Form1.cs pictureBox1_Paint() method, lines 1910-2100
"""

import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QPolygonF, QCursor


class MapWidget(QWidget):
    """
    GPS map visualization widget
    C# Reference: Form1.cs lines 1910-2100
    """

    def __init__(self, main_window=None):
        super().__init__(main_window)
        self.main_window = main_window

        # Enable mouse tracking
        self.setMouseTracking(True)

        # Map state
        self.scale = 0.25
        self.origin_lon = 110.123
        self.origin_lat = 31.03
        self.first_gps = True

        # Map pan offset (for dragging)
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0

        # Mouse state
        self.last_mouse_pos = QPointF()
        self.is_panning = False
        self.distance_measuring = False
        self.measure_start = QPointF()
        self.measure_end = QPointF()

        # Set minimum size
        self.setMinimumSize(400, 400)

    def set_map_origin(self, longitude: float, latitude: float):
        """Set map origin from first GPS fix"""
        if self.first_gps:
            self.origin_lon = longitude
            self.origin_lat = latitude
            self.first_gps = False
            print(f"Map origin set to: {longitude:.6f}, {latitude:.6f}")

    def gps_to_screen(self, longitude: float, latitude: float) -> QPointF:
        """
        Convert GPS coordinates to screen coordinates
        C# Reference: Form1.cs lines 1966-1967

        Args:
            longitude: GPS longitude
            latitude: GPS latitude

        Returns:
            Screen coordinates (relative to map center)
        """
        # Convert to meters from origin
        dx = (longitude - self.origin_lon) * 111120.0 * math.cos(math.radians(self.origin_lat))
        dy = (latitude - self.origin_lat) * 111120.0

        # Apply scale
        screen_x = dx * self.scale
        screen_y = -dy * self.scale  # Negative because Y is down in screen coords

        return QPointF(screen_x, screen_y)

    def paintEvent(self, event):
        """
        Paint map with GPS tracks, waypoints, AUV icon
        C# Reference: Form1.cs pictureBox1_Paint
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()

        # Map origin (center of widget)
        origin_x = width / 2.0
        origin_y = height / 2.0

        # Calculate ratio based on widget size (C# line 1915)
        min_dimension = min(width, height)
        ratio = min_dimension / 450.0  # 225.0 * 2

        # Translate coordinate system to center
        painter.translate(origin_x, origin_y)

        # Apply pan offset
        painter.translate(self.pan_offset_x, self.pan_offset_y)

        # Draw grid
        self._draw_grid(painter, width, height, ratio)

        # Draw GPS trajectory
        if self.main_window and hasattr(self.main_window, 'gps_queue'):
            self._draw_gps_trajectory(painter)

        # Draw dead reckoning trajectory
        if self.main_window and hasattr(self.main_window, 'dead_reckoning_queue'):
            self._draw_dead_reckoning_trajectory(painter)

        # Draw waypoint route
        if self.main_window and hasattr(self.main_window, 'autofixed_points'):
            self._draw_waypoint_route(painter)

        # Draw AUV icon
        if self.main_window:
            self._draw_auv_icon(painter, ratio)

        # Draw distance measurement
        if self.distance_measuring:
            self._draw_distance_measurement(painter)

    def _draw_grid(self, painter, width, height, ratio):
        """Draw map grid with coordinate lines"""
        # Draw main axes (C# lines 1927-1928)
        pen = QPen(QColor(0x5F9EA0), 0.5)  # CadetBlue
        painter.setPen(pen)

        painter.drawLine(0, int(-height/2), 0, int(height/2))
        painter.drawLine(int(-width/2), 0, int(width/2), 0)

        # Draw grid lines (C# lines 1930-1942)
        pen.setStyle(Qt.DashDotLine)
        painter.setPen(pen)

        for i in range(1, 9):
            if 100 * i < width / 2:
                painter.drawLine(int(-100*i), int(-height/2),
                               int(-100*i), int(height/2))
                painter.drawLine(int(100*i), int(-height/2),
                               int(100*i), int(height/2))

            if 100 * i < height / 2:
                painter.drawLine(int(-width/2), int(100*i),
                               int(width/2), int(100*i))
                painter.drawLine(int(-width/2), int(-100*i),
                               int(width/2), int(-100*i))

        # Draw "航行器" label (C# lines 1944-1948)
        font = QFont("Arial", int(8 * ratio))
        painter.setFont(font)
        painter.setPen(QColor(0xFFDEAD))  # NavajoWhite
        painter.drawText(int(-width/2 + 10), int(-height/2 + 18*ratio), "航行器")

        # Draw scale indicator (C# line 1963)
        scale_text = f"量程：{int(100/self.scale)}米/格"
        painter.drawText(int(-width/2), int(-height/2 + 23*ratio), scale_text)

    def _draw_gps_trajectory(self, painter):
        """Draw GPS trajectory as red dots (C# lines 1996-2007)"""
        if not self.main_window or not hasattr(self.main_window, 'gps_queue'):
            return

        gps_queue = self.main_window.gps_queue
        if gps_queue.count() < 1:
            return

        pen = QPen(QColor(255, 0, 0), 2.0)  # Red
        painter.setPen(pen)

        for lon, lat in gps_queue.get_all_points():
            screen_pos = self.gps_to_screen(lon, lat)
            # Draw 2px circle (C# line 2005)
            painter.drawEllipse(screen_pos, 1.0, 1.0)

    def _draw_dead_reckoning_trajectory(self, painter):
        """Draw dead reckoning trajectory as white dots (C# lines 1983-1994)"""
        if not self.main_window or not hasattr(self.main_window, 'dead_reckoning_queue'):
            return

        dr_queue = self.main_window.dead_reckoning_queue
        if dr_queue.count() < 1:
            return

        pen = QPen(QColor(255, 255, 255), 2.0)  # White
        painter.setPen(pen)

        for lon, lat in dr_queue.get_all_points():
            screen_pos = self.gps_to_screen(lon, lat)
            # Draw 2px circle (C# line 1992)
            painter.drawEllipse(screen_pos, 1.0, 1.0)

    def _draw_waypoint_route(self, painter):
        """Draw autonomous fixed point route"""
        if not self.main_window or not hasattr(self.main_window, 'autofixed_points'):
            return

        waypoints = self.main_window.autofixed_points
        if not waypoints:
            return

        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.setPen(QColor(255, 0, 0))

        for i, wp in enumerate(waypoints):
            screen_pos = self.gps_to_screen(wp.longitude, wp.latitude)

            # Draw waypoint dot
            painter.setBrush(QBrush(QColor(255, 0, 0)))
            painter.drawEllipse(screen_pos, 2.0, 2.0)

            # Draw waypoint info
            info_text = f"{i+1}"
            painter.drawText(int(screen_pos.x()), int(screen_pos.y()), info_text)

            # Draw line to next waypoint
            if i < len(waypoints) - 1:
                next_wp = waypoints[i + 1]
                next_screen_pos = self.gps_to_screen(next_wp.longitude, next_wp.latitude)
                painter.drawLine(screen_pos, next_screen_pos)

    def _draw_auv_icon(self, painter, ratio):
        """Draw AUV icon with heading (C# lines 1969-1979)"""
        if not self.main_window:
            return

        # Get AUV position
        auv_lon = getattr(self.main_window, 'auv_longitude', 0.0)
        auv_lat = getattr(self.main_window, 'auv_latitude', 0.0)
        heading = getattr(self.main_window, 'auv_heading', 0.0)

        screen_pos = self.gps_to_screen(auv_lon, auv_lat)

        # Create AUV-shaped polygon (pentagon pointing in heading direction)
        pi = math.pi / 180.0
        points = []
        for angle_offset in [0, 30, 150, 210, 330]:
            angle_rad = math.radians(heading + angle_offset)
            x = screen_pos.x() + ratio * 15 * math.sin(angle_rad)
            y = screen_pos.y() - ratio * 15 * math.cos(angle_rad)
            points.append(QPointF(x, y))

        polygon = QPolygonF(points)
        pen = QPen(QColor(0x4169E1), 2.0 * ratio)  # CornflowerBlue
        painter.setPen(pen)
        painter.drawPolygon(polygon)

        # Draw center circle (C# line 1960)
        painter.setBrush(QBrush(QColor(0x4169E1)))
        painter.drawEllipse(screen_pos, 2.0*ratio, 2.0*ratio)

    def _draw_distance_measurement(self, painter):
        """Draw distance measurement line"""
        if not self.distance_measuring:
            return

        pen = QPen(QColor(255, 255, 0), 2.0)  # Yellow
        painter.setPen(pen)

        # Convert screen coordinates to centered coordinates
        width = self.width()
        height = self.height()

        # measure_start and measure_end are in screen coordinates
        # Need to convert to centered coordinates (relative to widget center)
        start_x = self.measure_start.x() - width / 2.0
        start_y = self.measure_start.y() - height / 2.0
        end_x = self.measure_end.x() - width / 2.0
        end_y = self.measure_end.y() - height / 2.0

        # Apply pan offset
        start_x -= self.pan_offset_x
        start_y -= self.pan_offset_y
        end_x -= self.pan_offset_x
        end_y -= self.pan_offset_y

        painter.drawLine(QPointF(start_x, start_y), QPointF(end_x, end_y))

        # Calculate distance
        dx = end_x - start_x
        dy = end_y - start_y
        distance_pixels = math.sqrt(dx*dx + dy*dy)
        distance_meters = distance_pixels / self.scale

        # Calculate angle
        angle = math.degrees(math.atan2(dy, dx))
        angle = (angle + 90) % 360

        # Draw distance text
        font = QFont("Times New Roman", 12)
        painter.setFont(font)
        text = f"{distance_meters:.0f}米, {angle:.1f}°"
        painter.drawText(int(end_x), int(end_y - 15), text)

    def mousePressEvent(self, event):
        """Handle mouse clicks for waypoint selection and measurement"""
        pos = event.position()

        if event.button() == Qt.LeftButton:
            # Check if in waypoint selection mode
            if self.main_window and hasattr(self.main_window, 'selecting_waypoint'):
                if self.main_window.selecting_waypoint:
                    # Convert screen position to GPS coordinates
                    width = self.width()
                    height = self.height()

                    # Calculate position relative to center (accounting for pan)
                    rel_x = pos.x() - width / 2.0 - self.pan_offset_x
                    rel_y = pos.y() - height / 2.0 - self.pan_offset_y

                    # Convert to GPS coordinates
                    dx_meters = rel_x / self.scale
                    dy_meters = -rel_y / self.scale  # Negative because Y is down

                    longitude = self.origin_lon + dx_meters / (111120.0 * math.cos(math.radians(self.origin_lat)))
                    latitude = self.origin_lat + dy_meters / 111120.0

                    # Add waypoint to main window
                    self.main_window.add_waypoint_from_map(longitude, latitude)
                    print(f"Waypoint added: {latitude:.6f}, {longitude:.6f}")
            else:
                # Start panning
                self.is_panning = True
                self.last_mouse_pos = pos

        elif event.button() == Qt.RightButton:
            # Start distance measurement
            self.distance_measuring = True
            self.measure_start = pos
            self.measure_end = pos

        elif event.button() == Qt.MiddleButton:
            # Middle button also starts panning
            self.is_panning = True
            self.last_mouse_pos = pos

    def mouseMoveEvent(self, event):
        """Handle mouse drag for panning and measurement"""
        pos = event.position()

        if self.is_panning:
            # Pan the map
            dx = pos.x() - self.last_mouse_pos.x()
            dy = pos.y() - self.last_mouse_pos.y()

            self.pan_offset_x += dx
            self.pan_offset_y += dy

            self.last_mouse_pos = pos
            self.update()
            self.setCursor(QCursor(Qt.ClosedHandCursor))

        elif self.distance_measuring:
            # Update measurement end point
            self.measure_end = pos
            self.update()
            self.setCursor(QCursor(Qt.CrossCursor))
        else:
            # Update cursor based on selection mode
            if self.main_window and hasattr(self.main_window, 'selecting_waypoint'):
                if self.main_window.selecting_waypoint:
                    self.setCursor(QCursor(Qt.PointingHandCursor))
                else:
                    self.setCursor(QCursor(Qt.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.OpenHandCursor))

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.LeftButton and self.is_panning:
            # Stop panning
            self.is_panning = False
            self.setCursor(QCursor(Qt.OpenHandCursor))

        elif event.button() == Qt.MiddleButton and self.is_panning:
            # Stop panning
            self.is_panning = False
            self.setCursor(QCursor(Qt.OpenHandCursor))

        elif event.button() == Qt.RightButton and self.distance_measuring:
            # Stop measuring
            self.distance_measuring = False
            self.setCursor(QCursor(Qt.ArrowCursor))

    def wheelEvent(self, event):
        """Handle mouse wheel for zoom"""
        # Zoom in/out (C# lines 1891-1907)
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale *= 1.1  # Zoom in
        else:
            self.scale *= 0.9  # Zoom out

        # Limit zoom range
        self.scale = max(0.001, min(12.0, self.scale))
        self.update()
