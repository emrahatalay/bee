from setuptools import setup, find_packages

kw = {
    'name': 'bee',
    'version': '0.0.1',
    'author': 'Emrah Atalay',
    'author_email': 'atalay.emrah@gmail.com',
    'description': 'Bee framework',
    'license': 'MIT',
    'install_requires': ['uvloop', 'pyyaml',
                         'SQLAlchemy>=1.3.0', 'redis',
                         'aioredis', 'six', 'gino==1.0.1',
                         'colorama', 'terminaltables',
                         'termcolor', 'rom', 'cerberus',
                         'click', 'msgpack'
                         ],
    'packages': find_packages(),
    'zip_safe': False,
    'entry_points': {
        'console_scripts': [
            'bee_console=bee.console:main',
            'bee_msg=bee.message:main',
            'bee_load=bee.load:main',
        ]
    }
}

setup(**kw)
