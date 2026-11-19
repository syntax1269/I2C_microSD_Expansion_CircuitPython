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
