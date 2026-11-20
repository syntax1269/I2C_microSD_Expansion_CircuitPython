Examples
########

Each example is standalone: copy it to the ``CIRCUITPY`` drive as ``code.py``
and reset the board. Edit the I²C pin selection near the top to match your
board.

Simple test
-----------

Probe the module and print STATUS, version and card information.

.. literalinclude:: ../examples/simpletest.py
    :caption: examples/simpletest.py
    :linenos:

Basic read/write
----------------

64 KB round trip with CRC32 verification.

.. literalinclude:: ../examples/basic_readwrite.py
    :caption: examples/basic_readwrite.py
    :linenos:

Append and list
---------------

Append writes, directory listing and file queries.

.. literalinclude:: ../examples/append_and_list.py
    :caption: examples/append_and_list.py
    :linenos:

NeoPixel blit
-------------

Drive a WS2812B strip through the module's bit-bang engine.

.. literalinclude:: ../examples/neopixel_blit.py
    :caption: examples/neopixel_blit.py
    :linenos:

Bit-bang script
---------------

Token programs for timed pin edges.

.. literalinclude:: ../examples/bitbang_script.py
    :caption: examples/bitbang_script.py
    :linenos:

Ring-buffer data logger
-----------------------

500 Hz sampling into a 512-byte ring, drained with ``write_now()``.

.. literalinclude:: ../examples/sensor_ring_logger.py
    :caption: examples/sensor_ring_logger.py
    :linenos:

Persistent config manager
-------------------------

Checked queries, a checksummed config file and a staged update.

.. literalinclude:: ../examples/config_save_load.py
    :caption: examples/config_save_load.py
    :linenos:

Dual-module mirror / failover
-----------------------------

Two modules on one bus, with ``sticky_error`` failover.

.. literalinclude:: ../examples/dual_module_mirror.py
    :caption: examples/dual_module_mirror.py
    :linenos:

Sensor alert with module-side strobe
------------------------------------

CSV logging plus a timed bit-bang script the module plays on PB2.

.. literalinclude:: ../examples/threshold_bitbang_alert.py
    :caption: examples/threshold_bitbang_alert.py
    :linenos:
