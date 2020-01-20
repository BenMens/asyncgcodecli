#!/usr/bin/env python

import wx
import plotter_driver as pd
import queue

class PlotterStatus(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        # self.SetBackgroundColour("white")
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.connected = False
        self.SetMaxSize(wx.Size(20,20))
        self.SetMinSize(wx.Size(20,20))

    def on_paint(self, evt):
        dc = wx.PaintDC(self)
        size = self.GetSize()
        dc.SetUserScale(size.width / 1000, size.height / 1000)
        dc.SetPen(wx.Pen("black"))
        if (self.connected):
            dc.SetBrush(wx.Brush("green", wx.SOLID))
        else:
            dc.SetBrush(wx.Brush("red", wx.SOLID))

        dc.DrawCircle(500, 500, 400)
        del dc


class PlotterCanvas(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        self.SetBackgroundColour("white")
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.commands = []

    def on_paint(self, evt):
        context = self.plotter_driver.get_initial_context()
        dc = wx.PaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        size = self.GetSize()
        dc.SetUserScale(size.width / 1000, size.height / 1000)

        context['gc'] = gc
        for command in self.commands:
            command.draw(context)

        context['gc'] = None

        del dc
        del gc
    

class PlotterGUIFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(PlotterGUIFrame, self).__init__(*args, **kw)

        self.SetBackgroundColour("Dark Grey")

        pnl = wx.Panel(self, -1)
        pnl.SetBackgroundColour("Dark Grey")

        self.pnl_left = wx.Panel(pnl, -1)
        
        self.plotter_status = PlotterStatus(self.pnl_left, -1)

        self.home_button = wx.Button(self.pnl_left, -1, label="Home")
        self.Bind(wx.EVT_BUTTON, self.on_home_button, self.home_button)

        self.pen_up_button = wx.Button(self.pnl_left, -1, label="Pen up")
        self.Bind(wx.EVT_BUTTON, self.on_pen_up_button, self.pen_up_button)

        self.pen_down_button = wx.Button(self.pnl_left, -1, label="Pen down")
        self.Bind(wx.EVT_BUTTON, self.on_pen_down_button, self.pen_down_button)

        self.flush_button = wx.Button(self.pnl_left, -1, label="Flush queue")
        self.Bind(wx.EVT_BUTTON, self.on_flush_button, self.flush_button)

        self.draw_button = wx.Button(self.pnl_left, -1, label="Draw")
        self.Bind(wx.EVT_BUTTON, self.on_draw_button, self.draw_button)

        self.plotter_canvas = PlotterCanvas(pnl, -1)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.pnl_left, wx.SizerFlags().Border(wx.LEFT | wx.TOP, 20).Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        sizer.Add(self.plotter_canvas, wx.SizerFlags().Shaped().Border(wx.ALL, 20).Proportion(1).Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        pnl.SetSizer(sizer)

        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(self.plotter_status,  wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 20))
        sizer1.Add(self.home_button,     wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.pen_up_button,   wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.pen_down_button, wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.flush_button,    wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.draw_button,    wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM | wx.TOP, 5).Expand())
        self.pnl_left.SetSizer(sizer1)

        self.eventCount = 0

        self.plotter_driver = pd.PlotterDriver("/dev/cu.usbmodem14101")
        self.plotter_canvas.plotter_driver = self.plotter_driver
        self.plotter_driver.start()


        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.read_plotter_queue, self.timer)
        self.timer.Start(500)

        # self.Bind(wx.EVT_IDLE, self.on_idle)

    def on_home_button(self, event):
        self.plotter_driver.home()

    def on_pen_up_button(self, event):
        self.plotter_driver.pen_up()

    def on_pen_down_button(self, event):
        self.plotter_driver.pen_down()

    def on_flush_button(self, event):
        self.plotter_driver.flush_queue()
        
    def on_draw_button(self, event):
        self.plotter_driver.home()
        self.plotter_driver.pen_up()
        self.plotter_driver.move(10, 10)
        self.plotter_driver.pen_down()
        for i in range(0, 80, 1):
            self.plotter_driver.move(10+i, 10)
            self.plotter_driver.move(90,   10+i)
            self.plotter_driver.move(90-i, 90)
            self.plotter_driver.move(10,   90-i)
        self.plotter_driver.pen_up()
        self.plotter_driver.move(0, 0)

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
                    if self.plotter_status.connected:
                        self.plotter_canvas.commands.clear()


                if (isinstance(e, pd.CommandProcessedEvent)):
                    self.plotter_canvas.commands.append(e.command)
                    self.plotter_canvas.Refresh()

                    if isinstance(e.command, pd.GCodeSettingsCommand):
                        print(self.plotter_driver.settings)

            except queue.Empty:
                break
            

if __name__ == '__main__':
    app = wx.App()
    frm = PlotterGUIFrame(None, title='Plotter')
    frm.Show()
    app.MainLoop()
