"""Driver voor het aansturen van een gcode apparaat via de seriele poort."""

import serial
import threading
import traceback
import time
import re
import asyncio
import asyncio.events
import asyncgcodecli.logger as logger

__all__ = [
    "GCodeDeviceEvent",
    "GCodeDeviceConnectEvent",
    "GCodeGenericCommand",
    "ResponseReveivedEvent",
    "GenericDriver",
    "GRBLDriver",
    "GCodeMoveRapidCommand",
    "GCodeMoveLinearCommand",
]


class TimeoutException(Exception):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)


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
        self.connected = connected


class CommandQueuedEvent(GCodeDeviceEvent):
    def __init__(self, command, *args, **kw):
        super().__init__(*args, **kw)
        self.command = command


class CommandStartedEvent(GCodeDeviceEvent):
    def __init__(self, command, *args, **kw):
        super().__init__(*args, **kw)
        self.command = command


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
    def post_event(self, event):

        resultaat = await uarm.move(150, 0, 150, 200)

    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)


class GCodeCommand:
    nextId = 0

    def __init__(self, expect_ok=True, *args, **kw):
        super().__init__(*args, **kw)
        self.send = False
        self.confirmed = False
        self.gcode_result = GCodeResult()
        self.expect_ok = expect_ok
        self.id = GCodeCommand.nextId
        GCodeCommand.nextId += 1

    def command(self):
        return b""


class GCodeGenericCommand(GCodeCommand):
    def __init__(self, gcode, *args, **kw):
        super().__init__(*args, **kw)

        # remove comment
        gcode = re.sub(r";.*", "", gcode)
        gcode = re.sub(r"\(.*\)", "", gcode)
        gcode = gcode.replace("\n", "")

        self.gcode = str.encode(gcode) + b"\r"

    def command(self):
        return self.gcode


class GCodeMoveRapidCommand(GCodeCommand):
    def __init__(self, x=None, y=None, z=None, speed=None, *args, **kw):
        super().__init__(*args, **kw)
        self.x = x
        self.y = y
        self.z = z
        self.speed = speed

    def command(self):
        result = b"G0"
        if self.x is not None:
            result += b" X%.2f" % (self.x)
        if self.y is not None:
            result += b" Y%.2f" % (self.y)
        if self.z is not None:
            result += b" Z%.2f" % (self.z)
        if self.speed is not None:
            result += b" F%.2f" % (self.speed)

        result += b"\r"
        return result


class GCodeMoveLinearCommand(GCodeCommand):
    def __init__(self, x=None, y=None, z=None, speed=None, *args, **kw):
        super().__init__(*args, **kw)
        self.x = x
        self.y = y
        self.z = z
        self.speed = speed

    def command(self):
        result = b"G1"
        if self.x is not None:
            result += b" X%.2f" % (self.x)
        if self.y is not None:
            result += b" Y%.2f" % (self.y)
        if self.z is not None:
            result += b" Z%.2f" % (self.z)
        if self.speed is not None:
            result += b" F%.2f" % (self.speed)

        result += b"\r"
        return result


class GCodeHomeCommand(GCodeCommand):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def command(self):
        return b"$h\r"


class GCodeSetSpindleCommand(GCodeCommand):
    def __init__(self, pos, *args, **kw):
        super().__init__(*args, **kw)
        self.pos = pos

    def command(self):
        return b"M3 S%.2f\r" % (self.pos)


class GCodeWaitCommand(GCodeCommand):
    def __init__(self, time, *args, **kw):
        super().__init__(*args, **kw)
        self.time = time

    def command(self):
        return b"G4 P%.2f\r" % (self.time)


class SerialReceiveThread(threading.Thread):
    def __init__(self, port, loop, *args, **kw):
        super().__init__(*args, **kw)
        self.event_queue = asyncio.Queue()
        self.port = port
        self.stop = False
        self._loop = loop
        self.__serial = serial.Serial(None, baudrate=115200, timeout=0.01)
        self.setDaemon(1)

    def post_event(self, event):
        async def do_post_event(event):
            if isinstance(event, ResponseReveivedEvent):
                logger.log(logger.TRACE, "received: {}", event.response)

            await self.event_queue.put(event)

        future = asyncio.run_coroutine_threadsafe(do_post_event(event), self._loop)
        return future.result()

    def write(self, gcode):
        self.__serial.write(gcode)
        logger.log(logger.TRACE, "transmitted: {}", gcode.decode("utf-8"))

    def run(self):
        logger.log(logger.INFO, "Connecting to {} ", (self.port))

        if not self.__serial.is_open:
            for i in range(0, 5):
                if self.stop:
                    break
                try:
                    if i > 0:
                        logger.log(
                            logger.INFO, "Connecting to {} retry {}", (self.port, i)
                        )
                    self.__serial.port = self.port
                    self.__serial.open()
                    self.post_event(GCodeDeviceConnectEvent(True))
                    logger.log(logger.INFO, "Connected.")
                    break

                except serial.SerialException:
                    time.sleep(1)

        if not self.__serial.is_open and not self.stop:
            self.post_event(GCodeDeviceConnectEvent(False))
            logger.log(logger.INFO, "Timeout.")
            logger.log(
                logger.FATAL,
                'Could not connect to device "{}". Timeout occured.',
                (self.port),
            )

        response = ""

        while self.__serial.is_open:
            if self.stop:
                break

            try:
                b = self.__serial.read(size=1)
                if b:
                    if b == b"\n" or b == b"\r":
                        if len(response) > 0:
                            self.post_event(ResponseReveivedEvent(response))
                            response = ""
                    else:
                        response += b.decode("utf-8")

            except serial.SerialException:
                logger.log(logger.FATAL, "Connection lost! {}", traceback.format_exc())
                self.post_event(GCodeDeviceConnectEvent(False))
                self.__serial.close()

        if self.__serial.is_open:
            self.__serial.close()

        logger.log(logger.TRACE, "SerialReceiveThread for {} stopped", self.port)


class GenericDriver:
    def __init__(
        self, port, async_event_queue=None, advanced_flow_control=False, *args, **kw
    ):
        super().__init__(*args, **kw)
        self.__port = port
        self.__async_event_queue = async_event_queue
        self.__advanced_flow_control = advanced_flow_control
        self.__serial = None
        self.__process_serial_events_task = None
        self.__queue_empty_futures = []
        self._ready_future = None

    def _process_server_reset(self):
        self.__conected = False
        self.__processed_tail = 0
        self.__gcode_queue = []
        self.__send_limit = 128
        self.__status = "Unknown"
        if self._ready_future is None or self._ready_future.done():
            self._ready_future = asyncio.Future()
        self.settings = {}
        self.__check_queue_empty()

    def _flush_queue(self):
        self.__gcode_queue = self.__gcode_queue[: self.__processed_tail]

    def _forward_event(self, event):
        if self.__async_event_queue:
            self.__async_event_queue.put_nowait(event)

    async def __process_serial_events(self):
        try:
            while self.__serial is not None:
                event = await self.__serial.event_queue.get()
                if isinstance(event, ResponseReveivedEvent):
                    self._process_response(event.response)

                if (
                    isinstance(event, GCodeDeviceConnectEvent)
                    and event.connected is False
                ):
                    self._ready_future.set_exception(TimeoutException())

                self.__check_queue_empty()

                self._forward_event(event)
        except Exception:
            logger.log(logger.FATAL, "error {}", traceback.format_exc())

    def start(self):
        self._process_server_reset()

        def on_serial_done(task):
            self.stop()

        logger.log(logger.TRACE, "starting")

        self.__serial = SerialReceiveThread(
            self.__port, asyncio.events.get_running_loop()
        )

        self.__process_serial_events_task = asyncio.create_task(
            self.__process_serial_events()
        )

        self.__process_serial_events_task.add_done_callback(on_serial_done)

        self.__serial.start()

    def stop(self):
        if self.__serial is not None:
            self.__serial.stop = True

        if self.__process_serial_events_task is not None:
            self.__process_serial_events_task.cancel()

    def __process_queue(self):
        if not self.__serial:
            return

        unconfirmed_commands_in_progress = False
        for index in range(self.__processed_tail, len(self.__gcode_queue)):
            head = self.__gcode_queue[index]

            if head.send and not head.confirmed:
                unconfirmed_commands_in_progress = True

            if unconfirmed_commands_in_progress and not self.__advanced_flow_control:
                break
            if head.send:
                continue

            command = head.command()
            command_len = len(command)
            if command_len > self.__send_limit:
                break

            self.__serial.write(command)
            self.__send_limit -= command_len
            print(self.__send_limit)
            head.send = True

            if not head.expect_ok:
                self._confirm_command({"result": "ok", "error_code": 0})

            if not head.confirmed:
                unconfirmed_commands_in_progress = True

    def _confirm_command(self, result):
        try:
            head = self.__gcode_queue[self.__processed_tail]
            head.confirmed = True
            head.gcode_result.set_result(result)
            self.__processed_tail += 1
            self._forward_event(CommandProcessedEvent(head))
            self.__send_limit += len(head.command())
            print(self.__send_limit)

            if self.__processed_tail < len(self.__gcode_queue):
                new_head = self.__gcode_queue[self.__processed_tail]
                self._forward_event(CommandStartedEvent(new_head))
            self.__process_queue()
        except Exception as e:
            logger.log(logger.FATAL, "error {}", e.with_traceback())

    def queue_command(self, command):
        self.__gcode_queue.append(command)
        self._forward_event(CommandQueuedEvent(command))

        if self.__processed_tail == len(self.__gcode_queue) - 1:
            head = self.__gcode_queue[self.__processed_tail]
            self._forward_event(CommandStartedEvent(head))

        self.__process_queue()
        return command.gcode_result

    def __check_queue_empty(self):
        """
        Check if all queued commands are processed and resolve
        waiting Futures
        """
        if self.__processed_tail == len(self.__gcode_queue):
            for f in self.__queue_empty_futures:
                f.set_result(True)

            self.__queue_empty_futures.clear()

    async def wait_queue_empty(self):
        future = asyncio.Future()
        self.__queue_empty_futures.append(future)
        self.__check_queue_empty()
        return await future

    async def ready(self):
        return await self._ready_future

    def _queue_get_status(self):
        self.queue_command(GCodeGenericCommand("?"))

    async def wait_for_idle(self):
        await self.wait_queue_empty()
        self.__status = "Unknown"
        while True:
            if self.__status == "Idle":
                break
            self._queue_get_status()
            await asyncio.sleep(0.5)

    def _process_response(self, response):
        m = re.compile(r"\<?(.*)\>").match(response)
        if m is not None:
            self._process_status(m[1])

        if response == "ok":
            self._confirm_command({"result": "ok", "error_code": 0})

        if response == "Grbl 1.1h ['$' for help]":
            self._process_server_reset()

            settings_command = GCodeGenericCommand("$$")
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.gcode_result

                if not self._ready_future.done():
                    self._ready_future.set_result(True)
                else:
                    # Todo deal with case of second setting responses
                    # for example after pressing the plotter reset button
                    pass

            asyncio.create_task(wait_for_settings(settings_command))

        m = re.compile(r"\$([0-9]+)=([0-9]+\.?[0-9]*).*").match(response)
        if m is not None:
            self.settings[m[1]] = m[2]

        m = re.compile(r"error:(.*)").match(response)
        if m is not None:
            # ToDo set error
            self._confirm_command({"result": "error", "error_code": m[1]})

        m = re.compile(r"E([0-9]*)").match(response)
        if m is not None:
            # ToDo set error
            self._confirm_command({"result": "error", "error_code": m[1]})

    def _process_status(self, status):
        components = status.split("|")
        self.__status = components[0]

    def setStatus(self, status):
        self.__status = status

    async def sleep(self, time: float):
        """
        Wacht even.

        Wacht eerst tot de robotarm alle opdrachten in de wachtrij heeft
        uitgevoerd en klaar is met bewegen. Wacht daarna nog een
        beetje extra.

        Parameters
        ----------
        time : float De extra wachtijd in seconden

        Returns
        -------
        coroutine
            Deze functie geeft een coroutine als resultaat. Daarom
            moet je await gebruiken.

        Example
        -------

        Wacht 1 seconde::

            await robotArm.sleep(1)
        """
        await self.wait_for_idle()
        await asyncio.sleep(time)

    @staticmethod
    def execute_on_devices(devices, script):
        """
        Voer een script uit op meerdere devices.

        Parameters
        ----------
        createArms : callback voor het creeren van RobotArms
            bijvoorbeeld:
                [
                    RobotArm("/dev/cu.usbserial-1420"),
                    RobotArm("/dev/cu.usbserial-1421"),
                ]
        script : script
            Het uit te voeren script.

        Examples
        --------
        Voorbeeld met 2 robotarmen::

            async def do_move_arm(robotArms: RobotArm):
                for arm in arms:
                    robotArm.move(150, 0, 150, 200)

            RobotArm.execute_on_devices(
                [
                    RobotArm("/dev/cu.usbserial-1420"),
                    RobotArm("/dev/cu.usbserial-1421"),
                ],
                do_move_arm)
        """

        async def do_execute():
            try:
                for device in devices:
                    device.start()
                    await device.ready()

                logger.log(logger.INFO, "Executing script")
                await script(devices)
                logger.log(logger.INFO, "Script executed successfully")

                for device in devices:
                    await device.wait_for_idle()
                    device.stop()

                logger.log(logger.INFO, "do_execute ended")

            except TimeoutException:
                pass

            except Exception:
                logger.log(logger.FATAL, "Error {}", traceback.format_exc())

        asyncio.run(do_execute())

    def move_rapid(self, x=None, y=None, z=None, speed=10000):
        return self.queue_command(GCodeMoveRapidCommand(x=x, y=y, z=z, speed=speed))

    def move_linear(self, x=None, y=None, z=None, speed=10000):
        return self.queue_command(GCodeMoveLinearCommand(x=x, y=y, z=z, speed=speed))


class GRBLDriver(GenericDriver):
    """Stelt een op GRBL gebasseerd apparaat voor."""

    def __init__(self, port, *args, **kw):
        """
        Maak een nieuw GRBLDriver object.

        Parameters
        ----------
        port : string
            De naam van de usb port.
        """
        super().__init__(port, *args, **kw)
        self.limit_switch_on = False

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
