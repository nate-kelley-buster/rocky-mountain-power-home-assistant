# Rocky Mountain Power for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![Tests][tests-shield]][tests]
[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]
[![Community Forum][forum-shield]][forum]

Bring your Rocky Mountain Power billing and usage data into Home Assistant.

This custom integration logs into the Rocky Mountain Power customer portal, pulls your account and usage data, and exposes it in Home Assistant sensors and Energy Dashboard statistics.

## Quick Start

If you want the shortest path to a successful install:

1. Disable Rocky Mountain Power MFA / 2FA.
2. Install this integration with HACS.
3. Restart Home Assistant.
4. Add the integration in `Settings` -> `Devices & Services`.
5. If login fails, verify that the Home Assistant environment can run Playwright + Chromium.
6. Add the imported statistics to the Energy Dashboard.

## What You Get

- Current bill forecast sensors
- Current balance, due date, past due amount, and payment history sensors
- Historical electricity usage and cost data
- Energy Dashboard statistics for consumption and cost
- Multi-account support
- Automatic interval detection for accounts that report hourly or 15-minute data
- Configurable polling interval with a default of 12 hours

## Before You Install

Please read these first. They are the most common setup blockers.

### 1. Multi-factor authentication must be disabled

This integration uses browser automation to sign in to your Rocky Mountain Power account. At the moment, Rocky Mountain Power MFA / 2FA must be turned off for login to succeed.

In the Rocky Mountain Power portal, disable multi-factor authentication before setting up the integration.

### 2. This integration uses Playwright and Chromium

The integration depends on [Playwright](https://playwright.dev/python/) and a Chromium browser installed in the environment where Home Assistant is running.

HACS installs the integration files. It does not guarantee that the Home Assistant runtime can launch Chromium successfully. That part depends on how your Home Assistant instance is hosted.

### 3. Home Assistant OS users should read this carefully

If you are running Home Assistant OS, this integration may require extra work or may not be a good fit for your setup, because Playwright/Chromium support is more constrained there than on a normal Linux or container-based install.

If you are running Home Assistant Container, Home Assistant Core in a Python environment, or another Linux-based install where you control system dependencies, setup is usually much easier.

## Environment Fit

Best fit environments:

- Home Assistant Container on a Linux host you control
- Home Assistant Core in a Python virtual environment
- Other Linux installs where Chromium and required libraries can be installed

Potentially difficult environments:

- Home Assistant OS
- Minimal containers without Chromium dependencies

If Chromium cannot start in your Home Assistant environment, the integration will not be able to log in.

## Installation

### Option 1: Install with HACS

This is the easiest way for most users.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nate-kelley-buster&repository=rocky-mountain-power-home-assistant&category=integration)

### HACS install steps

1. Open HACS in Home Assistant.
2. Open the menu in the top-right corner.
3. Choose `Custom repositories`.
4. Add this repository URL:

```text
https://github.com/nate-kelley-buster/rocky-mountain-power-home-assistant
```

5. Set the category to `Integration`.
6. Click `Add`.
7. Find `Rocky Mountain Power` in HACS and click `Download`.
8. Restart Home Assistant.

### Option 2: Manual install

Use this if you do not use HACS.

### Manual install steps

1. Open your Home Assistant configuration directory.
2. Create a `custom_components` folder if it does not already exist.
3. Inside `custom_components`, create a folder named `rocky_mountain_power`.
4. Copy all files from this repository's `custom_components/rocky_mountain_power` directory into your Home Assistant `custom_components/rocky_mountain_power` directory.
5. Restart Home Assistant.

Your final path should look like this:

```text
<config>/custom_components/rocky_mountain_power/
```

## Playwright / Chromium Setup

After the integration files are installed, the Home Assistant runtime still needs Playwright's browser runtime available.

In a Python-based environment, the usual commands are:

```bash
pip install playwright
python -m playwright install --with-deps chromium
```

If you run Home Assistant in a container, your container image must include the system libraries Chromium needs. If you are using Home Assistant OS, this is the part most likely to require extra work.

Common missing pieces in broken environments include:

- browser dependencies
- font packages
- shared libraries required by Chromium
- sandbox restrictions in highly locked-down containers

## Add the Integration

Once the files are installed and Home Assistant has restarted:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=rocky_mountain_power)

### UI setup steps

1. Open Home Assistant.
2. Go to `Settings` -> `Devices & Services`.
3. Click `Add Integration`.
4. Search for `Rocky Mountain Power`.
5. Enter your Rocky Mountain Power username.
6. Enter your Rocky Mountain Power password.
7. Finish the setup flow.

There is no YAML configuration required.

## First Successful Run

After setup completes successfully, Home Assistant will:

- create Rocky Mountain Power sensors
- start fetching billing and forecast data
- import historical usage and cost statistics for Energy Dashboard use

The integration supports multiple accounts on the same Rocky Mountain Power login.

If you do not see Energy statistics immediately, give Home Assistant a little time to register and populate them.

## Configure Update Frequency

The integration defaults to updating every 12 hours. You can change that later from the integration options.

You can change that in Home Assistant:

1. Go to `Settings` -> `Devices & Services`.
2. Open the `Rocky Mountain Power` integration.
3. Click `Configure`.
4. Choose an update interval.

Available update interval options:

- 1 hour
- 2 hours
- 4 hours
- 6 hours
- 8 hours
- 12 hours
- 24 hours

Lower values fetch new data more often, but they also put more load on the Rocky Mountain Power site.

## Data Imported by the Integration

### Sensors

The integration creates sensors for:

- Current bill forecasted cost
- Current bill forecasted cost low
- Current bill forecasted cost high
- Current balance due
- Payment due date
- Past due amount
- Last payment amount
- Last payment date
- Next statement date

### Energy statistics

The integration also imports historical data into Home Assistant statistics so it can be used in the Energy Dashboard.

This includes:

- monthly usage and cost history
- daily usage and cost history
- interval usage data for supported accounts

Some Rocky Mountain Power accounts expose one-day interval data as hourly readings. Others expose it in 15-minute intervals. This integration automatically detects the interval length from the source data.

## Add It to the Energy Dashboard

To use the imported statistics in Home Assistant Energy:

1. Go to `Settings` -> `Dashboards` -> `Energy`.
2. Under electricity consumption, choose `Add consumption`.
3. Select the Rocky Mountain Power consumption statistic for the account you want.
4. Optionally add the matching cost statistic if you want cost tracking in Energy as well.

## Troubleshooting

### Login fails

Check these first:

- MFA / 2FA is disabled on your Rocky Mountain Power account
- your username and password are correct
- Chromium can actually launch in your Home Assistant environment
- Home Assistant can reach the Rocky Mountain Power site

### Integration installs but no data appears

Possible causes:

- browser automation is blocked by the environment
- Rocky Mountain Power changed part of the portal UI
- the site is temporarily unavailable
- the account is not exposing the expected usage data yet

### Home Assistant says the integration is installed, but setup still fails

That usually means the Python package was installed correctly, but the runtime environment still cannot complete browser automation.

The most common causes are:

- Chromium is missing
- Chromium dependencies are missing
- the environment blocks browser startup
- Rocky Mountain Power login requirements changed
- MFA is still enabled

### Some accounts show hourly data and others show 15-minute data

That is expected. The portal can return different interval sizes for different accounts/meters. The integration detects the interval from the returned timestamps instead of assuming everything is hourly.

### Forecast values may sometimes be zero

This can happen, especially early in a billing cycle or when Rocky Mountain Power has not populated projected cost values yet.

### Re-authentication

If Rocky Mountain Power invalidates your session or credentials change, Home Assistant may prompt you to re-authenticate through the integration UI.

## Known Limitations

- Requires Rocky Mountain Power MFA / 2FA to be disabled
- Requires Playwright and Chromium support in the Home Assistant runtime environment
- Depends on Rocky Mountain Power's website structure and API behavior
- Live portal changes on Rocky Mountain Power's side can temporarily break data retrieval until the integration is updated

## Credits

This project is based on [rocky-mountain-power](https://github.com/jaredhobbs/rocky-mountain-power) by [Jared Hobbs](https://github.com/jaredhobbs). That work provided the foundation that made this Home Assistant integration possible.

## Contributing

Issues and pull requests are welcome.

If you run into a problem, please include:

- your Home Assistant installation type
- how you installed this integration
- any relevant Home Assistant logs
- whether Chromium / Playwright is available in your runtime

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

***

[rmp]: https://www.rockymountainpower.net
[commits-shield]: https://img.shields.io/github/commit-activity/y/nate-kelley-buster/rocky-mountain-power-home-assistant.svg?style=for-the-badge
[commits]: https://github.com/nate-kelley-buster/rocky-mountain-power-home-assistant/commits/main
[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/nate-kelley-buster/rocky-mountain-power-home-assistant.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-nate--kelley--buster-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/nate-kelley-buster/rocky-mountain-power-home-assistant.svg?style=for-the-badge
[releases]: https://github.com/nate-kelley-buster/rocky-mountain-power-home-assistant/releases
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[tests-shield]: https://img.shields.io/github/actions/workflow/status/nate-kelley-buster/rocky-mountain-power-home-assistant/tests.yml?style=for-the-badge&label=tests
[tests]: https://github.com/nate-kelley-buster/rocky-mountain-power-home-assistant/actions/workflows/tests.yml
