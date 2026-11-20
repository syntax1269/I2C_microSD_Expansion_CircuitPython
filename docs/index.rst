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

Diagnostics
-----------

:meth:`~i2c_microsd_module.I2CmicroSD.diagnostics` returns a one-page health
report for troubleshooting. It is safe before ``begin()`` (unreadable fields
show as ``n/a``) and does not change ``last_error``.

.. code-block:: python

   print(microSDexp.diagnostics())

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

Blocking behavior
-----------------

Most high-level methods are **synchronous**: they poll the module's STATUS
frame with a short ``delay()`` until the operation completes or a timeout
expires. The I²C bus stays protocol-responsive, but your sketch/application is
blocked for the duration — plan for watchdogs, real-time loops, cooperative
schedulers and ESP32 tasks.

Timeouts scale up on slow buses and are capped at 120 s by the host.
``begin()`` takes ~1.5 s; ``openWrite()``/``openRead()`` may retry up to six
times; ``write()``/``read()``/``sync()``/``close()`` can each wait tens of
seconds; ``format()`` is destructive and can take minutes (per-wait cap 120 s).
``bitbang*()``/``showNeoPixels()``/``savePINMode()``/``diagnostics()`` only do a
bounded number of I²C transactions.

Non-blocking API
----------------

If your application cannot block, use the submit/poll API: ``begin_open_write``,
``begin_open_read``, ``begin_close``, ``begin_format`` and ``begin_query`` submit
a command without waiting; :meth:`~i2c_microsd_module.I2CmicroSD.poll_op` or
:meth:`~qwiic_sd_expansion_py.QwiicSDExpansion.poll_op` performs one STATUS read
and returns ``ASYNC_BUSY``, ``ASYNC_OK`` or a module error. ``write_now`` and
``read_now`` move only what fits right now (zero/empty means "try again"), and
``committed_bytes`` reports the commit counter. Only one operation may be
pending at a time. No feature flag is needed; the blocking API is unchanged.

Checked queries
---------------

The ``*_checked`` query variants (``exists_checked``, ``file_size_checked``,
``is_directory_checked``) return ``(ok, value)``, so "not found" is distinct
from a failed I²C transaction. ``last_ok`` is shorthand for checking
``last_error``. The original methods are unchanged.

