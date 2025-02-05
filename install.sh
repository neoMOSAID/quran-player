#!/bin/bash
# install-quran-player.sh - User-space installation with CLI wrappers

# Configuration
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo ~$REAL_USER)
INSTALL_DIR="$REAL_HOME/.quran-player"
BIN_DIR="/usr/local/bin"
DESKTOP_FILE="$REAL_HOME/.local/share/applications/quran-player.desktop"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Prevent root execution
if [ "$(id -u)" -eq 0 ] && [ -z "$SUDO_USER" ]; then
    echo -e "${RED}Error: Do not run this script as root!${NC}"
    echo -e "Run as regular user:"
    echo -e "  ./install.sh"
    exit 1
fi

# Install system dependencies
install_dependencies() {
    echo -e "${GREEN}Installing system dependencies (sudo required)...${NC}"

    # Check if user is in audio group
    if ! groups $REAL_USER | grep -q '\baudio\b'; then
        echo -e "${YELLOW}Adding user to audio group...${NC}"
        sudo usermod -aG audio $REAL_USER
    fi

    if command -v apt &> /dev/null; then
        sudo apt install -y \
            python3-venv \
            python3-pip \
            python3-tk \
            feh \
            pulseaudio-utils
    elif command -v pacman &> /dev/null; then
        sudo pacman -Sy --noconfirm \
            python \
            tk \
            feh \
            pulseaudio
    else
        echo -e "${RED}Unsupported package manager. Install dependencies manually.${NC}"
        exit 1
    fi
}

# Copy application files
copy_application_files() {
    echo -e "${GREEN}Copying application files...${NC}"
    mkdir -p "$INSTALL_DIR"
    
    # Core files
    cp -v quran_player.py quran_gui.py quran_search.py arabic_topng.py \
        requirements.txt arabic-font.ttf "$INSTALL_DIR/"

    # Assets
    [ -f icon.png ] && cp -v icon.png "$INSTALL_DIR/"
    [ -d "quran-text" ] && cp -rv quran-text "$INSTALL_DIR/"
    [ -d "audio" ] && cp -rv audio "$INSTALL_DIR/"
}

# Create virtual environment
create_venv() {
    echo -e "${GREEN}Creating Python virtual environment...${NC}"
    python3 -m venv "$INSTALL_DIR/env"
}

# Install Python dependencies
install_python_deps() {
    echo -e "${GREEN}Installing Python packages...${NC}"
    source "$INSTALL_DIR/env/bin/activate"
    pip install -r "$INSTALL_DIR/requirements.txt"
    deactivate
}

create_cli_wrappers() {
    echo -e "${GREEN}Creating command-line interfaces...${NC}"

    # Daemon controller
    sudo tee $BIN_DIR/quran-daemon > /dev/null <<EOF
#!/bin/bash
# Store PID in user-accessible location
PID_FILE="\$HOME/.quran-player/.daemon_pid"
case "\$1" in
    start)
        "$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_player.py" start &
        echo \$! > \$PID_FILE
        ;;
    stop)
        response=\$("$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_player.py" stop )
        if echo "\$response" | grep 'not running' >/dev/null ; then
            echo "not runnin"
            else echo "\$response"
        fi 
        [ -f \$PID_FILE ] && kill -9 \$(cat \$PID_FILE) 2>/dev/null && rm \$PID_FILE
        ;;
    *)
        "$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_player.py" "\$@"
        ;;
esac
EOF

    # GUI launcher with proper process handling
    sudo tee $BIN_DIR/quran-gui > /dev/null <<EOF
#!/bin/bash
# Store GUI PID for easy killing
PID_FILE="\$HOME/.quran-player/.gui_pid"
echo \$\$ > \$PID_FILE
trap "rm \$PID_FILE" EXIT

"$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_gui.py" "\$@"
EOF

    # quran-search
    sudo tee $BIN_DIR/quran-search > /dev/null <<EOF
#!/bin/bash
"$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_search.py" \$@
EOF

    # arabic to png
    sudo tee $BIN_DIR/arabic-topng > /dev/null <<EOF
#!/bin/bash
"$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/arabic_topng.py" \$@
EOF

    sudo chmod +x $BIN_DIR/quran-daemon $BIN_DIR/quran-gui $BIN_DIR/quran-search
}

# Create desktop entry
create_desktop_entry() {
    echo -e "${GREEN}Creating desktop shortcut...${NC}"
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    tee "$DESKTOP_FILE" > /dev/null <<EOF
[Desktop Entry]
Version=1.0
Name=Quran Player
Comment=Interactive Quran Player
Exec=quran-gui
Icon=$INSTALL_DIR/icon.png
Terminal=false
Type=Application
Categories=Audio;Education;
EOF

    update-desktop-database "$(dirname "$DESKTOP_FILE")"
}

# In create_cli_wrappers()
install_manpage() {
    echo -e "${GREEN}Installing manpage...${NC}"
    sudo mkdir -p /usr/local/share/man/man1
    sudo cp quran-daemon.1 /usr/local/share/man/man1/
    sudo gzip /usr/local/share/man/man1/quran-daemon.1
    sudo mandb >/dev/null
}

# Main installation
main_install() {
    #install_dependencies
    copy_application_files
    #create_venv
    #install_python_deps
    create_cli_wrappers
    #create_desktop_entry
    install_manpage
    
    echo -e "\n${GREEN}Installation complete!${NC}"
    echo -e "Usage:"
    echo -e "  Start daemon:                quran-daemon start"
    echo -e "  Control player directly:     quran-daemon [play|pause|next|prev|stop]"
    echo -e "  Control player through gui:  quran-gui [play|pause|next|prev|stop]"
    echo -e "  Launch GUI:                  quran-gui" 
    echo -e "  Stop GUI:                    quran-gui stop"
}

# Uninstall
uninstall() {
    echo -e "${RED}Uninstalling...${NC}"
    # Kill processes using stored PIDs
    [ -f "$REAL_HOME/.quran-player/.daemon_pid" ] && kill -9 $(cat "$REAL_HOME/.quran-player/.daemon_pid") 2>/dev/null
    [ -f "$REAL_HOME/.quran-player/.gui_pid" ] && kill -9 $(cat "$REAL_HOME/.quran-player/.gui_pid") 2>/dev/null
    # Remove all files
    echo "removing $BIN_DIR/quran-daemon"
    sudo rm -f $BIN_DIR/quran-daemon
    echo "removing $BIN_DIR/quran-gui"
    sudo rm -f $BIN_DIR/quran-gui
    echo "removing $BIN_DIR/quran-search"
    sudo rm -f $BIN_DIR/quran-search
    echo "removing $BIN_DIR/arabic-topng"
    sudo rm -f $BIN_DIR/arabic-topng
    echo "removing install dir  $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
    echo "removing desktop file  $DESKTOP_FILE"
    rm -f "$DESKTOP_FILE"
    echo -e "${GREEN}Uninstallation complete!${NC}"
}

# Argument handling
case "$1" in
    --uninstall)
        uninstall
        ;;
    *)
        set -e  # Exit on error
        main_install
        ;;
esac