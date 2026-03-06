"""Exploration test to dump all raw XHR data from the RMP site.

Run with: pytest tests/test_explore.py -v -s
"""
import json

import pytest

from rmp import RockyMountainPower


def _pretty(data):
    """Pretty print JSON, handling nested JSON strings."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data
    return json.dumps(data, indent=2, default=str)


@pytest.fixture
def api(rmp_credentials):
    instance = RockyMountainPower(
        rmp_credentials["username"],
        rmp_credentials["password"],
    )
    yield instance
    instance.end_session()


class TestExploreXHRs:
    """Dump all raw XHR responses to see what data RMP exposes."""

    def test_dump_login_xhrs(self, api):
        """See everything captured during login."""
        print("\n" + "=" * 70)
        print("  ALL XHR RESPONSES CAPTURED DURING LOGIN")
        print("=" * 70)

        api.login()

        for url, body in sorted(api.utility.xhrs.items()):
            print(f"\n{'─' * 70}")
            print(f"  URL: {url}")
            print(f"{'─' * 70}")
            print(_pretty(body))

        print(f"\n\n  Total XHRs captured during login: {len(api.utility.xhrs)}")

    def test_dump_energy_usage_xhrs(self, api):
        """See everything captured on the energy usage page."""
        print("\n" + "=" * 70)
        print("  ALL XHR RESPONSES ON ENERGY USAGE PAGE")
        print("=" * 70)

        api.login()
        # Clear XHRs from login so we only see energy page ones
        api.utility.xhrs.clear()

        api.utility.goto_energy_usage()
        # Wait extra for any lazy-loaded XHRs
        api.utility._page.wait_for_timeout(5000)

        for url, body in sorted(api.utility.xhrs.items()):
            print(f"\n{'─' * 70}")
            print(f"  URL: {url}")
            print(f"{'─' * 70}")
            print(_pretty(body))

        print(f"\n\n  Total XHRs captured on energy usage page: {len(api.utility.xhrs)}")

    def test_dump_forecast_raw(self, api):
        """Dump the raw forecast/meter type response to debug $0 values."""
        print("\n" + "=" * 70)
        print("  RAW FORECAST / METER TYPE DATA")
        print("=" * 70)

        api.login()
        api.utility.get_forecast()

        meter_url = "https://csapps.rockymountainpower.net/api/energy-usage/getMeterType"
        if meter_url in api.utility.xhrs:
            print(f"\n  getMeterType response:")
            print(_pretty(api.utility.xhrs[meter_url]))
        else:
            print(f"\n  getMeterType URL NOT FOUND in captured XHRs!")
            print(f"  Available URLs containing 'meter' or 'forecast':")
            for url in api.utility.xhrs:
                if "meter" in url.lower() or "forecast" in url.lower() or "projected" in url.lower():
                    print(f"    {url}")

        print(f"\n  Parsed forecast object:")
        print(_pretty(api.utility.forecast))

    def test_explore_all_pages(self, api):
        """Navigate through the site and capture every XHR we can find."""
        print("\n" + "=" * 70)
        print("  FULL SITE EXPLORATION - ALL AVAILABLE DATA")
        print("=" * 70)

        api.login()
        all_xhrs = dict(api.utility.xhrs)

        # Energy usage page
        print("\n  [1] Navigating to energy usage page...")
        api.utility.goto_energy_usage()
        api.utility._page.wait_for_timeout(5000)
        new_xhrs = {k: v for k, v in api.utility.xhrs.items() if k not in all_xhrs}
        print(f"      New XHRs found: {len(new_xhrs)}")
        all_xhrs.update(api.utility.xhrs)

        # Try navigating to other known pages
        pages_to_try = [
            ("My Account", "https://csapps.rockymountainpower.net/secure/my-account"),
            ("Billing & Payment", "https://csapps.rockymountainpower.net/secure/my-account/billing-payment-history"),
            ("Account Settings", "https://csapps.rockymountainpower.net/secure/my-account/manage-account"),
        ]

        for i, (name, url) in enumerate(pages_to_try, start=2):
            print(f"\n  [{i}] Navigating to {name}...")
            try:
                api.utility._page.goto(url)
                api.utility._page.wait_for_timeout(5000)
                new_xhrs = {k: v for k, v in api.utility.xhrs.items() if k not in all_xhrs}
                print(f"      New XHRs found: {len(new_xhrs)}")
                for new_url in sorted(new_xhrs.keys()):
                    print(f"        {new_url}")
                all_xhrs.update(api.utility.xhrs)
            except Exception as e:
                print(f"      Failed: {e}")

        # Summary of all unique API endpoints discovered
        print(f"\n{'=' * 70}")
        print(f"  SUMMARY: ALL UNIQUE API ENDPOINTS DISCOVERED")
        print(f"{'=' * 70}")

        api_urls = {url for url in all_xhrs if "/api/" in url}
        for url in sorted(api_urls):
            body = all_xhrs[url]
            try:
                parsed = json.loads(body)
                keys = list(parsed.keys()) if isinstance(parsed, dict) else f"[list of {len(parsed)}]"
            except (json.JSONDecodeError, TypeError):
                keys = "(not JSON)"
            print(f"\n  {url}")
            print(f"    Top-level keys: {keys}")

        non_api_urls = {url for url in all_xhrs if "/api/" not in url}
        if non_api_urls:
            print(f"\n  Non-API URLs:")
            for url in sorted(non_api_urls):
                print(f"    {url}")

        print(f"\n  Total unique endpoints: {len(all_xhrs)}")
