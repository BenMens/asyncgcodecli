# Async gcode client #

This is a async client library to control gcode severs. Currently only
UArm Swift Pro is supported. This library uses asyncio.

## Development ##

In VSCode create a new venv using _Python: Create environment_ and
use _requirements.txt_ as dependencies.

## Installation ##

```bash
pip3 install pyserial

pip3 install https://github.com/BenMens/asyncgcodecli/releases/latest/download/asyncgcodecli-1.0.0-py3-none-any.whl  
```

## Update to latest version ##

```bash
pip3 install --upgrade https://github.com/BenMens/asyncgcodecli/releases/latest/download/asyncgcodecli-1.0.0-py3-none-any.whl  
```

## Documentation ##

[online documentation](https://benmens.github.io/asyncgcodecli/index.html)

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
UArm.execute_on_robotarm('/dev/cu.usbmodem14101', move_script)
```
