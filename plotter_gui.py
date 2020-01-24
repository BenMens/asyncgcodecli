import wx
import plotter_driver as pd
import queue
from serial.tools import list_ports
from wxasync import AsyncBind, WxAsyncApp, StartCoroutine
import asyncio
from asyncio.events import get_event_loop

class PlotterStatus(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
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
            dc.SetBrush(wx.Brush("green"))
        else:
            dc.SetBrush(wx.Brush("red"))

        dc.DrawCircle(500, 500, 400)
        del dc

class PlotterCanvas(wx.Control):
    def __init__(self, parent, id):
        wx.Panel.__init__(self, parent, id)
        self.SetBackgroundColour("white")
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.plotter_driver = None

    def on_paint(self, evt):
        if self.plotter_driver != None:
            context = self.plotter_driver.get_initial_context()
            dc = wx.PaintDC(self)
            gc = wx.GraphicsContext.Create(dc)
            size = self.GetSize()
            dc.SetUserScale(size.width / 1000, size.height / 1000)

            context['gc'] = gc
            for command in self.plotter_driver.gcode_queue:
                if (command.confirmed):
                    command.draw(context)

            context['gc'] = None

            del dc
            del gc
    
class PlotterGUIFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.plotter_event_queue = asyncio.Queue()

        self.SetSize(wx.Size(400, 350))
        self.SetMinSize(wx.Size(400, 350))

        self.SetBackgroundColour("Dark Grey")

        self.pnl_top = wx.Panel(self, -1)

        self.plotter_status = PlotterStatus(self.pnl_top, -1)

        self.serial_selection = wx.Choice(self.pnl_top, -1)
        self.Bind(wx.EVT_CHOICE, self.on_serial_selection, self.serial_selection)

        self.serial_selection_refresh = wx.Button(self.pnl_top, -1, label="Refresh")
        self.Bind(wx.EVT_BUTTON, self.on_serial_selection_refresh_button, self.serial_selection_refresh)

        self.pnl = wx.Panel(self, -1)
        
        self.pnl_left = wx.Panel(self.pnl, -1)

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

        self.plotter_canvas = PlotterCanvas(self.pnl, -1)

        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self.pnl_top, wx.SizerFlags().Border(wx.LEFT| wx.TOP, 10))
        frame_sizer.Add(self.pnl,     wx.SizerFlags().Border(wx.LEFT, 10).Proportion(1).Expand())
        self.SetSizer(frame_sizer)        

        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        top_sizer.Add(self.serial_selection,         wx.SizerFlags().Proportion(1).Border(wx.RIGHT, 5).Expand())
        top_sizer.Add(self.serial_selection_refresh, wx.SizerFlags().Border(wx.RIGHT, 5))
        top_sizer.Add(self.plotter_status,           wx.SizerFlags().Border(wx.RIGHT, 5))
        self.pnl_top.SetSizer(top_sizer)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.pnl_left,       wx.SizerFlags().Border(wx.TOP, 20).Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        sizer.Add(self.plotter_canvas, wx.SizerFlags().Shaped().Border(wx.ALL, 20).Proportion(1).Align(wx.ALIGN_TOP|wx.ALIGN_LEFT))
        self.pnl.SetSizer(sizer)

        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(self.home_button,     wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.pen_up_button,   wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.pen_down_button, wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.flush_button,    wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM, 5).Expand())
        sizer1.Add(self.draw_button,     wx.SizerFlags().Align(wx.ALIGN_TOP|wx.ALIGN_LEFT).Border(wx.BOTTOM | wx.TOP, 5).Expand())
        self.pnl_left.SetSizer(sizer1)

        self.eventCount = 0

        self.on_serial_selection_refresh_button(None)

        self.plotter_driver = None

        wx.App.Get().loop.create_task(self.read_plotter_queue())

    def on_serial_selection(self, event):
        if self.plotter_driver != None: 
            self.plotter_driver.stop()

        self.plotter_status.connected = False
        self.plotter_status.Refresh()
        self.plotter_driver = pd.Plotter(event.String, self.plotter_event_queue)
        self.plotter_canvas.plotter_driver = self.plotter_driver
        self.plotter_driver.start()

    def on_serial_selection_refresh_button(self, event):
        self.serial_selection.Clear()
        ports = list_ports.comports()
        for p in ports:
            self.serial_selection.Append(p.device)
        self.serial_selection.SetSelection(wx.NOT_FOUND)

    def on_home_button(self, event):
        self.plotter_driver.home()

    def on_pen_up_button(self, event):
        self.plotter_driver.pen_up()

    def on_pen_down_button(self, event):
        self.plotter_driver.pen_down()

    def on_flush_button(self, event):
        self.plotter_driver.flush_queue()
        
    def on_draw_button(self, event):
        asyncio.create_task(self.perform_draw())

    async def perform_draw(self):
        self.plotter_driver.home()
        self.plotter_driver.pen_up()
        self.plotter_driver.move(10, 10)
        self.plotter_driver.pen_down()
        for i in range(0, 82, 2):
            self.plotter_driver.move(10+i, 10)
            await self.plotter_driver.wait_for_idle()
            self.plotter_driver.move(90,   10+i)
            # await self.plotter_driver.wait_for_idle()
            self.plotter_driver.move(90-i, 90)
            # await self.plotter_driver.wait_for_idle()
            self.plotter_driver.move(10,   90-i)
            # await self.plotter_driver.wait_for_idle()
        self.plotter_driver.pen_up()
        self.plotter_driver.move(0, 0)

    async def read_plotter_queue(self):
        while True:
            event = await self.plotter_event_queue.get()

            if (isinstance(event, pd.PlotterConnectEvent)):
                self.plotter_status.connected = event.connected
                self.plotter_status.Refresh()
                if self.plotter_status.connected:
                    self.plotter_canvas.Refresh()

            if (isinstance(event, pd.CommandProcessedEvent)):
                self.plotter_canvas.Refresh()


if __name__ == '__main__':
    app = WxAsyncApp()
    frm = PlotterGUIFrame(None, title='Plotter')
    frm.Show()
    app.SetTopWindow(frm)
    app.loop.run_until_complete(app.MainLoop())