import distutils
from distutils.core import setup, Extension

import sdss3tools
import os

sdss3tools.setup(
    name='ics_sps_webTelemetry',
    description = "Toy SDSS-3 actor.",
    )

