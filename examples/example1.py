"""Voorbeeld met 1 arm."""

from asyncgcodecli import UArm, GenericDriver


async def move_script(uarms: UArm):
    for uarm in uarms:

        """Script that moves the robot arm."""
        # set de robot arm mode to 0 (pomp)
        uarm.set_mode(0)

        uarm.move_linear(150, 0, 150, 200)

        # make a nice landing
        uarm.move_linear(150, 0, 20, 200)
        await uarm.sleep(1)
        uarm.move_linear(150, 0, 0, 10)


# Execute move_script on the UArm that is
# connected to /dev/cu.usbmodem14101
GenericDriver.execute_on_devices(
    lambda: [
        UArm("/dev/cu.usbserial-1420"),
    ],
    move_script,
)
