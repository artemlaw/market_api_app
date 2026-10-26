from pathlib import Path
import re
from setuptools import setup, find_packages
# from market_api_app import __version__

version_text = (Path(__file__).parent / "market_api_app" / "version.py").read_text(encoding="utf-8")
version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', version_text, re.MULTILINE)
if version_match is None:
    raise RuntimeError("Не удалось определить версию пакета")
__version__ = version_match.group(1)

setup(
    name='market_api_app',
    version=__version__,
    packages=find_packages(),
    install_requires=['requests', 'pandas', 'openpyxl', 'gspread'],
    extras_require={
        "dev": ["pytest",],
    },
    include_package_data=True,
    author='Lubentsov Artem',
    author_email='artem.law@mail.ru',
    description='Integration module MoySklad, YaMarket, Ozon, MegaMarket',
    url='https://github.com/artemlaw/market_api_app',
)
