from setuptools import setup, find_packages
import os

here = os.path.abspath(os.path.dirname(__file__))
readme_path = os.path.join(here, "README.md")

# Safe README load (prevents install crash if README.md missing in sdist)
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as fh:
        long_description = fh.read()
else:
    long_description = ""

VERSION = "0.1.5"
DESCRIPTION = "Scrapes online petition data from change.org"

setup(
    name="changedotorgscraper",  # normalized name for PyPI filenames
    version=VERSION,
    author="Charles Alba",
    author_email="alba@wustl.edu",
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,  # include README.md via MANIFEST.in
    install_requires=[
        "requests",
        "beautifulsoup4",
        "lxml",
        "tqdm",
        "pandas",
        "selenium",
        "webdriver-manager",
    ],
    license="MIT",
    keywords=["change.org", "petitions", "web scraping", "selenium", "beautifulsoup"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.8",
)
