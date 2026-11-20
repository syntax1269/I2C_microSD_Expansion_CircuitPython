# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
#
# SPDX-License-Identifier: MIT

"""Sphinx configuration for the I2C microSD Expansion CircuitPython library."""

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

extensions = [
    "sphinx.ext.autodoc",
    "sphinxcontrib.jquery",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "CircuitPython": ("https://docs.circuitpython.org/en/latest/", None),
    "BusDevice": (
        "https://docs.circuitpython.org/projects/busdevice/en/latest/",
        None,
    ),
}

source_suffix = {".rst": "restructuredtext"}
master_doc = "index"

project = "I2C microSD Expansion CircuitPython Library"
author = "I2C microSD Expansion contributors"
creation_year = "2026"
current_year = str(datetime.datetime.now().year)
year_duration = (
    current_year if current_year == creation_year else creation_year + " - " + current_year
)
copyright = year_duration + " I2C microSD Expansion contributors"

version = "1.0.8"
release = "1.0.8"

language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", ".env", "CODE_OF_CONDUCT.md"]
default_role = "any"
add_function_parentheses = True
pygments_style = "sphinx"
todo_include_todos = False
todo_emit_warnings = True

# Board and bus modules do not exist on a CPython documentation host.
autodoc_mock_imports = [
    "board",
    "busio",
    "micropython",
    "adafruit_bus_device",
]

html_theme = "sphinx_rtd_theme"
htmlhelp_basename = "I2CmicroSDExpansionCircuitPythondoc"

latex_documents = [
    (
        master_doc,
        "I2CmicroSDExpansionCircuitPython.tex",
        "I2C microSD Expansion CircuitPython Library Documentation",
        author,
        "manual",
    )
]

man_pages = [
    (
        master_doc,
        "i2cmicrosdexpansioncircuitpython",
        "I2C microSD Expansion CircuitPython Library Documentation",
        [author],
        1,
    )
]

texinfo_documents = [
    (
        master_doc,
        "I2CmicroSDExpansionCircuitPython",
        "I2C microSD Expansion CircuitPython Library Documentation",
        author,
        "I2CmicroSDExpansionCircuitPython",
        "Host library for the I2C microSD Expansion module.",
        "Miscellaneous",
    )
]
