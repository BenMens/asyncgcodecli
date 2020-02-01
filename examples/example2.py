"""Voorbeeld met 2 armen."""
from asyncgcodecli import UArm


async def move_script(uarms: UArm):
    """Script that moves the robot arm."""
    # set de robot arm mode to 0 (pomp)

    for uarm in uarms:
        uarm.set_mode(0)
        uarm.move(150, 0, 150, 200)

    for uarm in uarms:
        # make a nice landing
        uarm.move(150, 0, 20, 200)
        await uarm.sleep(1)
        uarm.move(150, 0, 0, 10)

# Execute move_script on the UArm that is
# connected to /dev/cu.usbmodem14101
UArm.execute_on_robotarms(
    ['/dev/cu.usbmodem14101', '/dev/cu.usbmodem14201'],
    move_script)
