"""Voorbeeld met 1 arm."""
from asyncgcodecli import UArm


async def move_script(uarm: UArm):
    """Script that moves the robot arm."""
    # set de robot arm mode to 0 (pomp)
    uarm.set_mode(0)

    uarm.move(150, 0, 150, 200)

    # make a nice landing
    uarm.move(150, 0, 20, 200)
    await uarm.sleep(1)
    uarm.move(150, 0, 0, 10)

# Execute move_script on the UArm that is
# connected to /dev/cu.usbmodem14101
UArm.execute_on_robotarm(
    '/dev/cu.usbmodem14101',
    move_script)
