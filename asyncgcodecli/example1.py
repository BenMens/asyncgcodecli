"""Voorbeeld 1."""

from asyncgcodecli import Plotter


# De onderstaande functie stuurt een reeks van commando's
# naar de plotter waarmee een figuur wordt getekend
async def do_plot(plotter):
    """Stuur een figuur naar de plotter."""
    await plotter.home()
    plotter.pen_up()
    plotter.move(10, 10)
    plotter.pen_down()
    for i in range(0, 82, 2):
        await plotter.move(10+i,  10)
        # await plotter.wait_for_idle()
        plotter.move(90,   10+i)
        # await plotter.wait_for_idle()
        plotter.move(90-i, 90)
        # await plotter.wait_for_idle()
        plotter.move(10,   90-i)
        # await plotter.wait_for_idle()
    plotter.pen_up()
    plotter.move(0, 0)

# Gebruik de bovenstaaande functie om de
# de plotter die verbonden is met de port /dev/cu.usbmodem14201
# te besturen.
Plotter.execute('/dev/cu.usbmodem14201', do_plot)

