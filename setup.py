import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("install.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Check for Windows platform
if not sys.platform.startswith("win"):
    logger.error("This setup script is for Windows only. Use install.sh on Linux.")
    sys.exit(1)

# Configuration
APP_NAME = "quran-player"
INSTALL_DIR = Path(os.getenv("APPDATA")) / APP_NAME
# Use a subdirectory (bin) within the install directory for CLI wrappers instead of WindowsApps.
SCRIPTS_DIR = INSTALL_DIR / "bin"
DESKTOP_DIR = Path.home() / "Desktop"
DESKTOP_FILE = DESKTOP_DIR / "Quran Player.lnk"
VENV_DIR = INSTALL_DIR / "env"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe"

REQUIRED_MODULES = ['winshell', 'win32com']

def check_admin():
    """Check if running with administrator privileges"""
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

def install_requirements():
    """Install required Python modules"""
    try:
        import win32com.client
        import winshell
    except ImportError:
        logger.info("Installing required Windows modules...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "pywin32", "winshell"
        ], check=True)

def copy_application_files():
    """Copy application files with error handling"""
    logger.info("Copying application files...")
    
    files_to_copy = [
        "quran_player.py", "quran_gui.py", "quran_search.py", "arabic_topng.py",
        "requirements.txt", "arabic-font.ttf", "icon.png"
    ]
    
    for file in files_to_copy:
        src = Path(file)
        dest = INSTALL_DIR / file
        try:
            if src.exists():
                shutil.copy(src, dest)
                logger.debug(f"Copied {src} to {dest}")
            else:
                logger.warning(f"Source file not found: {src}")
        except Exception as e:
            logger.error(f"Failed to copy {src}: {str(e)}")
            raise

    for folder in ["quran-text", "audio"]:
        src = Path(folder)
        dest = INSTALL_DIR / folder
        try:
            if src.exists():
                shutil.copytree(src, dest, dirs_exist_ok=True)
                logger.debug(f"Copied directory {src} to {dest}")
            else:
                logger.warning(f"Source directory not found: {src}")
        except Exception as e:
            logger.error(f"Failed to copy directory {src}: {str(e)}")
            raise

def create_virtual_environment():
    """Create Python virtual environment"""
    logger.info("Creating virtual environment...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Virtual environment creation failed: {e.output.decode()}")
        raise

def install_dependencies():
    """Install Python dependencies"""
    logger.info("Installing dependencies...")
    req_file = INSTALL_DIR / "requirements.txt"
    try:
        subprocess.run(
            [str(PYTHON_EXE), "-m", "pip", "install", "-r", str(req_file)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Dependency installation failed: {e.output.decode()}")
        raise

def create_cli_wrappers():
    """Create command-line interface wrappers"""
    logger.info("Creating command-line wrappers...")
    
    # Ensure SCRIPTS_DIR exists
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    wrappers = {
        "quran-daemon.bat": f"@echo off\n\"{PYTHON_EXE}\" \"{INSTALL_DIR / 'quran_player.py'}\" %*",
        "quran-gui.bat": f"@echo off\n\"{PYTHON_EXE}\" \"{INSTALL_DIR / 'quran_gui.py'}\" %*",
        "quran-search.bat": f"@echo off\n\"{PYTHON_EXE}\" \"{INSTALL_DIR / 'quran_search.py'}\" %*",
        "arabic-topng.bat": f"@echo off\n\"{PYTHON_EXE}\" \"{INSTALL_DIR / 'arabic_topng.py'}\" %*",
    }

    for script, content in wrappers.items():
        script_path = SCRIPTS_DIR / script
        try:
            with open(script_path, "w") as f:
                f.write(content)
            logger.debug(f"Created wrapper: {script_path}")
        except Exception as e:
            logger.error(f"Failed to create {script_path}: {str(e)}")
            raise

def create_desktop_shortcut():
    """Create desktop shortcut with error handling"""
    logger.info("Creating desktop shortcut...")
    try:
        from win32com.client import Dispatch
        import winshell
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(str(DESKTOP_FILE))
        shortcut.TargetPath = str(SCRIPTS_DIR / "quran-gui.bat")
        shortcut.IconLocation = str(INSTALL_DIR / "icon.png")
        shortcut.WorkingDirectory = str(INSTALL_DIR)
        shortcut.Description = "Quran Player"
        shortcut.save()
        logger.info(f"Desktop shortcut created: {DESKTOP_FILE}")
        
    except Exception as e:
        logger.error(f"Failed to create desktop shortcut: {str(e)}")
        logger.warning("Desktop shortcut creation failed, but installation will continue")

def main():
    try:
        if not check_admin():
            logger.warning("Some operations might require administrator privileges")
        
        logger.info(f"Installing to: {INSTALL_DIR}")
        
        # Create directories
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

        # Install required Windows modules
        install_requirements()

        # Copy files
        copy_application_files()

        # Set up virtual environment
        create_virtual_environment()
        install_dependencies()

        # Create CLI wrappers
        create_cli_wrappers()

        # Create desktop shortcut
        create_desktop_shortcut()

        logger.info("\nInstallation completed successfully!")
        logger.info(f"Shortcut created on desktop: {DESKTOP_FILE}")
        logger.info("You can now run the Quran Player from the Start menu or desktop shortcut.")

    except Exception as e:
        logger.error(f"\nInstallation failed: {str(e)}")
        logger.info("See install.log for detailed error information")
        sys.exit(1)

if __name__ == "__main__":
    main()
