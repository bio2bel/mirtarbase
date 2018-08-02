# -*- coding: utf-8 -*-

"""A Bio2BEL package for miRTarBase."""

from .enrich import enrich_mirnas, enrich_rnas  # noqa: F401
from .manager import Manager  # noqa: F401

__version__ = '0.1.3-dev'

__title__ = 'bio2bel_mirtarbase'
__description__ = "A package for converting miRTarBase to BEL"
__url__ = 'https://github.com/bio2bel/mirtarbase'

__author__ = 'Charles Tapley Hoyt and Colin Birkenbihl'
__email__ = 'charles.hoyt@scai.fraunhofer.de'

__license__ = 'MIT License'
__copyright__ = 'Copyright (c) 2017-2018 Charles Tapley Hoyt and Colin Birkenbihl'
