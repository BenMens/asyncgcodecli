import serial
import threading
import time
import queue

class PlotterEvent:
    def __init__(self, *args, **kw):
        super(PlotterEvent, self).__init__(*args, **kw)

class PlotterConnectEvent:
    def __init__(self, connected, *args, **kw):
        super(PlotterConnectEvent, self).__init__(*args, **kw)
        self.connected = connected



class PlotterDriver:
    def __init__(self, port, *args, **kw):
        super(PlotterDriver, self).__init__(*args, **kw)
        self.line = f''
        self.port = port
        self.connected = False
        self.queue = queue.Queue()

    def start(self):
        self.thread = threading.Thread(target=self.read_input_thread)
        self.thread.setDaemon(1)
        self.thread.start()

    def read_input_thread(self):
        while (True):

            if (not self.connected):
                print ('Connecting ', end='', flush=True)

            while (not self.connected):
                try:
                    self.serial = serial.Serial(self.port, baudrate=115200)
                    self.connected = True
                    self.queue.put(PlotterConnectEvent(True))
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
                            print(self.line)
                            if self.line == f"Grbl 1.1h ['$' for help]":
                                self.serial.write(b'$$\n')

                            self.line = f''
                        elif b == b'\r':
                            pass
                        elif b == b'\n':
                            pass
                        else:
                            self.line += b.decode("utf-8")
                except Exception as e:
                    self.connected = False
                    self.queue.put(PlotterConnectEvent(False))
                    print ('Connection lost!')




if __name__ == '__main__':

    driver = PlotterDriver("/dev/cu.usbmodem14101")
    driver.start()

    while (True):
        e = driver.queue.get()
        print(e)

    



    
