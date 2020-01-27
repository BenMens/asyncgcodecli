"""Voorbeeld 2."""

from driver import UArm


# De onderstaande functie stuurt een reeks van commando's
# naar de robotarm.
async def do_move_arm(uarm: UArm):
    """Beweeg de robotarm in een cool patroon."""
    # set de robot arm op mode 0 (pomp)
    uarm.set_mode(0)

    uarm.move(150, 0, 150, 200)

    for _ in range(1, 5):
        uarm.move(150, -200, 100, 200)
        uarm.move(150,    0, 100, 200)
        uarm.move(150,  100, 100,  50)
        uarm.move(150,  200, 100,  25)

    # for i in range(1,5):
    #     uarm.move(150, 200, 100, 200)
    #     uarm.move(150, -200, 100, 200)
    #     uarm.move(300, 0, 100, 200)

    # uarm.move(150, 0, 10, 200)
    # uarm.move(150, 0, 150, 200)

    # uarm.move(150,  -200, 15,  200)

    # await uarm.sleep(3)

    # uarm.move(150,  -200, 5,  200)

    # # uarm.set_pump(True)
    # await uarm.sleep(1)

    # uarm.move(150,  -200, 20,  200)
    # uarm.move(150,   200, 20,  200)
    # r: GCodeResult = uarm.move(150,   200,  5,  200)

    # uarm.set_pump(False)
    # await uarm.sleep(2)

    # uarm.move(150,   200,  15,    2)

    # uarm.move(150,   200, 150,  200)
    # uarm.move(150,  -200, 150,  200)

    # for x in range(1, 3):
    #     await uarm.sleep(1)
    #     uarm.set_wrist(120)
    #     await uarm.sleep(1)
    #     uarm.set_wrist(60)

    # zorg voor een mooie landing
    uarm.move(150, 0, 20, 200)
    uarm.set_pump(False)
    await uarm.sleep(1)
    uarm.move(150, 0, 0, 10)


# Gebruik de bovenstaaande functie om de
# de robotarm die verbonden is met de port /dev/cu.usbmodem14101
# te besturen.
UArm.execute('/dev/cu.usbmodem14101', do_move_arm)
