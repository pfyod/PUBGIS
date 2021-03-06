from distutils.core import setup
from setuptools import find_packages

setup(name='PUBGIS',
      version='0.2.0',
      description='PUBG Location Tracker',
      author='Andrew Zwicky',
      author_email='andrew.zwicky@gmail.com',
      license='GPLv3',
      url='https://github.com/andrewzwicky/PUBGIS',
      packages=['pubgis', 'pubgis.minimap_iterators'],
      package_dir={'pubgis': 'pubgis',
                   'pubgis.minimap_iterators': 'pubgis/minimap_iterators'},
      package_data={'pubgis': ['images/*.jpg', '*.ui'],
                    '': ['LICENSE', 'README.md']},
      python_requires='>=3.6',
      install_requires=['numpy>=1.13.0+mkl',
                        'PyQt5>=5.9',
                        'opencv-python>=3.0',
                        'mss>=3.0.1',
                        'Pillow>=4.2.1',
                        ],
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: X11 Applications :: Qt',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Topic :: Games/Entertainment :: First Person Shooters',
          'Topic :: Multimedia :: Graphics :: Capture :: Screen Capture',
          'Topic :: Multimedia :: Video :: Capture',
          'Topic :: Utilities',
          'Programming Language :: Python :: 3.6',
      ]
      )
