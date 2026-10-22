"""Compile the obfuscated C sources into native .so modules (run on the VPS)."""
import glob
from setuptools import setup, Extension

modules = [f[:-2] for f in glob.glob("*.c")]
ext_modules = [Extension(m, [m + ".c"]) for m in modules]

setup(
    name="tg-ads-bot-obf",
    ext_modules=ext_modules,
)
