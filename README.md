# EX‑CommandStation Integration for Home Assistant
This custom integration allows Home Assistant to monitor and control an [EX‑CommandStation](https://dcc-ex.com/ex-commandstation/index.html) — a simple but powerful DCC/DC command station used to run model train layouts.

> [!NOTE]
> I'm a [Home Assistant](https://www.home-assistant.io/) user since 2018 and this is my first custom integration that I have started writing in 2025 for studying purposes and to help others connect the [EX‑CommandStation](https://dcc-ex.com/ex-commandstation/index.html) from the innovative [DCC‑EX](https://dcc-ex.com/) project with their Home Assistant setup.

## Features
- (Planned) Monitor status of the EX‑CommandStation
- (Planned) Control locomotives, turnouts, and routes

## Installation
Clone this repository into your Home Assistant's `custom_components` directory:

```bash
cd config/custom_components
git clone https://github.com/SenMorgan/ha-excommandstation
```

## Configuration
Basic configuration (coming soon):

```yaml
excommandstation:
    host: "x.x.x.x"  # IP address or hostname of the EX‑CommandStation
    port: 2560       # Port number (default is 2560)
```

## License
Copyright (c) 2025 Arsenii Kuzin (aka Sen Morgan). Licensed under the MIT license, see LICENSE.md
