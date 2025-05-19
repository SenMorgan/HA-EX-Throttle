> [!WARNING]
> **Work in progress:** This integration is currently under development and may not be fully functional. Please check back later for updates.

<p align="center">
   <img src="https://media3.giphy.com/media/TLeLKUdIc1tvAxb7ab/source.gif" width="400" height="250" />
</p>

# EX-HABridge Integration for Home Assistant

This custom integration allows [Home Assistant](https://www.home-assistant.io/) to monitor and control an [EX-CommandStation](https://dcc-ex.com/ex-commandstation/index.html) — a simple but powerful DCC/DC command station used to run model train layouts.

> [!NOTE]
> I'm a [Home Assistant](https://www.home-assistant.io/) user since 2018 and this is my first custom integration that I have started writing in 2025 for studying purposes and to help others connect the [EX-CommandStation](https://dcc-ex.com/ex-commandstation/index.html) from the innovative [DCC-EX](https://dcc-ex.com/) project with their Home Assistant setup.

## ✅ Planned and Implemented Features

### Core

- [x] Communication with EX-CommandStation over Telnet
- [x] Configuration via UI with connection validation
- [x] EX-CommandStation version validation
- [x] Reconnect logic with backoff (device availability monitoring)

### Switches & Controls

- [x] Tracks power toggle (common for Main and Program tracks)
- [x] Support for loco function commands control (using service calls)
- [x] Multi-locomotive support
- [x] Turnout control
- [ ] Turntable control

### CV Operations

- [x] Write to CV registers via service
- [ ] Read CV registers via service
- [ ] Display CV read results

## Installation

1. Copy `custom_components/ex_habridge` directory to your Home Assistant `custom_components` directory. The path should look like this: `custom_components/ex_habridge/`.
2. Restart Home Assistant.
3. Add the integration using the Home Assistant UI:
   - Go to **Settings** > **Devices & services** > **Add Integration**.
   - Search for *EX-HABridge* and follow the prompts to set it up.

## Disclaimer

This integration is an unofficial, community-developed project and is not affiliated with or officially endorsed by Home Assistant or the DCC-EX project. Use at your own risk.

The software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the author(s) be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.

All trademarks and logos are property of their respective owners.


## Disclaimer

This integration is an unofficial, community-developed project and is not affiliated with or officially endorsed by Home Assistant or the DCC-EX project. Use at your own risk.

The software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the author(s) be liable for any claim, damages, or other liability, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.

All trademarks and logos are property of their respective owners.


## License

Copyright (c) 2025 Arsenii Kuzin (aka Sen Morgan). Licensed under the MIT license, see LICENSE.md
