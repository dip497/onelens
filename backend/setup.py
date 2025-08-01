from setuptools import setup, find_packages

setup(
    name="backend",
    version="0.1.0",
    packages=find_packages(include=["app", "app.*"]),
    python_requires=">=3.11",
)