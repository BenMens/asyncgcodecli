"""Test 2."""

from context import Plotter
from context import logger


logger.set_log_level(logger.INFO)


async def move_script(plotter: Plotter):
    pass


# Gebruik de bovenstaaande functie om de
# de robotarm die verbonden is met de port /dev/cu.usbmodem14101
# te besturen.
Plotter.execute_on_plotter('/dev/cu.usbmodem14101', move_script)
