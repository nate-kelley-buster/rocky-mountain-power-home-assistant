"""Test actually switching accounts via the mat-select dropdown.

Run with: pytest tests/test_account_switch2.py -v -s
"""
import json

import pytest

from rmp import RockyMountainPower


@pytest.fixture
def api(rmp_credentials):
    instance = RockyMountainPower(
        rmp_credentials["username"],
        rmp_credentials["password"],
    )
    yield instance
    instance.end_session()


class TestAccountSwitch:

    def test_switch_account(self, api):
        """Click the account-picker mat-select and switch to the other account."""
        api.login()
        page = api.utility._page

        print(f"\n  Logged in. Active account: {api.account.get('accountNumber')}")
        print(f"  All accounts: {[a.get('accountNickname') for a in api.utility.accounts]}")

        # Find the account picker mat-select
        picker = page.query_selector("wcss-account-picker mat-select")
        if not picker:
            pytest.fail("Could not find account picker")

        current_text = picker.evaluate("el => el.textContent.trim()")
        print(f"  Current picker text: '{current_text}'")

        # Click to open the dropdown
        picker.click()
        page.wait_for_timeout(1000)

        # Get all options
        options = page.query_selector_all("mat-option")
        print(f"  Found {len(options)} options in dropdown:")
        for i, opt in enumerate(options):
            text = opt.evaluate("el => el.textContent.trim()")
            print(f"    [{i}] {text}")

        # Click the one that isn't currently selected
        if len(options) >= 2:
            # Click the second option (index 1) to switch
            for opt in options:
                text = opt.evaluate("el => el.textContent.trim()")
                if "9984" in text:  # Switch to South Jordan
                    print(f"\n  Clicking option: '{text}'")
                    opt.click()
                    break

            page.wait_for_timeout(5000)

            # Check what XHRs were triggered by the switch
            print(f"\n  XHRs after account switch:")
            api_urls = sorted([url for url in api.utility.xhrs if "/api/" in url])
            for url in api_urls:
                endpoint = url.split("/api/")[-1]
                print(f"    {endpoint}")

            # Check the new account info
            acct_info_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
            if acct_info_url in api.utility.xhrs:
                info = json.loads(api.utility.xhrs[acct_info_url])
                acct_info = info.get("getAccountInfoResponseBody", {}).get("accountInfo", {})
                print(f"\n  New account billing info:")
                print(f"    Balance: ${acct_info.get('totalDueAmount', 'N/A')}")
                print(f"    Due date: {acct_info.get('currentDueAmountDueDate', 'N/A')}")

            acct_details_url = "https://csapps.rockymountainpower.net/api/account/getAccountDetails"
            if acct_details_url in api.utility.xhrs:
                details = json.loads(api.utility.xhrs[acct_details_url])
                acct = details.get("getAccountDetailsResponseBody", {}).get("account", {})
                print(f"\n  Switched to account:")
                print(f"    Number: {acct.get('accountNumber', 'N/A')}")
                print(f"    Address: {acct.get('mailingAddressLine1', 'N/A')}")
