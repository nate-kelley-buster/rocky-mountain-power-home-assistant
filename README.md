# Rocky Mountain Power - Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![Tests][tests-shield]][tests]

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

[![Community Forum][forum-shield]][forum]

_Home Assistant custom component to integrate with [Rocky Mountain Power][rmp]._

## About

This integration allows you to monitor your Rocky Mountain Power electricity usage and costs directly in Home Assistant. It scrapes data from the Rocky Mountain Power customer portal using [Playwright](https://playwright.dev/python/) for browser automation.

This project is based on the excellent work by [Jared Hobbs (@jaredhobbs)](https://github.com/jaredhobbs/rocky-mountain-power). The original project uses Selenium for browser automation; this fork replaces Selenium with Playwright, removing the need for a separate Selenium addon.

## Features

- Forecasted electricity cost (standard, low, high)
- Billing info: current balance, due date, past due amount, last payment
- Historical energy consumption and cost statistics
- Integrates with the Home Assistant Energy Dashboard
- Multi-account support
- No separate Selenium addon required — uses Playwright directly

## Prerequisites

> **Important:** This integration uses Playwright for browser automation, which
> requires Chromium to be installed on the system running Home Assistant.

Playwright works on standard Linux (e.g. Debian/Ubuntu-based Docker images) and
macOS. It may **not** work on minimal environments like Home Assistant OS (HAOS)
without additional setup.

After installing the integration, ensure Playwright's Chromium browser is
available:

```bash
pip install playwright
python -m playwright install --with-deps chromium
```

If you run Home Assistant in Docker, you'll need a container image that includes
the system libraries Chromium requires (glibc, NSS, ALSA, etc.).

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nate-kelley-buster&repository=rocky-mountain-power-home-assistant&category=integration)

Click the button above to add this repository via HACS, then click "Install" and restart Home Assistant.

Or, to add manually via HACS:

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner and select "Custom repositories"
3. Add this repository URL and select "Integration" as the category
4. Click "Install"
5. Restart Home Assistant

### Manual

1. Using your tool of choice, open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `rocky_mountain_power`.
4. Download _all_ the files from the `custom_components/rocky_mountain_power/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant.
7. In the HA UI go to "Configuration" -> "Integrations", click "+" and search for "Rocky Mountain Power".

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=rocky_mountain_power)

Before continuing, make sure to **turn off Multi Factor Authentication** on your
Rocky Mountain Power account. You can turn it off from the "Manage account" link on the left side of the page.

1. **Username**: your Rocky Mountain Power username
2. **Password**: your Rocky Mountain Power password

## Sensors

| Sensor | Description |
|--------|-------------|
| Current bill forecasted cost | Projected cost for the current billing period |
| Current bill forecasted cost (low) | Low estimate of projected cost |
| Current bill forecasted cost (high) | High estimate of projected cost |
| Current balance due | Amount currently owed |
| Payment due date | When payment is due |
| Past due amount | Any overdue balance |
| Last payment amount | Most recent payment |
| Last payment date | When last payment was made |
| Next statement date | When the next bill will be generated |

## Energy Dashboard

This integration automatically imports historical energy consumption and cost
data into Home Assistant's long-term statistics. To add it to the Energy
Dashboard:

1. Go to **Settings → Dashboards → Energy**
2. Under **Electricity grid**, click **Add consumption**
3. Select the `Rocky Mountain Power elec <account> energy consumption` statistic
4. Optionally add the matching cost statistic

## Acknowledgments

This project is based on [rocky-mountain-power](https://github.com/jaredhobbs/rocky-mountain-power) by [Jared Hobbs](https://github.com/jaredhobbs). Thank you for the foundational work that made this integration possible.

## Contributions are welcome!

If you want to contribute, feel free to open a pull request or issue.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

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
