"""Existing workflow fixtures intentionally exercise the explicit local demo.

Restricted access tests override this setting and exercise the same real app.
"""
import os

os.environ["DEMO_ACCESS_MODE"] = "local"
