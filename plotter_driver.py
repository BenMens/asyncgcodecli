import serial
from serial.tools import list_ports
import threading
import time
import queue
import re
import wx
import asyncio

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

class GCodeCommand:
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.send = False
        self.confirmed = False

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
    def __init__(self, grbl_driver, port, *args, **kw):
        super().__init__(*args, **kw)
        self.grbl_driver = grbl_driver
        self.port = port
        self.stop = False
        self.serial = serial.Serial(None, baudrate=115200, timeout=1)
        self.setDaemon(1)

    def write(self, command):
        self.serial.write(command)

    def run(self):
        while (not self.stop):

            print ('Connecting ', end='', flush=True)

            while (not self.serial.is_open):
                if (self.stop): break
                try:
                    self.serial.port = self.port
                    self.serial.open()
                    self.grbl_driver.post_event(PlotterConnectEvent(True))
                    print ('')
                    print ('Connected')

                except serial.SerialException  as e:
                    print ('.', end='', flush=True)
                    time.sleep(1)

            self.line = f''

            while(self.serial.is_open):
                if (self.stop): break
                try:
                    b =  self.serial.read(size=1)
                    if b:
                        if b == b'\r':
                            self.grbl_driver.process_response(self.line)
                            self.line = f''
                        elif b == b'\r':
                            pass
                        elif b == b'\n':
                            pass
                        else:
                            self.line += b.decode("utf-8")

                except serial.SerialException as e:
                    self.grbl_driver.reset()
                    self.grbl_driver.post_event(PlotterConnectEvent(False))
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
        self.serial = SerialReceiveThread(self, port)
        self.async_event_queue = async_event_queue
        self.event_queue = queue.Queue()

    def reset(self):
        self.connected = False
        self.processed_tail = 0
        self.gcode_queue = []
        self.send_limit = 100
        self.settings = {}

    def flush_queue(self):
        self.gcode_queue = self.gcode_queue[ : self.processed_tail]

    def start(self):
        self.serial = SerialReceiveThread(self, self.port)
        self.serial.start()

        asyncio.create_task(self.forward_events())

    async def forward_events(self):
        while True:
            await asyncio.sleep(0.1)
            try:
                event = self.event_queue.get_nowait()
                if self.async_event_queue:
                    self.async_event_queue.put_nowait(event)

            except queue.Empty:
                pass

    def stop(self):
        if self.serial != None:
            self.serial.stop = True
            self.serial = None

    def process_queue(self):        
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

    def process_response(self, response):
        self.log(TRACE, response)

        if (response == "ok"):
            head = self.gcode_queue[self.processed_tail]
            head.confirmed = True
            self.processed_tail += 1
            self.post_event(CommandProcessedEvent(head))
            self.send_limit += len(head.command())
            self.process_queue()       

    def post_event(self, event):
        self.event_queue.put(event)

        # if self.plotter_event_queue != None:
        #     self.plotter_event_queue.put_nowait(event)


    def queue_command(self, command):
         self.gcode_queue.append(command)
         self.process_queue()
         return command

    def get_initial_context(self):
        return {
            'x': 0,
            'y': 0,
            'spindle': 900
        }

    def log(self, level, string):
        print(string)


class GrblDriver(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, advanced_flow_control = True, *args, **kw)

    def reset(self):
        super().reset()
        self.status = 'Unknown'

    def process_status(self, status):
        components = status.split('|')
        self.status = components[0]

    async def wait_for_idle(self):
        self.status = 'Unknown'
        while True:
            if self.status == 'Idle': break
            self.queue_command(GCodeGenericCommand('?'))
            await asyncio.sleep(0.1)

    def process_response(self, response):
        super().process_response(response)

        if response == f"Grbl 1.1h ['$' for help]":
            self.queue_command(GCodeGenericCommand('$$'))

        m = re.compile(r'\$([0-9]+)=([0-9]+\.?[0-9]*).*').match(response)
        if m != None:
            self.settings[m[1]] = m[2]

        m= re.compile(r'\<?(.*)\>').match(response)
        if m != None:
            self.process_status(m[1])

        m= re.compile(r'error:(.*)').match(response)
        if m != None:
            # ToDo set error
            head = self.gcode_queue[self.processed_tail]
            head.confirmed = True
            self.processed_tail += 1
            self.post_event(CommandProcessedEvent(head))
            self.send_limit += len(head.command())
            self.process_queue()           

class MarlinDriver(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)

    async def wait_for_idle(self):
        command = GCodeGenericCommand('M400')
        self.queue_command(command)
        while True:
            if command.confirmed == True: break
            await asyncio.sleep(0.1)

    def process_response(self, response):
        super().process_response(response)

        # m= re.compile(r'error:(.*)').match(response)
        # if m != None:
        #     # ToDo set error
        #     head = self.gcode_queue[self.processed_tail]
        #     head.confirmed = True
        #     self.processed_tail += 1
        #     self.post_event(CommandProcessedEvent(head))
        #     self.send_limit += len(head.command())
        #     self.process_queue()     

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


class uArm(MarlinDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, *args, **kw)

    def move(self, x, y, z, speed = 10000):
        self.queue_command(GCodeMoveCommand(x = x, y = y, z = z, speed = speed))
