from setuptools import find_packages, setup

with open('README.md') as f:
    readme_text = f.read()

with open('LICENSE') as f:
    license_text = f.read()

setup(
    name='ammcon',
    version='0.0.1',
    long_description=readme_text,
    url='http://github.com/ammgws/ammcon',
    packages=find_packages(exclude=('tests', 'docs')),
    license=license_text,
    zip_safe=False,
    install_requires=[
        'crccheck>=0.6',
        'marshmallow',
        'marshmallow_sqlalchemy',
        'pyserial>=3.1.1',
        'SQLAlchemy',
        'sqlalchemy_utils',
        'zmq',
    ],
)
