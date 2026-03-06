"""Dump detailed data from the most interesting RMP API endpoints.

Run with: pytest tests/test_explore_detail.py -v -s
"""
import json

import pytest

from rmp import RockyMountainPower


def _pretty(data):
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


class TestExploreDetail:

    def test_dump_interesting_endpoints(self, api):
        """Login, visit pages, and dump the most HA-relevant API responses."""
        api.login()

        interesting_urls = [
            "https://csapps.rockymountainpower.net/api/user/me",
            "https://csapps.rockymountainpower.net/api/self-service/getAccountList",
            "https://csapps.rockymountainpower.net/api/account/getAccountDetails",
            "https://csapps.rockymountainpower.net/api/account/getAccountInfo",
            "https://csapps.rockymountainpower.net/api/account/getMeteredAgreements",
            "https://csapps.rockymountainpower.net/api/account/getBlueSkyAndMeteredAgreements",
            "https://csapps.rockymountainpower.net/api/account/getPendingDraftRequests",
            "https://csapps.rockymountainpower.net/api/account-lookup/initiateAccountLookup",
            "https://csapps.rockymountainpower.net/api/energy-usage/checkHomeEnergyReportEligibility",
            "https://csapps.rockymountainpower.net/api/communication/getPaperlessBillingStatus",
        ]

        # Visit energy usage and billing pages to trigger more XHRs
        api.utility.goto_energy_usage()
        api.utility._page.wait_for_timeout(3000)

        api.utility._page.goto("https://csapps.rockymountainpower.net/secure/my-account/billing-payment-history")
        api.utility._page.wait_for_timeout(5000)

        api.utility._page.goto("https://csapps.rockymountainpower.net/secure/my-account")
        api.utility._page.wait_for_timeout(3000)

        for url in interesting_urls:
            print(f"\n{'=' * 70}")
            print(f"  {url.split('/api/')[-1]}")
            print(f"{'=' * 70}")
            if url in api.utility.xhrs:
                print(_pretty(api.utility.xhrs[url]))
            else:
                print("  (not captured)")

    def test_dump_billing_history(self, api):
        """Dump full billing and payment history."""
        api.login()

        api.utility._page.goto("https://csapps.rockymountainpower.net/secure/my-account/billing-payment-history")
        api.utility._page.wait_for_timeout(5000)

        billing_url = "https://csapps.rockymountainpower.net/api/account/getPaymentAndBillingHistory"
        print(f"\n{'=' * 70}")
        print(f"  BILLING & PAYMENT HISTORY")
        print(f"{'=' * 70}")
        if billing_url in api.utility.xhrs:
            print(_pretty(api.utility.xhrs[billing_url]))
        else:
            print("  (not captured)")
