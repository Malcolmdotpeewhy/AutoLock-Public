# AutoLock (Zero-G Edition)

A professional-grade, autonomous assistant for League of Legends, built with Python and CustomTkinter. AutoLock streamlines the pre-game experience with intelligent automation, a premium UI, and robust client integration.

## Key Features

### 🚀 Advanced Dashboard & Automation
-   **Universal Queue Support**: Ranked Solo/Duo, Flex, Normal Draft, Blind, ARAM, Arena, TFT, and Quickplay.
-   **Specialized Game Modes**:
    -   **Summoner's Rift**: 5-role configuration with Primary, Secondary, and Tertiary picks + Ban per role.
    -   **Arena**: Dedicated 3-slot Priority Pick & Ban system.
    -   **ARAM**: "Sniper" mode with 8 priority targets and auto-swap logic.
-   **Intelligent Automation**:
    -   **Auto-Accept**: Automatically accepts queue pops with randomized human-like delays.
    -   **Auto-Pick & Ban**: Locks in your champions and bans based on your configuration.
    -   **Auto-Hover**: Declare your intent to teammates before banning phase.
    -   **Smart Delays**: Configurable "Lock-In Timing" and "CS Speed" to balance speed (insta-lock) with safety.

### 🔮 Rune Manager & Builder
-   **Local Rune Library**: Create, edit, save, and delete unlimited rune pages locally.
-   **Interactive Builder**: Full visual editor for Primary/Secondary trees and Stat Shards.
-   **One-Click Equip**: Instantly push any saved page to the League Client.
-   **Champion Binding**: Link specific rune pages to specific champions for automatic equipping when picked.

### 🛠️ Tools & System Control
-   **Client Management**:
    -   **Launch Client**: Auto-detects and launches the Riot Client if not running.
    -   **Restart UX**: Fix visual glitches by restarting the LCU interface without closing the game.
-   **Asset Management**: Automatic background downloading of high-quality champion icons and rune assets.
-   **System Monitoring**: Real-time CPU & RAM usage tracking, plus LCU connection status.
-   **Quick Actions**:
    -   **Always on Top**: Toggle overlay mode.
    -   **Clear Cache**: Fix asset issues by resetting local cache.
    -   **Logs**: Easy access to debug logs for troubleshooting.

## Installation

### Method 1: Automatic (Recommended)
1.  Navigate to the `scripts/` folder.
2.  Run `install_and_run.bat`.
    -   This script will automatically check for Python, create a virtual environment (optional), install all required dependencies (`customtkinter`, `requests`, `psutil`, `pillow`, `packaging`), and launch the application.

### Method 2: Manual (For Developers)
1.  Ensure you have Python 3.10+ installed.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the application from the root directory:
    ```bash
    python -m core.main
    ```

## Usage

1.  **Launch the App**: Run via the batch script or Python command.
2.  **Dashboard**:
    -   Select your **Queue Type** (e.g., Ranked Solo/Duo).
    -   Configure your **Picks & Bans** for your role. Click the slot to open the Champion Selector.
    -   Adjust **Automation Settings** (Delays, Auto-Lock, etc.) in the "Automation & Loop" panel.
    -   Toggle the **Power Button** (top left) to enable automation.
3.  **Runes**:
    -   Go to the **Runes & Spells** tab.
    -   Create a new page or select an existing one.
    -   Click **Save** to store locally, or **Equip** to push to the client.
4.  **Tools**:
    -   Use the **Tools & System** tab to fix client issues or manage app settings.

## Configuration

-   **Settings**: Most settings are adjustable directly within the UI (Delays, Toggles, Picks).
-   **config.json**: Advanced users can manually edit `config.json` in the root directory for fine-tuning.
-   **Logs**: Check `debug.log` if you encounter issues.

## Disclaimer

This software is intended for educational purposes and personal use to enhance the user experience. Use at your own risk. The developers are not responsible for any actions taken by Riot Games against your account.
