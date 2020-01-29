# Async gcode client #

This is a async client library to control gcode severs. Currently only
UArm Swift Pro is supported. This library uses asyncio.

## Installation ##

```bash
pip3 install pyserial

pip3 install git+https://github.com/BenMens/asyncgcodecli
```

## Update to latest version ##

```bash
pip3 install --upgrade  git+https://github.com/BenMens/asyncgcodecli
```

## Read documentation ##

```bash
pydoc3 asyncgcodecli.UArm
```

## Example ##

```python
"""Example"""

from asyncgcodecli import UArm


async def move_script(uarm: UArm):
    """Script that moves the robot arm."""
    # set de robot arm mode to 0 (pomp)
    uarm.set_mode(0)

    uarm.move(150, 0, 150, 200)

    for _ in range(1, 5):
        uarm.set_buzzer(2000, 500)
        uarm.set_buzzer(5000, 500)

    # make a nice landing
    uarm.move(150, 0, 20, 200)
    await uarm.sleep(1)
    uarm.move(150, 0, 0, 10)

# Execute move_script on the UArm that is
# connected to /dev/cu.usbmodem14101
UArm.execute('/dev/cu.usbmodem14101', move_script)
```