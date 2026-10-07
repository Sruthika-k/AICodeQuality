import math


def calculate_circle_area(radius):
    """Calculate the area of a circle given its radius.

    Args:
        radius (int or float): The radius of the circle. Must be non-negative.

    Returns:
        float: The area of the circle.

    Raises:
        TypeError: If radius is not an integer or a float.
        ValueError: If radius is negative.
    """
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        raise TypeError("Radius must be a numeric value (int or float).")
    if radius < 0:
        raise ValueError("Radius cannot be negative.")

    return math.pi * (radius**2)