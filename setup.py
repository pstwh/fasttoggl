from setuptools import find_packages, setup

with open("requirements.txt") as f:
    requirements = [
        line.strip() for line in f if line.strip() and not line.startswith("#")
    ]

setup(
    name="fasttoggl",
    version="1.0.1",
    packages=find_packages(include=["fasttoggl", "fasttoggl.*"]),
    include_package_data=True,
    url="https://github.com/pstwh/fasttoggl",
    keywords="toggl, time tracking",
    python_requires=">=3.10, <4",
    install_requires=requirements,
    entry_points={
        "console_scripts": ["fasttoggl=fasttoggl.cli:main"],
    },
    description="Fast Toggl",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)
