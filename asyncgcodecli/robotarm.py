"""Driver for the robot arm."""

__all__ = ["RobotArm"]

import math
from asyncgcodecli.driver import GRBLDriver


class RobotArm(GRBLDriver):
    """Stelt een RobotArm voor."""

    def __init__(self, port, *args, **kw):
        """
        Maak een nieuw RobotArm object.

        Parameters
        ----------
        port : string
            De naam van de usb port.
        """
        super().__init__(port, *args, **kw)
        self.lastXYZ = None

    def convertToXYZtoAngles(self, x: float, y: float, z: float):

        # https://paulbourke.net/geometry/circlesphere/
        l1 = 200
        l2 = 200

        lxy = math.sqrt(math.pow(x, 2) + math.pow(y, 2))

        d = math.sqrt(math.pow(lxy, 2) + math.pow(z, 2))
        a = (math.pow(l1, 2) - math.pow(l2, 2) + math.pow(d, 2)) / (2 * d)
        h = math.sqrt(math.pow(l1, 2) - math.pow(a, 2))

        p2y = a * lxy / d
        p2z = a * z / d

        pjz = p2z + h * lxy / d
        pjy = p2y - h * z / d

        _angle0 = math.atan2(x, y) * 180 / math.pi
        _angle1 = math.atan2(pjy, pjz) * 180 / math.pi
        _angle2 = math.atan2(z - pjz, lxy - pjy) * 180 / math.pi

        return [_angle0, _angle1, _angle2]

    def move_linear(
        self, x: float, y: float, z: float, speed: float = 100, interpolate=True
    ):
        newXYZ = [x, y, z]
        lastMove = None

        if self.lastXYZ is None or interpolate is False:
            angles = self.convertToXYZtoAngles(*newXYZ)
            lastMove = super().move_linear(*angles, speed)
        else:
            len = math.sqrt(math.pow(x, 2) + math.pow(y, 2) + math.pow(z, 2))
            numSteps = min(math.ceil(len * 1000 / speed), math.ceil(len))

            for i in range(0, numSteps + 1, 1):
                iPos = [
                    a + (b - a) * i / numSteps for a, b in zip(self.lastXYZ, newXYZ)
                ]
                # print(iPos)
                angles = self.convertToXYZtoAngles(*iPos)
                # print(angles)
                lastMove = super().move_linear(*angles, speed)

        self.lastXYZ = newXYZ

        return lastMove
