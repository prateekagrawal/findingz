"""Compatibility entry point; the UI lives in the installable findingz package."""
import runpy

runpy.run_module("findingz.ui", run_name="__main__")
