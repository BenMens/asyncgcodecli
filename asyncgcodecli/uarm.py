"""Driver for the UArm Swift Pro."""

__all__ = ["UArm"]

import asyncio
from asyncgcodecli.driver import (
    GenericDriver,
    GCodeGenericCommand,
)


class UArm(GenericDriver):
    """Stelt een UArm voor."""

    def __init__(self, port, *args, **kw):
        """
        Maak een nieuw UArm object.

        Parameters
        ----------
        port : string
            De naam van de usb port.
        """
        super().__init__(port, *args, **kw)
        self.limit_switch_on = False

    def _process_status(self, status):
        components = status.split(",")
        self.__status = components[0]

    def _queue_get_status(self):
        self.queue_command(GCodeGenericCommand("?", expect_ok=False))

    def _process_response(self, response):
        super()._process_response(response)

        if response == "@6 N0 V1":
            self.limit_switch_on = True

        if response == "@6 N0 V0":
            self.limit_switch_on = False

        if response == "@1":
            settings_command = GCodeGenericCommand("$$")
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.gcode_result

                self._ready_future.set_result(True)

            asyncio.create_task(wait_for_settings(settings_command))

    def set_wrist(self, angle: float):
        """
        Draai de pompeenheid.

        Draai de pompeenheid op de robotarm naar de opgegeven hoek.

        Parameters
        ----------
        angle : float
            De gewenste draaihoek

        Returns
        -------
        GCodeResult
            Een future voor het resultaat.
        """
        return self.queue_command(GCodeGenericCommand("G2202 N3 V%.2f F1" % angle))

    def set_mode(self, mode: int):
        """
        Stel mode in.

        Stel de robotarm in op de gewenste mode

        Parameters
        ----------
        mode : int

            0: Standard Suction mode
            1: Laser mode
            2: 3D printing mode
            3: Universal holder mode
            4: Pro Suction mode
            5: Plus Suction mode
            6: Touch Pen mode

        Returns
        -------
        GCodeResult
            Een future voor het resultaat.
        """
        return self.queue_command(GCodeGenericCommand("M2400 S{}".format(mode)))

    def set_pump(self, on: bool):
        """
        Zet de pomp aan of uit.

        Parameters
        ----------
        on : bool
            True voor aan, False voor uit

        Returns
        -------
        GCodeResult
            Een future voor het resultaat.
        """
        if on:
            return self.queue_command(GCodeGenericCommand("M2231 V1"))
        else:
            return self.queue_command(GCodeGenericCommand("M2231 V0"))

    def set_buzzer(self, freq: float, time: float):
        """
        Maak geluid.

        Maak geluid met de zoemer.

        Parameters
        ----------
        freq : float
            De frequentie
        time : float
            Tijd in milliseconden

        Returns
        -------
        GCodeResult
            Een future voor het resultaat.
        """
        return self.queue_command(
            GCodeGenericCommand("M2210 F%.2f T%.2f" % (freq, time))
        )

    def arc(self, clockwise=True, **kw):
        """
        Beweeg in een boog.

        Parameters
        ----------
        x : float
            Doelpositie x
        y : float
            Doelpositie y
        r : float
            De hoek in graden
        clockwise : bool
            True = met de klok mee (default)
            False = tegen de kok in

        Parameters
        ----------
        x : float
            Doelpositie x
        y : float
            Doelpositie y
        i : float
            x offset vanaf beginpunt naar moddelpint cirkel
        j : float
            y offset vanaf beginpunt naar moddelpint cirkel
        clockwise : bool
            True = met de klok mee (default)
            False = tegen de kok in

        Returns
        -------
        GCodeResult
            Een future voor het resultaat.
        """
        command = "G2" if clockwise else "G3"
        if "r" in kw is not None:
            if "x" in kw:
                command += " X%.2f" % kw["x"]
            if "y" in kw:
                command += " Y%.2f" % kw["y"]
            if "r" in kw:
                command += " R%.2f" % kw["r"]

            return self.queue_command(GCodeGenericCommand(command))

        elif "i" in kw or "j" in kw:
            if "x" in kw:
                command += " X%.2f" % kw["x"]
            if "y" in kw:
                command += " Y%.2f" % kw["y"]
            if "i" in kw:
                command += " I%.2f" % kw["i"]
            if "j" in kw:
                command += " J%.2f" % kw["j"]

            return self.queue_command(GCodeGenericCommand(command))
