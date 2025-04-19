# EX‑CommandStation Integration for Home Assistant
This custom integration allows [Home Assistant](https://www.home-assistant.io/) to monitor and control an [EX‑CommandStation](https://dcc-ex.com/ex-commandstation/index.html) — a simple but powerful DCC/DC command station used to run model train layouts.

> [!NOTE]
> I'm a [Home Assistant](https://www.home-assistant.io/) user since 2018 and this is my first custom integration that I have started writing in 2025 for studying purposes and to help others connect the [EX‑CommandStation](https://dcc-ex.com/ex-commandstation/index.html) from the innovative [DCC‑EX](https://dcc-ex.com/) project with their Home Assistant setup.

## ✅ Planned and Implemented Features

### Core
- [x] Communication with EX‑CommandStation over Telnet
- [x] Configuration via UI with connection validation
- [ ] EX‑CommandStation version validation
- [ ] Reconnect logic with backoff (device availability monitoring)

### Switches & Controls
- [x] Tracks power toggle (common for Main and Program tracks)
- [x] Support for loco function commands control (using service calls)
- [ ] Turnout control with auto-registration
- [ ] Multi-locomotive support with auto-registration

### CV Operations
- [x] Write to CV registers via service
- [ ] Read CV registers via service
- [ ] Display CV read results

## Installation
1. Copy `custom_components/excommandstation` directory to your Home Assistant `custom_components` directory. The path should look like this: `custom_components/excommandstation/`.
2. Restart Home Assistant.
3. Add the integration using the Home Assistant UI:
   - Go to **Settings** > **Devices & services** > **Add Integration**.
   - Search for *EX‑CommandStation* and follow the prompts to set it up.

## License
Copyright (c) 2025 Arsenii Kuzin (aka Sen Morgan). Licensed under the MIT license, see LICENSE.md
