#!/usr/bin/env python

import wx
import plotter_driver as pd
import queue


class PlotterStatus(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        self.SetBackgroundColour("white")
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.connected = False
        self.SetMaxSize(wx.Size(20,20))
        self.SetMinSize(wx.Size(20,20))

    def on_paint(self, evt):
        dc = wx.PaintDC(self)
        size = self.GetSize()
        dc.SetUserScale(size.width / 1000, size.height / 1000)
        dc.SetPen(wx.Pen("grey", style=wx.TRANSPARENT))
        if (self.connected):
            dc.SetBrush(wx.Brush("green", wx.SOLID))
        else:
            dc.SetBrush(wx.Brush("red", wx.SOLID))

        dc.DrawRectangle(100, 100, 800, 800)
        del dc

class PlotterCanvas(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        self.SetBackgroundColour("white")
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.commands = []
        self.context = {}

    def on_paint(self, evt):
        pass
        dc = wx.PaintDC(self)
        size = self.GetSize()
        dc.SetUserScale(size.width / 100, size.height / 100)

        self.context['dc'] = dc
        for command in self.commands:
            command.draw(self.context)

        self.context['dc'] = None

        del dc
    


class PlotterGUIFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(PlotterGUIFrame, self).__init__(*args, **kw)

        pnl = wx.Panel(self, -1)

        self.plotter_status = PlotterStatus(pnl, -1)

        self.plotter_canvas = PlotterCanvas(pnl, -1)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.plotter_status, wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        sizer.Add(self.plotter_canvas, wx.SizerFlags().Shaped().Proportion(1).Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        pnl.SetSizer(sizer)
        self.eventCount = 0

        self.plotter_driver = pd.PlotterDriver("/dev/cu.usbmodem14101")
        self.plotter_driver.start()


        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.read_plotter_queue, self.timer)
        self.timer.Start(500)

        # self.Bind(wx.EVT_IDLE, self.on_idle)


    def on_idle(self, evt):
        self.eventCount += 1
        print ('idle ' + str(self.eventCount))

    def read_plotter_queue(self, evt):
        while (True):
            try:
                e = self.plotter_driver.event_queue.get(block=False)
                if (isinstance(e, pd.PlotterConnectEvent)):
                    self.plotter_status.connected = e.connected
                    self.plotter_status.Refresh()

                if (isinstance(e, pd.CommandProcessedEvent)):
                    self.plotter_canvas.commands.append(e.command)
                    self.plotter_canvas.Refresh()

                    if isinstance(e.command, pd.GCodeSettingsCommand):
                        print(self.plotter_driver.settings)
                        for i in range(0, 100, 10):
                            self.plotter_driver.queue_command(pd.GCodeMoveCommand(0+i, 0, 50000))
                            self.plotter_driver.queue_command(pd.GCodeMoveCommand(100, 0+i, 50000))
                            self.plotter_driver.queue_command(pd.GCodeMoveCommand(100-i, 100, 50000))
                            self.plotter_driver.queue_command(pd.GCodeMoveCommand(0,  100-i, 50000))


            except queue.Empty:
                break
            

if __name__ == '__main__':
    # When this module is run (not imported) then create the app, the
    # frame, show it, and start the event loop.
    app = wx.App()
    frm = PlotterGUIFrame(None, title='Plotter')
    frm.Show()
    app.MainLoop()
