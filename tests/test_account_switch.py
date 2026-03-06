"""Explore how to switch between accounts on the RMP site.

Run with: pytest tests/test_account_switch.py -v -s
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


class TestAccountSwitching:

    def test_find_account_switcher(self, api):
        """Find the account selector on the page."""
        api.login()
        page = api.utility._page

        print(f"\n  Active account: {api.account.get('accountNumber')}")
        print(f"  All accounts: {[a['accountNumber'] for a in api.utility.accounts]}")

        # Look for the account nickname text on the page
        for acct in api.utility.accounts:
            nickname = acct.get("accountNickname", "")
            acct_num = acct["accountNumber"]
            print(f"\n  Searching for account: {nickname} ({acct_num})")

            # Try finding by text content
            els = page.query_selector_all(f"text='{nickname}'")
            print(f"    Found {len(els)} elements with text '{nickname}'")
            for el in els:
                tag = el.evaluate("el => el.tagName")
                classes = el.evaluate("el => el.className")
                parent_tag = el.evaluate("el => el.parentElement?.tagName")
                parent_classes = el.evaluate("el => el.parentElement?.className")
                visible = el.is_visible()
                print(f"      <{tag} class='{classes}'> visible={visible} parent=<{parent_tag} class='{parent_classes}'>")

        # Look for common account selector patterns
        print(f"\n  Looking for common selector patterns...")
        selectors_to_try = [
            ("mat-select (Angular Material)", "mat-select"),
            ("account dropdown", "[class*='account']"),
            ("account selector", "[class*='selector']"),
            ("account switcher", "[class*='switcher']"),
            ("account menu", "[class*='account-menu']"),
            ("dropdown toggle", "[class*='dropdown']"),
            ("account list items", "[class*='account-list']"),
            ("navigation account", "nav [class*='account']"),
        ]

        for name, selector in selectors_to_try:
            els = page.query_selector_all(selector)
            visible_els = [el for el in els if el.is_visible()]
            if els:
                print(f"    {name} ({selector}): {len(els)} total, {len(visible_els)} visible")
                for el in visible_els[:3]:
                    tag = el.evaluate("el => el.tagName")
                    classes = el.evaluate("el => el.className")
                    text = el.evaluate("el => el.textContent?.trim()?.substring(0, 80)")
                    print(f"      <{tag} class='{classes}'> text='{text}'")

        # Dump the full page structure looking for account-related elements
        print(f"\n  Scanning all elements for account number text...")
        for acct in api.utility.accounts:
            acct_num = acct["accountNumber"].split("-")[0]  # Just the number part
            els = page.query_selector_all(f"text='{acct_num}'")
            if els:
                print(f"    Found {len(els)} elements containing '{acct_num}'")
                for el in els[:5]:
                    tag = el.evaluate("el => el.tagName")
                    classes = el.evaluate("el => el.className")
                    text = el.evaluate("el => el.textContent?.trim()?.substring(0, 100)")
                    visible = el.is_visible()
                    print(f"      <{tag} class='{classes}'> visible={visible} text='{text}'")

    def test_try_account_switch_via_js(self, api):
        """Try to find account switching mechanism via JavaScript."""
        api.login()
        page = api.utility._page

        # Check localStorage/sessionStorage for account context
        print("\n  Checking storage for account context...")
        local_keys = page.evaluate("Object.keys(localStorage)")
        session_keys = page.evaluate("Object.keys(sessionStorage)")
        print(f"    localStorage keys: {local_keys}")
        print(f"    sessionStorage keys: {session_keys}")

        for key in local_keys:
            val = page.evaluate(f"localStorage.getItem('{key}')")
            if "account" in key.lower() or "25656074" in str(val) or "54802745" in str(val):
                print(f"    localStorage['{key}'] = {str(val)[:200]}")

        for key in session_keys:
            val = page.evaluate(f"sessionStorage.getItem('{key}')")
            if "account" in key.lower() or "25656074" in str(val) or "54802745" in str(val):
                print(f"    sessionStorage['{key}'] = {str(val)[:200]}")

        # Check cookies
        cookies = page.context.cookies()
        for c in cookies:
            if "account" in c["name"].lower() or "25656074" in str(c.get("value", "")) or "54802745" in str(c.get("value", "")):
                print(f"    Cookie '{c['name']}' = {str(c['value'])[:200]}")

        # Look for Angular components related to accounts
        print("\n  Looking for Angular account components...")
        angular_els = page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const matches = [];
            for (const el of all) {
                const tag = el.tagName.toLowerCase();
                if (tag.includes('account') || tag.includes('selector') || tag.includes('switcher')) {
                    matches.push({
                        tag: tag,
                        classes: el.className,
                        text: el.textContent?.trim()?.substring(0, 80),
                        visible: el.offsetParent !== null
                    });
                }
            }
            return matches;
        }""")
        for el in angular_els:
            print(f"    <{el['tag']} class='{el['classes']}'> visible={el['visible']} text='{el['text']}'")
