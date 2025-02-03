from setuptools import setup, find_packages

setup(
    name='market_api_app',
    version='0.1.5',
    packages=find_packages(),
    install_requires=['requests', 'pandas', 'openpyxl'],
    extras_require={
        "dev": ["pytest",],
    },
    include_package_data=True,
    author='Lubentsov Artem',
    author_email='artem.law@mail.ru',
    description='Integration module MoySklad, YaMarket, Ozon, MegaMarket',
    url='https://github.com/artemlaw/market_api_app',
)