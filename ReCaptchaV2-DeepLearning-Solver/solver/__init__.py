"""Solver package init made import-safe for frozen builds.

Avoid importing heavy ML dependencies (torch) at package import time.
Consumers should call `get_captcha_solver()` or import the class inside
runtime code when they actually need it.
"""

CaptchaSolver = None

def get_captcha_solver():
	"""Return the CaptchaSolver class by importing it lazily.

	This function caches the loaded class on the package module so
	subsequent callers (including frozen/extracted runtimes) get a
	stable reference. If the import fails the exception is propagated
	so callers can log diagnostics.
	"""
	global CaptchaSolver
	if CaptchaSolver is not None:
		return CaptchaSolver

	# Import here to avoid import-time dependency on torch/ultralytics
	try:
		from .captcha_solver import CaptchaSolver as _CaptchaSolver
		CaptchaSolver = _CaptchaSolver
		return _CaptchaSolver
	except Exception:
		# Let the caller handle/log the exception with more context.
		raise


__all__ = ["CaptchaSolver", "get_captcha_solver"]
