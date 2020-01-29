"""Driver for the UArm Swift Pro."""

import asyncio
from asyncgcodecli.driver import \
    GenericDriver, \
    GCodeGenericCommand, \
    GCodeMoveCommand


class UArm(GenericDriver):
    """Stelt een UArm voor."""

    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)
        self.limit_switch_on = False

    def _process_status(self, status):
        components = status.split(',')
        self.__status = components[0]

    def _queue_get_status(self):
        self.queue_command(GCodeGenericCommand('?', expect_ok=False))

    def _process_response(self, response):
        super()._process_response(response)

        if response == f"@6 N0 V1":
            self.limit_switch_on = True

        if response == f"@6 N0 V0":
            self.limit_switch_on = False

        if response == f"@1":
            settings_command = GCodeGenericCommand('$$')
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.gcode_result

                self._ready_future.set_result(True)

            asyncio.create_task(wait_for_settings(settings_command))

    def move(self, x: float, y: float, z: float, speed: float = 100):
        """
        Beweeg robotarm.

        Beweeg de robot arm naar het punt (x, y, z) met de
        aangegeven snelheid.

        Parameters:
        -----------
            x : float
                x-doelpositie
            y : float
                y-doelpositie
            z : float
                z-doelpositie
            speed:
                float De beweegsnelheid. 200 is het maximum.

        Resultaat:
        ----------
            GCodeResult: Een future voor het resultaat.
        """
        return self.queue_command(GCodeMoveCommand(x=x, y=y, z=z, speed=speed))

    def set_wrist(self, angle: float):
        """
        Draai de pompeenheid.

        Draai de pompeenheid op de robotarm naar de opgegeven hoek.

        Parameters:
        -----------
            angle : float
                De gewenste draaihoek

        Resultaat:
        ----------
            GCodeResult: Een future voor het resultaat.
        """
        return self.queue_command(
            GCodeGenericCommand('G2202 N3 V%.2f F1' % angle))

    def set_mode(self, mode: int):
        """
        Stel mode in.

        Stel de robotarm in op de gewenste mode

        Parameters:
        -----------
            mode : int

                0: Standard Suction mode
                1: Laser mode
                2: 3D printing mode
                3: Universal holder mode
                4: Pro Suction mode
                5: Plus Suction mode
                6: Touch Pen mode

        Resultaat:
        ----------
            GCodeResult: Een future voor het resultaat.
        """
        return self.queue_command(
            GCodeGenericCommand('M2400 S{}'.format(mode)))

    def set_pump(self, on: bool):
        """
        Zet de pomp aan of uit.

        Parameters:
        -----------
            on : bool
                True voor aan, False voor uit

        Resultaat:
        ----------
            GCodeResult: Een future voor het resultaat.
        """
        if on:
            return self.queue_command(GCodeGenericCommand('M2231 V1'))
        else:
            return self.queue_command(GCodeGenericCommand('M2231 V0'))

    def set_buzzer(self, freq, time):
        return self.queue_command(
            GCodeGenericCommand('M2210 F%.2f T%.2f' % (freq, time)))

    def arc(self, clockwise=True, **kw):
        command = 'G2' if clockwise else 'G3'
        if 'r' in kw is not None:
            if 'x' in kw:
                command += ' X%.2f' % kw['x']
            if 'y' in kw:
                command += ' Y%.2f' % kw['y']
            if 'r' in kw:
                command += ' R%.2f' % kw['r']

            return self.queue_command(GCodeGenericCommand(command))

        elif 'i' in kw or 'j' in kw:
            if 'x' in kw:
                command += ' X%.2f' % kw['x']
            if 'y' in kw:
                command += ' Y%.2f' % kw['y']
            if 'i' in kw:
                command += ' I%.2f' % kw['i']
            if 'j' in kw:
                command += ' J%.2f' % kw['j']

            return self.queue_command(GCodeGenericCommand(command))

    async def sleep(self, time: float):
        """
        Wacht even.

        Wacht eerst tot de robotarm alle opdrachten in de wachtrij heeft
        uitgevoerd en klaar is met bewegen. Wacht daarna nog een
        beetje extra.

        Parameters:
        -----------
            time : float De extra wachtijd in seconden

        Resultaat:
        ----------
            coroutine: Deze functie geeft een coroutine als resultaat. Daarom
            moet je await gebruiken.

            Voorbeeld::

                await uarm.sleep(1)
        """
        await self.queue_empty()
        await asyncio.sleep(time)

    @staticmethod
    def execute(port: any, script):
        """
        Voer script uit op UArm.

        Parameters
        ----------
            port : str of list
                bijvoorbeeld:
                    '/dev/cu.usbmodem14101' of
                    ['/dev/cu.usbmodem14101', '/dev/cu.usbmodem14201']
            script : script
                Het uit te voeren script.

        Voorbeeld met 1 robotarm::

            async def do_move_arm(uarm: UArm):
                uarm.move(150, 0, 150, 200)

            UArm.send('/dev/cu.usbmodem14101', do_move_arm)


        Voorbeeld met 2 robotarmen::

            async def do_move_arm(uarms: UArm):
                for arm in arms:
                    uarm.move(150, 0, 150, 200)

            UArm.send(
                ['/dev/cu.usbmodem14101', '/dev/cu.usbmodem14201'],
                do_move_arm)
        """
        async def do_execute():
            uarms = []
            if isinstance(port, list):
                uarms = [UArm(p) for p in port]
            else:
                uarms = [UArm(port)]

            for uarm in uarms:
                uarm.start()
                await uarm.ready()

            if isinstance(port, list):
                await script(uarms)
            else:
                await script(uarms[0])

            for uarm in uarms:
                await uarm.queue_empty()
                uarm.stop()
                await asyncio.sleep(2)

        asyncio.run(do_execute())
