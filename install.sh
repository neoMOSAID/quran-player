#!/bin/bash
# install-quran-player.sh - Fixed user-home installation

set -e  # Exit on error

# Configuration
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo ~$REAL_USER)
INSTALL_DIR="$REAL_HOME/.quran-player"
SERVICE_FILE="/etc/systemd/system/quran-player.service"
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
    echo -e "  ./install-quran-player.sh"
    exit 1
fi

# Install system dependencies
install_dependencies() {
    echo -e "${GREEN}Installing system dependencies (sudo required)...${NC}"

    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y \
            python3-venv \
            python3-pip \
            python3-tk \
            feh \
            ffmpeg
    elif command -v pacman &> /dev/null; then
        sudo pacman -Sy --noconfirm \
            python \
            tk \
            feh \
            ffmpeg
    else
        echo -e "${RED}Unsupported package manager. Install dependencies manually.${NC}"
        exit 1
    fi
}

# Copy application files
copy_application_files() {
    echo -e "${GREEN}Copying application files...${NC}"

    # Create install directory
    mkdir -p "$INSTALL_DIR"

    # Copy core files
    cp -v quran_player.py quran_gui.py quran_search.py  requirements.txt arabic_topng.py "$INSTALL_DIR/"

    # Copy assets
    cp -rv quran-text "$INSTALL_DIR/"
    [ -f icon.png ] && cp -v icon.png "$INSTALL_DIR/"
    [ -f default_config.ini ] && cp -v default_config.ini "$INSTALL_DIR/"

    # Copy audio samples if exists
    if [ -d "audio" ]; then
        cp -rv audio "$INSTALL_DIR/"
    else
        echo -e "${YELLOW}No audio files found. Place them in $INSTALL_DIR/audio later.${NC}"
    fi
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
}

# Create config directory
create_config() {
    echo -e "${GREEN}Creating configuration...${NC}"
    mkdir -p "$REAL_HOME/.config/quran-player"
    [ -f default_config.ini ] && \
        cp default_config.ini "$REAL_HOME/.config/quran-player/config.ini"

    if [ -n "$SUDO_USER" ]; then
        sudo chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/quran-player"
    fi
}

# Install systemd service
install_service() {
    echo -e "${GREEN}Installing system service...${NC}"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Quran Player Daemon
After=network.target

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/env/bin/python $INSTALL_DIR/quran_player.py start
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable quran-player.service
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
Exec=$INSTALL_DIR/env/bin/python $INSTALL_DIR/quran_gui.py
Icon=$INSTALL_DIR/icon.png
Terminal=false
Type=Application
Categories=Audio;Education;
EOF

    update-desktop-database "$(dirname "$DESKTOP_FILE")"
}

# Create CLI wrapper
create_cli_wrapper() {
    echo -e "${GREEN}Creating command-line interface...${NC}"
    sudo tee /usr/local/bin/quran-player > /dev/null <<EOF
#!/bin/bash
"$INSTALL_DIR/env/bin/python" "$INSTALL_DIR/quran_gui.py" "\$@"
EOF
    sudo chmod +x /usr/local/bin/quran-player
}

# Main installation
main_install() {
    install_dependencies
    copy_application_files
    create_venv
    install_python_deps
    create_config
    install_service
    create_cli_wrapper
    create_desktop_entry
    echo -e "\n${GREEN}Installation complete!${NC}"
    echo -e "Use: quran-player [command] or launch from applications menu"
}

# Uninstall
uninstall() {
    echo -e "${RED}Uninstalling...${NC}"
    sudo systemctl stop quran-player.service || true
    sudo systemctl disable quran-player.service || true
    sudo rm -f "$SERVICE_FILE"
    sudo rm -f /usr/local/bin/quran-player
    rm -rf "$INSTALL_DIR"
    rm -f "$DESKTOP_FILE"
    echo -e "${GREEN}Uninstallation complete!${NC}"
}

# Argument handling
case "$1" in
    --uninstall)
        uninstall
        ;;
    *)
        main_install
        ;;
esac

