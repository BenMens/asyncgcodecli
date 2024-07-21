"""Voorbeeld met 2 armen."""

from asyncgcodecli import UArm, GenericDriver


async def move_script(uarms: UArm):
    """Script that moves the robot arm."""
    # set de robot arm mode to 0 (pomp)

    for uarm in uarms:
        uarm.set_mode(0)

    for _ in range(1, 5):
        for uarm in uarms:
            await uarm.sleep(0)

        uarms[0].move_linear(150, -200, 150, 200)
        uarms[1].move_linear(150, 200, 150, 200)

        for uarm in uarms:
            await uarm.sleep(0)

        uarms[0].move_linear(150, 0, 150, 200)
        uarms[1].move_linear(150, 0, 150, 200)

    for uarm in uarms:
        await uarm.sleep(0)

    for uarm in uarms:
        # make a nice landing
        uarm.move_linear(150, 0, 20, 200)

    for uarm in uarms:
        await uarm.sleep(0)

    for uarm in uarms:
        # make a nice landing
        uarm.move_linear(150, 0, 0, 10)


# Execute move_script on the UArm that is
# connected to /dev/cu.usbmodem14101
GenericDriver.execute_on_devices(
    lambda: [
        UArm("/dev/cu.usbserial-1420"),
        UArm("/dev/cu.usbserial-1421"),
    ],
    move_script,
)
