from setuptools import setup, find_packages
import os
import shutil

# Package configuration
setup(
    name="quran-player",
    version="1.3.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'pygame>=2.1.3',
        'configparser>=5.3.0',
        'psutil>=5.9.4',
        'portalocker>=2.7.0',
        'arabic-reshaper>=3.0.0',
        'python-bidi>=0.4.2',
        'pillow>=9.4.0'
    ],
    entry_points={
        'console_scripts': [
            'quran-daemon=quran_player:main',
            'quran-gui=quran_gui:main',
            'quran-search=quran_search:main',
            'arabic-topng=arabic_topng:main'
        ]
    },
    author="MOSAID Radouan",
    author_email="mail@mosaid.xyz",
    description="Quran Player with Audio and Visual Verse Display",
    license="GPLv3",
    url="https://github.com/neoMOSAID/quran-player",
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Operating System :: Microsoft :: Windows',
    ],
    data_files=[
        ('config', [
            'default_config.ini',
            'arabic-font.ttf'
        ]),
        ('audio', [os.path.join('audio', f) for f in os.listdir('audio')]),
        ('quran-text', [os.path.join('quran-text', f) for f in os.listdir('quran-text')])
    ]
)

# Windows-specific post-install setup
if os.name == 'nt':
    try:
        # Create startup shortcut
        startup_dir = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Quran Player')
        os.makedirs(startup_dir, exist_ok=True)
        
        # Create desktop shortcut
        desktop_path = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop', 'Quran Player.lnk')
        
        # Create batch file wrapper
        with open(os.path.join(startup_dir, 'quran-gui.bat'), 'w') as f:
            f.write("@echo off\npython -m quran_gui %*")

        print("Windows shortcuts created successfully")
        
    except Exception as e:
        print(f"Windows post-install setup failed: {str(e)}")