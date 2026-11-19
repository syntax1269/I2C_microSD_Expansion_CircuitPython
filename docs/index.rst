I2C microSD Expansion — CircuitPython Library
==============================================

Add FAT file storage to any CircuitPython board with just two I²C wires.
The module owns the SD card and filesystem; this library opens files, reads and
writes bytes, lists directories, queries card health and drives the module's
expansion pins and bit-bang engine.

The sketch owns the bus, exactly as ``Wire.begin()`` does on Arduino.

.. code-block:: python

   import board
   import busio
   from i2c_microsd_module import I2CmicroSD

   i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
   microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)

   if not microSDexp.begin():
       raise SystemExit("microSD expansion not found")

   with microSDexp.open("HELLO.TXT", "w") as f:
       f.write(b"HELLO-WORLD")

   with microSDexp.open("HELLO.TXT", "r") as f:
       print(f.read(32))

Requirements
------------

* A CircuitPython board with an ``busio.I2C`` bus.
* An I²C microSD Expansion module with a FAT16/FAT32 card.
* Firmware 18.5.x or newer for files, 18.5.2 for pins/bit-bang and 18.8.0 for
  banner frames and the measured-clock report. Check with
  ``microSDexp.version()``.

Installation
------------

Copy ``lib/i2c_microsd_module/`` from the CircuitPython library bundle onto the
``CIRCUITPY`` drive. On a Blinka host, install from PyPI::

    pip install i2c-microsd-expansion-circuitpython

.. toctree::
    :caption: API Reference
    :maxdepth: 3

    api

.. toctree::
    :caption: Examples

    examples

.. toctree::
    :caption: Links

    Source repository <https://github.com/syntax1269/I2C_microSD_Expansion_CircuitPython>
    Download from GitHub <https://github.com/syntax1269/I2C_microSD_Expansion_CircuitPython/releases/latest>
    CircuitPython library bundle <https://circuitpython.org/libraries>
    CircuitPython reference documentation <https://docs.circuitpython.org>
    PyPI package <https://pypi.org/project/i2c-microsd-expansion-circuitpython/>

Building these docs locally
---------------------------

From the repository root::

    pip install -r docs/requirements.txt
    python -m sphinx -b html -W docs docs/_build/html

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
