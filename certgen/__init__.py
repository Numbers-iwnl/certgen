"""
certgen -- headless core for Gerador de Certificados.

No Qt, no Tkinter. Everything in this package is pure logic (PDF layout,
spreadsheet reading, email sending, persistence) so it can be unit tested
and reused by any UI on top of it.
"""
from .version import __version__

__all__ = ["__version__"]
