from setuptools import setup, find_packages
from market_api_app import __version__

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
