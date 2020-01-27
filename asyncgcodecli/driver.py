"""Driver voor het aansturen van een gcode apparaat via de seriele poort."""

import serial
import threading
import time
import queue
import re
import asyncio

TRACE = 1


class GCodeDeviceEvent:
    """Basis class voor CGodeEvents."""

    def __init__(self, *args, **kw):
        """Initialize GCodeDeviceEvent."""
        super().__init__(*args, **kw)


class GCodeDeviceConnectEvent(GCodeDeviceEvent):
    """Event that is fired when a device connects or disconnects."""

    def __init__(self, connected, *args, **kw):
        """Initialize GCodeDeviceConnectEvent."""
        super().__init__(*args, **kw)
        self.__conected = connected


class CommandProcessedEvent(GCodeDeviceEvent):
    def __init__(self, command, *args, **kw):
        super().__init__(*args, **kw)
        self.command = command


class ResponseReveivedEvent(GCodeDeviceEvent):
    def __init__(self, response, *args, **kw):
        super().__init__(*args, **kw)
        self.response = response


class GCodeResult(asyncio.Future):
    """
    Het resultaat van een gcode-opdracht.

    GCodeResult is het resultaat dat het aangesloten apparaat zoals een
    robotarm, teruggeeft op een gcode-opdracht. Omdat het tijd kost voor
    het aangeslopen apparaat om de opdracht te verwerken, duurt het ook
    even voordat het het resultaat beschikbaar is. Daarom moet je await
    gebruiken als
    je wilt wachten op het resultaat.

    Voorbeeld 1::

        # Het commando move geeft een GCodeResult als resultaat.
        resultaat_als_gcode_result = uarm.move(150, 0, 150, 200)

        resultaat = await resultaat_als_gcode_result

    Voorbeeld 2 (korte notatie)::

        resultaat = await uarm.move(150, 0, 150, 200)

    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)


class GCodeCommand:
    def __init__(self, expect_ok=True, *args, **kw):
        super().__init__(*args, **kw)
        self.send = False
        self.confirmed = False
        self.gcode_result = GCodeResult()
        self.expect_ok = expect_ok

    def command(self):
        return b''


class GCodeGenericCommand(GCodeCommand):
    def __init__(self, gcode, *args, **kw):
        super().__init__(*args, **kw)
        self.gcode = str.encode(gcode) + b'\r'

    def command(self):
        return self.gcode


class GCodeMoveCommand(GCodeCommand):
    def __init__(self, x=None, y=None, z=None, speed=None, *args, **kw):
        super().__init__(*args, **kw)
        self.x = x
        self.y = y
        self.z = z
        self.speed = speed

    def command(self):
        result = b'G1'
        if self.x is not None:
            result += b' X%.2f' % (self.x)
        if self.y is not None:
            result += b' Y%.2f' % (self.y)
        if self.z is not None:
            result += b' Z%.2f' % (self.z)
        if self.speed is not None:
            result += b' F%.2f' % (self.speed)

        result += b'\r'
        return result


class GCodeHomeCommand(GCodeCommand):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def command(self):
        return b'$h\r'


class GCodeSetSpindleCommand(GCodeCommand):
    def __init__(self, pos, *args, **kw):
        super().__init__(*args, **kw)
        self.pos = pos

    def command(self):
        return b'M3 S%.2f\r' % (self.pos)


class GCodeWaitCommand(GCodeCommand):
    def __init__(self, time, *args, **kw):
        super().__init__(*args, **kw)
        self.time = time

    def command(self):
        return b'G4 P%.2f\r' % (self.time)


class SerialReceiveThread(threading.Thread):
    def __init__(self, port, *args, **kw):
        super().__init__(*args, **kw)
        self.event_queue = queue.Queue()
        self.port = port
        self.stop = False
        self.__serial = serial.Serial(None, baudrate=115200, timeout=1)
        self.setDaemon(1)

    def post_event(self, event):
        self.event_queue.put(event)

    def write(self, gcode):
        self.__serial.write(gcode)

    def run(self):
        while (not self.stop):

            print('Connecting ', end='', flush=True)

            while (not self.__serial.is_open):
                if (self.stop):
                    break
                try:
                    self.__serial.port = self.port
                    self.__serial.open()
                    self.post_event(GCodeDeviceConnectEvent(True))
                    print('')
                    print('Connected')

                except serial.SerialException:
                    print('.', end='', flush=True)
                    time.sleep(1)

            response = f''

            while(self.__serial.is_open):
                if (self.stop):
                    break
                try:
                    b = self.__serial.read(size=1)
                    if b:
                        if b == b'\n' or b == b'\r':
                            if (len(b) > 0):
                                self.post_event(
                                    ResponseReveivedEvent(response))
                                response = f''
                        else:
                            response += b.decode("utf-8")

                except serial.SerialException:
                    self.post_event(GCodeDeviceConnectEvent(False))
                    self.__serial.close()
                    print('Connection lost!')

        if (self.__serial.is_open):
            self.__serial.close()

        print('thread stopped')


class GenericDriver:
    def __init__(
            self, port,
            async_event_queue=None,
            advanced_flow_control=False,
            *args,
            **kw):
        super().__init__(*args, **kw)
        self.__port = port
        self.__async_event_queue = async_event_queue
        self.__advanced_flow_control = advanced_flow_control
        self.__serial = None
        self.__process_serial_events_task = None
        self.__queue_empty_futures = []
        self._reset()

    def _reset(self):
        self.__conected = False
        self.__processed_tail = 0
        self.__gcode_queue = []
        self.__send_limit = 128
        self.__status = 'Unknown'
        self._ready_future = asyncio.Future()
        self.settings = {}

    def _flush_queue(self):
        self.__gcode_queue = self.__gcode_queue[: self.__processed_tail]

    def _forward_event(self, event):
        if self.__async_event_queue:
            self.__async_event_queue.put_nowait(event)

    async def __process_serial_events(self):
        while True:
            await asyncio.sleep(0.01)
            while self.__serial is not None:
                try:
                    event = self.__serial.event_queue.get_nowait()
                    if isinstance(event, ResponseReveivedEvent):
                        self._process_response(event.response)

                    self.__check_queue_empty()

                    self._forward_event(event)

                except queue.Empty:
                    break

    def start(self):
        self.__serial = SerialReceiveThread(self.__port)
        self.__serial.start()

        self.__process_serial_events_task = asyncio.create_task(
            self.__process_serial_events())

    def stop(self):
        if self.__serial is not None:
            self.__serial.stop = True
            self.__serial = None

        if self.__process_serial_events_task is not None:
            self.__process_serial_events_task.cancel()

    def __process_queue(self):
        if not self.__serial:
            return

        for index in range(self.__processed_tail, len(self.__gcode_queue)):
            head = self.__gcode_queue[index]

            if head.send and not self.__advanced_flow_control:
                break
            if head.send and self.__advanced_flow_control:
                continue

            command = head.command()
            command_len = len(command)
            if (command_len > self.__send_limit):
                break

            self.__serial.write(command)
            self.__send_limit -= command_len
            head.send = True
            self._log(TRACE, command.decode("utf-8"))

            if not head.expect_ok:
                self._confirm_command({'result': 'ok', 'error_code': 0})

    def _confirm_command(self, result):
        head = self.__gcode_queue[self.__processed_tail]
        head.confirmed = True
        head.gcode_result.set_result(result)
        self.__processed_tail += 1
        self._forward_event(CommandProcessedEvent(head))
        self.__send_limit += len(head.command())
        self.__process_queue()

    def queue_command(self, command):
        self.__gcode_queue.append(command)
        self.__process_queue()
        return command.gcode_result

    def __check_queue_empty(self):
        if self.__processed_tail == len(self.__gcode_queue):
            for f in self.__queue_empty_futures:
                f.set_result(True)

            self.__queue_empty_futures.clear()

    def queue_empty(self):
        future = asyncio.Future()
        self.__queue_empty_futures.append(future)
        self.__check_queue_empty()
        return future

    def ready(self):
        return self._ready_future

    def _log(self, level, string):
        print(string)

    def _queue_get_status(self):
        self.queue_command(GCodeGenericCommand('?'))

    async def wait_for_idle(self):
        self.__status = 'Unknown'
        while True:
            if self.__status == 'Idle':
                break
            self._queue_get_status()
            await asyncio.sleep(0.1)

    def _process_response(self, response):
        self._log(TRACE, response)

        m = re.compile(r'\<?(.*)\>').match(response)
        if m is not None:
            self._process_status(m[1])

        if (response == "ok"):
            self._confirm_command({'result': 'ok', 'error_code': 0})

        if response == f"Grbl 1.1h ['$' for help]":
            settings_command = GCodeGenericCommand('$$')
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.gcode_result

                self._ready_future.set_result(True)

            asyncio.create_task(wait_for_settings(settings_command))

        m = re.compile(r'\$([0-9]+)=([0-9]+\.?[0-9]*).*').match(response)
        if m is not None:
            self.settings[m[1]] = m[2]

        m = re.compile(r'error:(.*)').match(response)
        if m is not None:
            # ToDo set error
            self._confirm_command({'result': 'error', 'error_code': m[1]})

        m = re.compile(r'E([0-9]*)').match(response)
        if m is not None:
            # ToDo set error
            self._confirm_command({'result': 'error', 'error_code': m[1]})

    def _process_status(self, status):
        components = status.split('|')
        self.__status = components[0]


class Plotter(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)

    def pen_up(self):
        self.queue_command(GCodeSetSpindleCommand(400))
        return self.queue_command(GCodeWaitCommand(1))

    def pen_down(self):
        self.queue_command(GCodeSetSpindleCommand(900))
        return self.queue_command(GCodeWaitCommand(1))

    def move(self, x, y, speed=10000):
        return self.queue_command(GCodeMoveCommand(x=x, y=y, speed=speed))

    def home(self):
        return self.queue_command(GCodeHomeCommand())

    @staticmethod
    def execute(port, func):
        async def do_execute():
            plotter = Plotter(port)
            plotter.start()
            await plotter.ready()
            await func(plotter)
            await plotter.queue_empty()
            plotter.stop()
            await asyncio.sleep(2)

        asyncio.run(do_execute())


class UArm(GenericDriver):
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
    def execute(port: str, script):
        """
        Voer script uit op UArm.

        Args:
        -----
            port (str): bijvoorbeeld: '/dev/cu.usbmodem14101'
            script (script): Het uit te voeren script.

        Voorbeeld::

            async def do_move_arm(uarm: UArm):
                uarm.move(150, 0, 150, 200)

            UArm.send('/dev/cu.usbmodem14101', 2, do_move_arm)

        """
        async def do_execute():
            uarm = UArm(port)
            uarm.start()
            await uarm.ready()

            await script(uarm)

            await uarm.queue_empty()
            uarm.stop()
            await asyncio.sleep(2)

        asyncio.run(do_execute())
