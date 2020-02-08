"""Test 1."""

from context import UArm


async def move_script(uarm: UArm):
    """Move robot arm script."""

    # set de robot arm op mode 0 (pomp)
    uarm.set_mode(0)

    uarm.move(150, 0, 150, 200)

    # uarm.arc(x=200, y=100, r=90)
    uarm.arc(x=200, y=50, i=0, j=50, clockwise=False)

    for _ in range(1, 5):
        uarm.set_buzzer(2000, 500)
        uarm.set_buzzer(5000, 500)

    for _ in range(1, 5):
        uarm.move(150, 0, 10, 200)
        uarm.move(350, 0, 10, 200)

    for _ in range(1, 5):
        uarm.move(150, -200, 150, 200)
        uarm.move(150, 200, 150, 200)

    # zorg voor een mooie landing
    uarm.move(150, 0, 20, 200)
    uarm.set_pump(False)
    await uarm.sleep(1)
    uarm.move(150, 0, 0, 10)


# Gebruik de bovenstaaande functie om de
# de robotarm die verbonden is met de port /dev/cu.usbmodem14101
# te besturen.
UArm.execute_on_robotarm('/dev/cu.usbmodem14101', move_script)
