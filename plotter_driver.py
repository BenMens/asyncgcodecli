import serial
from serial.tools import list_ports
import threading
import time
import queue
import re
import wx
import asyncio
import math
from math import pi

WARN  = 1
FATAL = 2
ERROR = 3
INFO  = 4
TRACE = 5

class PlotterEvent:
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

class PlotterConnectEvent(PlotterEvent):
    def __init__(self, connected, *args, **kw):
        super().__init__(*args, **kw)
        self.connected = connected

class CommandProcessedEvent(PlotterEvent):
    def __init__(self, command, *args, **kw):
        super().__init__(*args, **kw)
        self.command = command

class ResponseReveivedEvent(PlotterEvent):
    def __init__(self, response, *args, **kw):
        super().__init__(*args, **kw)
        self.response = response

class GCodeCommand:
    def __init__(self, expect_ok = True, *args, **kw):
        super().__init__(*args, **kw)
        self.send = False
        self.confirmed = False
        self.confirmed_future = asyncio.Future()
        self.expect_ok = expect_ok

    def command(self):
        return b''

    def draw(self, context):
        pass

class GCodeGenericCommand(GCodeCommand):
    def __init__(self, gcode, *args, **kw):
        super().__init__(*args, **kw)
        self.gcode = str.encode(gcode) + b'\r'

    def command(self):
        return self.gcode


class GCodeMoveCommand(GCodeCommand):
    def __init__(self, x = None, y= None, z = None, speed = None, *args, **kw):
        super().__init__(*args, **kw)
        self.x = x
        self.y = y
        self.z = z
        self.speed = speed

    def command(self):
        result = b'G1'
        if self.x != None:
            result += b' X%.2f' % (self.x)
        if self.y != None:
            result += b' Y%.2f' % (self.y)
        if self.z != None:
            result += b' Z%.2f' % (self.z)
        if self.speed != None:
            result += b' F%.2f' % (self.speed)

        result += b'\r'
        return result

    def draw(self, context):
        spindle = context['spindle']
        if spindle >= 900:
            gc = context['gc']
            x1 = context['x']
            y1 = context['y']
            gc.SetPen(wx.Pen("black", width=3))
            path = gc.CreatePath()
            path.MoveToPoint(x1 * 10, y1 * 10)
            path.AddLineToPoint(self.x * 10, self.y * 10)
            gc.StrokePath(path)

        context['x'] = self.x
        context['y'] = self.y

class GCodeHomeCommand(GCodeCommand):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def command(self):
        return b'$h\r'

    def draw(self, context):
        context['x'] = 0
        context['y'] = 0

class GCodeSetSpindleCommand(GCodeCommand):
    def __init__(self, pos, *args, **kw):
        super().__init__(*args, **kw)
        self.pos = pos

    def command(self):
        return b'M3 S%.2f\r' % (self.pos)

    def draw(self, context):
        context['spindle'] = self.pos


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
        self.serial = serial.Serial(None, baudrate=115200, timeout=1)
        self.setDaemon(1)

    def post_event(self, event):
        self.event_queue.put(event)

    def write(self, gcode):
        self.serial.write(gcode)

    def run(self):
        while (not self.stop):

            print ('Connecting ', end='', flush=True)

            while (not self.serial.is_open):
                if (self.stop): break
                try:
                    self.serial.port = self.port
                    self.serial.open()
                    self.post_event(PlotterConnectEvent(True))
                    print ('')
                    print ('Connected')

                except serial.SerialException  as e:
                    print ('.', end='', flush=True)
                    time.sleep(1)

            response = f''

            while(self.serial.is_open):
                if (self.stop): break
                try:
                    b =  self.serial.read(size=1)
                    if b:
                        if b == b'\n' or b == b'\r':
                            if (len(b) > 0):
                                self.post_event(ResponseReveivedEvent(response))
                                response = f''
                        else:
                            response += b.decode("utf-8")

                except serial.SerialException as e:
                    self.post_event(PlotterConnectEvent(False))
                    self.serial.close()
                    print ('Connection lost!')
                
        if (self.serial.is_open):
            self.serial.close()

        print('thread stopped')



class GenericDriver:
    def __init__(self, port, async_event_queue = None,  advanced_flow_control = False, *args, **kw):
        super().__init__(*args, **kw)
        self.port = port
        self.reset()
        self.advanced_flow_control = advanced_flow_control
        self.serial = None
        self.async_event_queue = async_event_queue
        self.process_serial_events_task = None
        self.queue_empty_futures = []
        self.ready_future = asyncio.Future()

    def reset(self):
        self.connected = False
        self.processed_tail = 0
        self.gcode_queue = []
        self.send_limit = 500
        self.settings = {}

    def flush_queue(self):
        self.gcode_queue = self.gcode_queue[ : self.processed_tail]

    def forward_event(self, event):
        if self.async_event_queue:
            self.async_event_queue.put_nowait(event)

    async def process_serial_events(self):
        while True:
            await asyncio.sleep(0.01)
            while self.serial != None:
                try:
                    event = self.serial.event_queue.get_nowait()
                    if isinstance(event, ResponseReveivedEvent):
                        self.process_response(event.response)

                    self.check_queue_empty()                        

                    self.forward_event(event)

                except queue.Empty:
                    break

    def start(self):
        self.serial = SerialReceiveThread(self.port)
        self.serial.start()

        self.process_serial_events_task = asyncio.create_task(self.process_serial_events())

    def stop(self):
        if self.serial != None:
            self.serial.stop = True
            self.serial = None

        if self.process_serial_events_task != None:
            self.process_serial_events_task.cancel()

    def process_queue(self):
        if not self.serial: return

        for index in range(self.processed_tail, len(self.gcode_queue)):
            head = self.gcode_queue[index]

            if head.send and not self.advanced_flow_control: break
            if head.send and self.advanced_flow_control: continue

            command = head.command()
            command_len = len(command)
            if (command_len > self.send_limit):
                break

            self.serial.write(command)
            self.send_limit -= command_len
            head.send = True
            self.log(TRACE, command.decode("utf-8"))

            if not head.expect_ok:
                self.confirm_command()

    def confirm_command(self):
        head = self.gcode_queue[self.processed_tail]
        head.confirmed = True
        head.confirmed_future.set_result(True)
        self.processed_tail += 1
        self.forward_event(CommandProcessedEvent(head))
        self.send_limit += len(head.command())
        self.process_queue()       

    def process_response(self, response):
        self.log(TRACE, response)

        m= re.compile(r'\<?(.*)\>').match(response)
        if m != None:
            self.process_status(m[1])

        if (response == "ok"):
            self.confirm_command()

    def queue_command(self, command):
         self.gcode_queue.append(command)
         self.process_queue()
         return command

    def check_queue_empty(self):
        if self.processed_tail == len(self.gcode_queue):
            for f in self.queue_empty_futures:
                f.set_result(True)

            self.queue_empty_futures.clear()


    def queue_empty(self):
        future = asyncio.Future()
        self.queue_empty_futures.append(future)
        self.check_queue_empty()
        return future

    def ready(self):
        return self.ready_future

    def get_initial_context(self):
        return {
            'x': 0,
            'y': 0,
            'spindle': 900
        }

    def log(self, level, string):
        print(string)

    def queue_get_status(self):
        self.queue_command(GCodeGenericCommand('?'))

    async def wait_for_idle(self):
        self.status = 'Unknown'
        while True:
            if self.status == 'Idle': break
            self.queue_get_status()
            await asyncio.sleep(0.1)


class GrblDriver(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, advanced_flow_control = True, *args, **kw)

    def reset(self):
        super().reset()
        self.status = 'Unknown'

    def process_response(self, response):
        super().process_response(response)

        if response == f"Grbl 1.1h ['$' for help]":
            settings_command = GCodeGenericCommand('$$')
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.confirmed_future

                self.ready_future.set_result(True)

            asyncio.create_task(wait_for_settings(settings_command))            

        m = re.compile(r'\$([0-9]+)=([0-9]+\.?[0-9]*).*').match(response)
        if m != None:
            self.settings[m[1]] = m[2]

        m= re.compile(r'error:(.*)').match(response)
        if m != None:
            # ToDo set error
            self.confirm_command()

    def process_status(self, status):
        components = status.split('|')
        self.status = components[0]


class MarlinDriver(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, advanced_flow_control = True, *args, **kw)

    def process_status(self, status):
        components = status.split(',')
        self.status = components[0]

    def queue_get_status(self):
        self.queue_command(GCodeGenericCommand('?', expect_ok=False))


class Plotter(GrblDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)

    def pen_up(self):
        self.queue_command(GCodeSetSpindleCommand(400))
        self.queue_command(GCodeWaitCommand(1))

    def pen_down(self):
        self.queue_command(GCodeSetSpindleCommand(900))
        self.queue_command(GCodeWaitCommand(1))

    def move(self, x, y, speed = 10000):
        self.queue_command(GCodeMoveCommand(x = x, y = y, speed = speed))

    def home(self):
        self.queue_command(GCodeHomeCommand())


class UArm(MarlinDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)

    def process_response(self, response):
        super().process_response(response)

        if response == f"@6 N0 V1":
            self.switch = True

        if response == f"@6 N0 V0":
            self.switch = False

        if response == f"@1":
            settings_command = GCodeGenericCommand('$$')
            self.queue_command(settings_command)

            async def wait_for_settings(settings_command):
                await settings_command.confirmed_future

                self.ready_future.set_result(True)

            asyncio.create_task(wait_for_settings(settings_command))         

    def move(self, x, y, z, speed = 100):
        self.queue_command(GCodeMoveCommand(x = x, y = y, z = z, speed = speed))

    def set_wrist(self, angle):
        self.queue_command(GCodeGenericCommand('G2202 N3 V%.2f F1' % angle))

    def set_mode(self, mode):
        self.queue_command(GCodeGenericCommand('M2400 S{}'.format(mode)))


    def set_pump(self, on):
        if on:
            self.queue_command(GCodeGenericCommand('M2231 V1'))
        else:
            self.queue_command(GCodeGenericCommand('M2231 V0'))


if __name__ == '__main__':

    async def main():
        driver = Plotter('/dev/cu.usbmodem14201')
        driver.start()
        await driver.ready()
        await perform_draw(driver)
        await driver.queue_empty()
        driver.stop()
        await asyncio.sleep(2)

    async def perform_draw(driver):
        driver.home()
        driver.pen_up()
        driver.move(10, 10)
        driver.pen_down()
        for i in range(0, 82, 2):
            driver.move(10+i, 10)
            # await driver.wait_for_idle()
            driver.move(90,   10+i)
            # await driver.wait_for_idle()
            driver.move(90-i, 90)
            # await driver.wait_for_idle()
            driver.move(10,   90-i)
            # await driver.wait_for_idle()
        driver.pen_up()
        driver.move(0, 0)

    async def do_arm():
        driver = UArm('/dev/cu.usbmodem14101')
        driver.start()
        await driver.ready()

        driver.set_mode(2)

        driver.move(150, 0, 10, 10)
        driver.move(150, 0, 150, 10)

        for i in range(1, 5):
            driver.move(150, -100, 150, 200)
            driver.move(150, 100, 150, 200)


        await driver.queue_empty()
        # await driver.wait_for_idle()

        driver.set_pump(True)
        for x in range(1, 3):
            await asyncio.sleep(1)
            driver.set_wrist(120)
            await asyncio.sleep(1)
            driver.set_wrist(60)
        driver.set_pump(False)

        await driver.queue_empty()
        driver.stop()
        await asyncio.sleep(2)



    asyncio.run(do_arm())