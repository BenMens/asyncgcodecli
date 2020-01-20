import serial
import threading
import time
import queue
import re
import wx

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
        self.processed = False

    def command(self):
        return b''

    def draw(self, context):
        pass

class GCodeSettingsCommand(GCodeCommand):
    def __init__(self, *args, **kw):
        super(GCodeSettingsCommand, self).__init__(*args, **kw)

    def command(self):
        return b'$$\n'


class GCodeMoveCommand(GCodeCommand):
    def __init__(self, x, y, speed, *args, **kw):
        super(GCodeMoveCommand, self).__init__(*args, **kw)
        self.x = x
        self.y = y
        self.speed = speed

    def command(self):
        return b'G1 X%.2f Y%.2f F%.2f\n' % (self.x, self.y, self.speed)

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
        return b'$h\n'

    def draw(self, context):
        context['x'] = 0
        context['y'] = 0

class GCodeMovePenCommand(GCodeCommand):
    def __init__(self, pos, *args, **kw):
        super(GCodeMovePenCommand, self).__init__(*args, **kw)
        self.pos = pos

    def command(self):
        return b'M3 S%.2f\n' % (self.pos)

    def draw(self, context):
        context['pen_y'] = self.pos


class GCodeWaitCommand(GCodeCommand):
    def __init__(self, time, *args, **kw):
        super(GCodeWaitCommand, self).__init__(*args, **kw)
        self.time = time

    def command(self):
        return b'G4 P%.2f\n' % (self.time)

class GrblDriver:
    def __init__(self, port, *args, **kw):
        super(GrblDriver, self).__init__(*args, **kw)
        self.line = f''
        self.port = port
        self.event_queue = queue.Queue()
        self.reset()

    def reset(self):
        self.connected = False
        self.gcode_queue = []
        self.send_limit = 100
        self.queue_head = 0
        self.settings = {}

    def flush_queue(self):
        self.gcode_queue = self.gcode_queue[ : self.queue_head]

    def start(self):
        self.thread = threading.Thread(target=self.read_input_thread)
        self.thread.setDaemon(1)
        self.thread.start()

    def process_queue(self):
        
        while (self.queue_head < len(self.gcode_queue)):
            head = self.gcode_queue[self.queue_head]

            command = head.command()
            command_len = len(command)
            if (command_len > self.send_limit):
                break

            self.serial.write(command)
            self.send_limit -= command_len
            self.queue_head += 1
            self.log(TRACE, command.decode("utf-8"))

    def queue_command(self, command):
         self.gcode_queue.append(command)
         self.process_queue()

    def process_response(self, response):
        self.log(TRACE, response)

        if response == f"Grbl 1.1h ['$' for help]":
            self.queue_command(GCodeSettingsCommand())

        m = re.compile(r'\$([0-9]+)=([0-9]+\.?[0-9]*).*').match(response)
        if m != None:
            self.settings[m[1]] = m[2]


        if (response == "ok"):
            head = self.gcode_queue.pop(0)
            head.processed = True
            self.event_queue.put(CommandProcessedEvent(head))
            self.queue_head -= 1
            self.send_limit += len(head.command())
            self.process_queue()


    def read_input_thread(self):
        while (True):

            if (not self.connected):
                print ('Connecting ', end='', flush=True)

            while (not self.connected):
                try:
                    self.serial = serial.Serial(self.port, baudrate=115200)
                    self.connected = True
                    self.event_queue.put(PlotterConnectEvent(True))
                    print ('')
                    print ('Connected')

                except Exception as e:
                    print ('.', end='', flush=True)
                    time.sleep(1)

            self.line = f''

            while(self.connected):
                try:
                    b =  self.serial.read(size=1)
                    if b:
                        if b == b'\r':
                            self.process_response(self.line)
                            self.line = f''
                        elif b == b'\r':
                            pass
                        elif b == b'\n':
                            pass
                        else:
                            self.line += b.decode("utf-8")

                except serial.SerialException as e:
                    self.reset()
                    self.event_queue.put(PlotterConnectEvent(False))
                    print ('Connection lost!')

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
        self.queue_command(GCodeMovePenCommand(400))
        self.queue_command(GCodeWaitCommand(1))

    def move(self, x, y, speed = 1000):
        self.queue_command(GCodeMoveCommand(x, y, speed))

    def home(self):
        self.queue_command(GCodeHomeCommand())


if __name__ == '__main__':

    driver = PlotterDriver("/dev/cu.usbmodem14101")
    driver.start()

    while (True):
        e = driver.event_queue.get()
        if (isinstance(e, CommandProcessedEvent)):
            if isinstance(e.command, GCodeSettingsCommand):
                print(driver.settings)
                for i in range(0, 100, 1):
                    driver.queue_command(GCodeMoveCommand(0+i, 0, 50000))
                    driver.queue_command(GCodeMoveCommand(100, 0+i, 50000))
                    driver.queue_command(GCodeMoveCommand(100-i,  100, 50000))
                    driver.queue_command(GCodeMoveCommand(0,  100-i, 50000))


    



    
