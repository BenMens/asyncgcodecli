"""Driver for a GRBL based plotter."""


__all__ = [
    'Plotter'
]

import asyncio
import asyncgcodecli.logger as logger
from asyncgcodecli.driver import \
    GenericDriver, \
    GCodeMoveCommand, \
    GCodeSetSpindleCommand, \
    GCodeWaitCommand, \
    GCodeHomeCommand, \
    TimeoutException


class Plotter(GenericDriver):
    def __init__(self, port, *args, **kw):
        super().__init__(port, advanced_flow_control=True, *args, **kw)

    def pen_up(self):
        self.queue_command(GCodeSetSpindleCommand(400))
        return self.queue_command(GCodeWaitCommand(1))

    def pen_down(self):
        self.queue_command(GCodeSetSpindleCommand(900))
        return self.queue_command(GCodeWaitCommand(1))

    def move(self, x, y, speed=10000):
        return self.queue_command(GCodeMoveCommand(x=x, y=y, speed=speed))

    def home(self):
        # self.queue_command(GCodeGenericCommand("$27=2.000"))
        return self.queue_command(GCodeHomeCommand())

    @staticmethod
    def execute_on_plotter(port, script):
        async def do_execute_on_plotter():
            try:
                plotter = Plotter(port)
                plotter.start()
                await plotter.ready()
                logger.log(
                    logger.INFO,
                    "Executing script")
                await script(plotter)
                logger.log(
                    logger.INFO,
                    "Script executed successfully")
                await plotter.wait_queue_empty()
                plotter.stop()
                await asyncio.sleep(2)
            except TimeoutException:
                logger.log(
                    logger.FATAL,
                    "Script not printed because of printer timeout")

        asyncio.run(do_execute_on_plotter())
