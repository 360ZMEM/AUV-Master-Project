"""Display contract for inspection estimates; never accepts cable truth."""
from dataclasses import dataclass
import math


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class InspectionGeometry:
    position_ned: tuple[float, float, float] | None
    burial_m: float | None
    lateral_sigma_m: float | None
    width_m: float | None
    heading_deg: float | None
    label: str


def inspection_geometry(tracking, reference_z_m, age_s, timeout_s=1.5):
    """Return a labelled projection or qualified 3D point, never a truth fallback.

    reference_z_m is only the display plane. A valid burial value still needs
    a valid sea-floor reference supplied by the caller for a physical 3D plot.
    """
    unavailable = InspectionGeometry(None, None, None, None, None, "POSITION UNAVAILABLE / DEPTH UNAVAILABLE")
    age = finite(age_s)
    if age is None or not 0 <= age <= timeout_s:
        return InspectionGeometry(None, None, None, None, None, "ESTIMATE STALE / OUTPUT UNAVAILABLE")
    if not isinstance(tracking, dict):
        return unavailable
    diagnostics = tracking.get("diagnostics")
    if not isinstance(diagnostics, dict) or diagnostics.get("lateral_valid") is not True:
        return unavailable
    xy = tracking.get("estimated_cable_xy_m")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        return unavailable
    x, y, z = finite(xy[0]), finite(xy[1]), finite(reference_z_m)
    if x is None or y is None or z is None:
        return unavailable
    burial = finite(tracking.get("burial_depth_m")) if diagnostics.get("depth_valid") is True else None
    if burial is not None and burial < 0:
        burial = None
    sigma = finite(diagnostics.get("observation_line_sigma_m"))
    if sigma is not None and sigma < 0:
        sigma = None
    width = finite(diagnostics.get("fwhm_width_m"))
    if width is not None and width <= 0:
        width = None
    label = "LATERAL PROJECTION / DEPTH UNAVAILABLE" if burial is None else "POSITION + QUALIFIED BURIAL"
    return InspectionGeometry((x,y,z if burial is None else z+burial), burial, sigma, width,
                              finite(tracking.get("cable_heading_deg")), label)
