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
        super(PlotterEvent, self).__init__(*args, **kw)

class PlotterConnectEvent(PlotterEvent):
    def __init__(self, connected, *args, **kw):
        super(PlotterConnectEvent, self).__init__(*args, **kw)
        self.connected = connected

class CommandProcessedEvent(PlotterEvent):
    def __init__(self, command, *args, **kw):
        super(CommandProcessedEvent, self).__init__(*args, **kw)
        self.command = command


class GCodeCommand:
    def __init__(self, *args, **kw):
        super(GCodeCommand, self).__init__(*args, **kw)
        self.send = False
        self.confirmed = False

    def command(self):
        return b''

    def draw(self, context):
        pass

class GCodeSettingsCommand(GCodeCommand):
    def __init__(self, *args, **kw):
        super(GCodeSettingsCommand, self).__init__(*args, **kw)

    def command(self):
        return b'$$\r'


class GCodeMoveCommand(GCodeCommand):
    def __init__(self, x, y, speed, *args, **kw):
        super(GCodeMoveCommand, self).__init__(*args, **kw)
        self.x = x
        self.y = y
        self.speed = speed

    def command(self):
        return b'G1 X%.2f Y%.2f F%.2f\r' % (self.x, self.y, self.speed)

    def draw(self, context):
        pen_y = context['pen_y']
        if pen_y >= 900:
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
        super(GCodeHomeCommand, self).__init__(*args, **kw)

    def command(self):
        return b'$h\r'

    def draw(self, context):
        context['x'] = 0
        context['y'] = 0

class GCodeMovePenCommand(GCodeCommand):
    def __init__(self, pos, *args, **kw):
        super(GCodeMovePenCommand, self).__init__(*args, **kw)
        self.pos = pos

    def command(self):
        return b'M3 S%.2f\r' % (self.pos)

    def draw(self, context):
        context['pen_y'] = self.pos


class GCodeWaitCommand(GCodeCommand):
    def __init__(self, time, *args, **kw):
        super(GCodeWaitCommand, self).__init__(*args, **kw)
        self.time = time

    def command(self):
        return b'G4 P%.2f\r' % (self.time)

class GCodeStatusRequest(GCodeCommand):
    def __init__(self, *args, **kw):
        super(GCodeStatusRequest, self).__init__(*args, **kw)

    def command(self):
        return b'?\r'

class SerialReceiveThread(threading.Thread):
    def __init__(self, grbl_driver, port, *args, **kw):
        super(SerialReceiveThread, self).__init__(*args, **kw)
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



class GrblDriver:
    def __init__(self, port, *args, **kw):
        super(GrblDriver, self).__init__(*args, **kw)
        self.line = f''
        self.port = port
        self.event_queue = queue.Queue()
        self.processed_commands = []
        self.reset()
        self.serial = SerialReceiveThread(self, port)
        self.status = 'Unknown'

    def reset(self):
        self.connected = False
        self.gcode_queue = []
        self.send_limit = 100
        self.queue_head = 0
        self.settings = {}
        self.processed_commands.clear()

    def flush_queue(self):
        self.gcode_queue = self.gcode_queue[ : self.queue_head]

    def start(self):
        self.serial = SerialReceiveThread(self, self.port)
        self.serial.start()

    def stop(self):
        if self.serial != None:
            self.serial.stop = True
            self.serial = None

    def process_queue(self):        
        while (self.queue_head < len(self.gcode_queue)):
            head = self.gcode_queue[0]
            if head.send: break

            command = head.command()
            command_len = len(command)
            if (command_len > self.send_limit):
                break

            self.serial.write(command)
            self.send_limit -= command_len
            head.send = True
            self.log(TRACE, command.decode("utf-8"))

    def post_event(self, event):
        self.event_queue.put(event)

    def queue_command(self, command):
         self.gcode_queue.append(command)
         self.process_queue()

    def process_status(self, status):
        components = status.split('|')
        self.status = components[0]

    async def wait_for_idle(self):
        self.status = 'Unknown'
        while True:
            if self.status == 'Idle': break
            self.queue_command(GCodeStatusRequest())
            await asyncio.sleep(0.1)

    def process_response(self, response):
        self.log(TRACE, response)

        if response == f"Grbl 1.1h ['$' for help]":
            self.queue_command(GCodeSettingsCommand())

        m = re.compile(r'\$([0-9]+)=([0-9]+\.?[0-9]*).*').match(response)
        if m != None:
            self.settings[m[1]] = m[2]

        m= re.compile(r'\<?(.*)\>').match(response)
        if m != None:
            self.process_status(m[1])

        m= re.compile(r'error:(.*)').match(response)
        if m != None:
            # ToDo set error
            head = self.gcode_queue.pop(0)
            head.confirmed = True
            self.processed_commands.append(head)
            self.event_queue.put(CommandProcessedEvent(head))
            self.send_limit += len(head.command())
            self.process_queue()            

        if (response == "ok"):
            head = self.gcode_queue.pop(0)
            head.confirmed = True
            self.processed_commands.append(head)
            self.event_queue.put(CommandProcessedEvent(head))
            self.send_limit += len(head.command())
            self.process_queue()

    def get_initial_context(self):
        return {
            'x': 0,
            'y': 0,
            'pen_y': 900
        }

    def log(self, level, string):
        print(string)


class PlotterDriver(GrblDriver):
    def __init__(self, port, *args, **kw):
        super(PlotterDriver, self).__init__(port, *args, **kw)\

    def pen_up(self):
        self.queue_command(GCodeMovePenCommand(400))
        self.queue_command(GCodeWaitCommand(1))

    def pen_down(self):
        self.queue_command(GCodeMovePenCommand(900))
        self.queue_command(GCodeWaitCommand(1))

    def move(self, x, y, speed = 10000):
        self.queue_command(GCodeMoveCommand(x, y, speed))

    def home(self):
        self.queue_command(GCodeHomeCommand())


if __name__ == '__main__':
    pass

    # print (serial.__file__)

    # while (True):
    #     ports = list_ports.comports()
    #     for p in ports:
    #         print(p.device)
    #     time.sleep(2)

    # while (True):
    #     e = driver.event_queue.get()
    #     if (isinstance(e, CommandProcessedEvent)):
    #         if isinstance(e.command, GCodeSettingsCommand):
    #             print(driver.settings)
    #             for i in range(0, 100, 1):
    #                 driver.queue_command(GCodeMoveCommand(0+i, 0, 50000))
    #                 driver.queue_command(GCodeMoveCommand(100, 0+i, 50000))
    #                 driver.queue_command(GCodeMoveCommand(100-i,  100, 50000))
    #                 driver.queue_command(GCodeMoveCommand(0,  100-i, 50000))


    



    
