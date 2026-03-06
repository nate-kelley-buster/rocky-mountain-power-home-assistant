"""Live integration tests against the real Rocky Mountain Power website.

These tests require valid credentials in a .env file:
    RMP_USERNAME=your_username
    RMP_PASSWORD=your_password

Run with: pytest tests/test_live.py -v -s
"""
import pytest

from rmp import (
    AccountInfo,
    AggregateType,
    BillingInfo,
    CannotConnect,
    CostRead,
    Forecast,
    InvalidAuth,
    RockyMountainPower,
)


def _print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _print_separator():
    print(f"  {'-'*56}")


@pytest.fixture
def api(rmp_credentials):
    """Create and yield an API instance, ensuring cleanup."""
    instance = RockyMountainPower(
        rmp_credentials["username"],
        rmp_credentials["password"],
    )
    yield instance
    instance.end_session()


class TestLiveLogin:
    """Test login against the real RMP site."""

    def test_login_succeeds(self, api):
        _print_header("LOGIN TEST")
        print(f"  Attempting login as: {api._username}")

        api.login()

        assert api.customer_id is not None
        assert api.account is not None
        assert "accountNumber" in api.account

        print(f"  Login successful!")
        print(f"  Customer ID:    {api.customer_id}")
        print(f"  Account Number: {api.account.get('accountNumber', 'N/A')}")
        print(f"  Account Name:   {api.account.get('accountName', 'N/A')}")
        print(f"  Raw account data keys: {list(api.account.keys())}")

    def test_login_populates_account(self, api):
        _print_header("ACCOUNT OBJECT TEST")
        api.login()
        account = api.get_account()

        assert account.uuid is not None
        assert account.utility_account_id is not None
        assert account.customer.uuid is not None

        print(f"  Account UUID:         {account.uuid}")
        print(f"  Utility Account ID:   {account.utility_account_id}")
        print(f"  Customer UUID:        {account.customer.uuid}")

    def test_login_invalid_credentials(self):
        _print_header("INVALID LOGIN TEST")
        print(f"  Attempting login with bad credentials...")
        api = RockyMountainPower("bad_user@example.com", "bad_password")
        with pytest.raises((InvalidAuth, CannotConnect)) as exc_info:
            api.login()
        print(f"  Correctly raised: {exc_info.type.__name__}")
        api.end_session()


class TestLiveMultiAccount:
    """Test multiple account discovery."""

    def test_discover_all_accounts(self, api):
        _print_header("MULTI-ACCOUNT DISCOVERY TEST")
        api.login()

        accounts = api.get_accounts()

        assert isinstance(accounts, list)
        assert len(accounts) >= 1

        print(f"  Found {len(accounts)} account(s):")
        _print_separator()
        print(f"  {'#':<4} {'Account Number':<20} {'Nickname':<25} {'Address':<40} {'Status':<10} {'Type':<12}")
        _print_separator()
        for i, acct in enumerate(accounts, 1):
            assert isinstance(acct, AccountInfo)
            assert acct.account_number is not None
            assert acct.status is not None
            acct_type = "Business" if acct.is_business else "Residential"
            print(f"  {i:<4} {acct.account_number:<20} {acct.nickname:<25} {acct.address:<40} {acct.status:<10} {acct_type:<12}")
        _print_separator()


class TestLiveBilling:
    """Test billing data retrieval."""

    def test_get_billing_info(self, api):
        _print_header("BILLING INFO TEST")
        api.login()
        print(f"  Fetching billing info...")

        billing = api.get_billing_info()

        assert billing is not None
        assert isinstance(billing, BillingInfo)
        assert billing.current_balance >= 0

        print(f"  Account:              {billing.account.uuid}")
        _print_separator()
        print(f"  Current balance:      ${billing.current_balance:.2f}")
        print(f"  Due date:             {billing.due_date}")
        print(f"  Past due amount:      ${billing.past_due_amount:.2f}")
        print(f"  Last payment:         ${billing.last_payment_amount:.2f}")
        print(f"  Last payment date:    {billing.last_payment_date}")
        print(f"  Next statement date:  {billing.next_statement_date}")
        print(f"  Payment program:      {billing.enrolled_payment_program}")
        _print_separator()

        if billing.past_due_amount > 0:
            print(f"  *** PAST DUE: ${billing.past_due_amount:.2f} ***")


class TestLiveForecast:
    """Test forecast retrieval against the real RMP site."""

    def test_get_forecast(self, api):
        _print_header("FORECAST TEST")
        api.login()
        print(f"  Logged in. Navigating to energy usage page...")

        forecasts = api.get_forecast()

        assert isinstance(forecasts, list)
        assert len(forecasts) >= 1

        f = forecasts[0]
        assert isinstance(f, Forecast)
        assert f.forecasted_cost > 0
        assert f.forecasted_cost_low > 0
        assert f.forecasted_cost_high > 0
        assert f.forecasted_cost_low <= f.forecasted_cost <= f.forecasted_cost_high
        assert f.start_date is not None
        assert f.end_date is not None
        assert f.account is not None

        print(f"  Number of forecasts: {len(forecasts)}")
        _print_separator()
        print(f"  CURRENT BILL FORECAST")
        print(f"  Billing period:      {f.start_date} to {f.end_date}")
        print(f"  Current date:        {f.current_date}")
        print(f"  Forecasted cost:     ${f.forecasted_cost:.2f}")
        print(f"  Forecasted low:      ${f.forecasted_cost_low:.2f}")
        print(f"  Forecasted high:     ${f.forecasted_cost_high:.2f}")
        print(f"  Account:             {f.account.uuid}")
        _print_separator()


class TestLiveMonthlyUsage:
    """Test monthly usage data retrieval."""

    def test_get_monthly_cost_reads(self, api):
        _print_header("MONTHLY USAGE TEST")
        api.login()
        print(f"  Fetching monthly cost reads...")

        reads = api.get_cost_reads(AggregateType.MONTH)

        assert isinstance(reads, list)
        assert len(reads) > 0

        for read in reads:
            assert isinstance(read, CostRead)
            assert read.consumption >= 0
            assert read.start_time is not None
            assert read.end_time is not None
            assert read.start_time < read.end_time

        for i in range(len(reads) - 1):
            assert reads[i].start_time <= reads[i + 1].start_time

        total_kwh = sum(r.consumption for r in reads)
        total_cost = sum(r.provided_cost for r in reads)

        print(f"  Total monthly records: {len(reads)}")
        print(f"  Date range:            {reads[0].start_time.date()} to {reads[-1].end_time.date()}")
        print(f"  Total consumption:     {total_kwh:,.1f} kWh")
        print(f"  Total cost:            ${total_cost:,.2f}")
        _print_separator()
        print(f"  {'Month':<20} {'kWh':>10} {'Cost':>10}")
        _print_separator()
        for read in reads:
            month_label = read.start_time.strftime("%b %Y")
            cost_str = f"${read.provided_cost:.2f}" if read.provided_cost else "N/A"
            print(f"  {month_label:<20} {read.consumption:>10.1f} {cost_str:>10}")
        _print_separator()


class TestLiveDailyUsage:
    """Test daily usage data retrieval."""

    def test_get_daily_cost_reads(self, api):
        _print_header("DAILY USAGE TEST (1 month)")
        api.login()
        print(f"  Fetching daily cost reads for past month...")

        reads = api.get_cost_reads(AggregateType.DAY, 1)

        assert isinstance(reads, list)
        assert len(reads) > 0

        for read in reads:
            assert isinstance(read, CostRead)
            assert read.consumption >= 0
            assert read.start_time < read.end_time

        for i in range(len(reads) - 1):
            assert reads[i].start_time <= reads[i + 1].start_time

        total_kwh = sum(r.consumption for r in reads)
        total_cost = sum(r.provided_cost for r in reads)
        avg_daily = total_kwh / len(reads) if reads else 0

        print(f"  Total daily records:   {len(reads)}")
        print(f"  Date range:            {reads[0].start_time.date()} to {reads[-1].end_time.date()}")
        print(f"  Total consumption:     {total_kwh:,.1f} kWh")
        print(f"  Total cost:            ${total_cost:,.2f}")
        print(f"  Avg daily usage:       {avg_daily:.1f} kWh/day")
        _print_separator()
        print(f"  {'Date':<15} {'kWh':>10} {'Cost':>10}")
        _print_separator()
        for read in reads:
            date_label = read.start_time.strftime("%Y-%m-%d")
            cost_str = f"${read.provided_cost:.2f}" if read.provided_cost else "N/A"
            print(f"  {date_label:<15} {read.consumption:>10.2f} {cost_str:>10}")
        _print_separator()


class TestLiveHourlyUsage:
    """Test hourly usage data retrieval."""

    def test_get_hourly_cost_reads(self, api):
        _print_header("HOURLY USAGE TEST (1 day)")
        api.login()
        print(f"  Fetching hourly cost reads for past day...")

        reads = api.get_cost_reads(AggregateType.HOUR, 1)

        assert isinstance(reads, list)
        assert len(reads) > 0

        for read in reads:
            assert isinstance(read, CostRead)
            assert read.consumption >= 0
            assert read.start_time < read.end_time

        for i in range(len(reads) - 1):
            assert reads[i].start_time <= reads[i + 1].start_time

        total_kwh = sum(r.consumption for r in reads)
        peak_read = max(reads, key=lambda r: r.consumption)
        min_read = min(reads, key=lambda r: r.consumption)

        print(f"  Total hourly records:  {len(reads)}")
        print(f"  Date:                  {reads[0].start_time.date()}")
        print(f"  Time range:            {reads[0].start_time.strftime('%H:%M')} to {reads[-1].end_time.strftime('%H:%M')}")
        print(f"  Total consumption:     {total_kwh:.3f} kWh")
        print(f"  Peak hour:             {peak_read.start_time.strftime('%H:%M')} - {peak_read.consumption:.3f} kWh")
        print(f"  Lowest hour:           {min_read.start_time.strftime('%H:%M')} - {min_read.consumption:.3f} kWh")
        _print_separator()
        print(f"  {'Time':<15} {'kWh':>10} {'Bar'}")
        _print_separator()
        max_consumption = peak_read.consumption if peak_read.consumption > 0 else 1
        for read in reads:
            time_label = f"{read.start_time.strftime('%H:%M')}-{read.end_time.strftime('%H:%M')}"
            bar_len = int((read.consumption / max_consumption) * 30)
            bar = "#" * bar_len
            print(f"  {time_label:<15} {read.consumption:>10.3f} {bar}")
        _print_separator()


class TestLiveFullFlow:
    """End-to-end test of the complete data retrieval flow."""

    def test_full_flow(self, api):
        """Login, get forecast, get all types of usage data, then cleanup."""
        _print_header("FULL END-TO-END FLOW TEST")

        # Login
        print(f"\n  [1/7] Logging in as {api._username}...")
        api.login()
        assert api.customer_id is not None
        print(f"        Customer ID: {api.customer_id}")

        # Accounts
        print(f"\n  [2/7] Discovering accounts...")
        accounts = api.get_accounts()
        assert len(accounts) >= 1
        for acct in accounts:
            print(f"        {acct.account_number} - {acct.nickname} ({acct.status})")

        # Billing
        print(f"\n  [3/7] Fetching billing info...")
        billing = api.get_billing_info()
        assert billing is not None
        print(f"        Balance due:         ${billing.current_balance:.2f}")
        print(f"        Due date:            {billing.due_date}")
        print(f"        Last payment:        ${billing.last_payment_amount:.2f} on {billing.last_payment_date}")
        print(f"        Next statement:      {billing.next_statement_date}")

        # Forecast
        print(f"\n  [4/7] Fetching forecast...")
        forecasts = api.get_forecast()
        if forecasts:
            f = forecasts[0]
            print(f"        Forecasted cost:     ${f.forecasted_cost:.2f}")
            print(f"        Range:               ${f.forecasted_cost_low:.2f} - ${f.forecasted_cost_high:.2f}")
            print(f"        Billing period:      {f.start_date} to {f.end_date}")
        else:
            print(f"        No forecast data available for this account")

        # Monthly
        print(f"\n  [5/7] Fetching monthly usage...")
        monthly = api.get_cost_reads(AggregateType.MONTH)
        assert len(monthly) > 0
        monthly_kwh = sum(r.consumption for r in monthly)
        monthly_cost = sum(r.provided_cost for r in monthly)
        print(f"        Records:             {len(monthly)} months")
        print(f"        Date range:          {monthly[0].start_time.date()} to {monthly[-1].end_time.date()}")
        print(f"        Total consumption:   {monthly_kwh:,.1f} kWh")
        print(f"        Total cost:          ${monthly_cost:,.2f}")

        # Daily (1 month)
        print(f"\n  [6/7] Fetching daily usage (1 month)...")
        daily = api.get_cost_reads(AggregateType.DAY, 1)
        assert len(daily) > 0
        daily_kwh = sum(r.consumption for r in daily)
        daily_cost = sum(r.provided_cost for r in daily)
        print(f"        Records:             {len(daily)} days")
        print(f"        Date range:          {daily[0].start_time.date()} to {daily[-1].end_time.date()}")
        print(f"        Total consumption:   {daily_kwh:,.1f} kWh")
        print(f"        Total cost:          ${daily_cost:,.2f}")
        print(f"        Avg daily:           {daily_kwh / len(daily):.1f} kWh/day")

        # Hourly (1 day)
        print(f"\n  [7/7] Fetching hourly usage (1 day)...")
        hourly = api.get_cost_reads(AggregateType.HOUR, 1)
        assert len(hourly) > 0
        hourly_kwh = sum(r.consumption for r in hourly)
        peak = max(hourly, key=lambda r: r.consumption)
        print(f"        Records:             {len(hourly)} hours")
        print(f"        Date:                {hourly[0].start_time.date()}")
        print(f"        Total consumption:   {hourly_kwh:.3f} kWh")
        print(f"        Peak hour:           {peak.start_time.strftime('%H:%M')} ({peak.consumption:.3f} kWh)")

        _print_separator()
        print(f"  ALL 7 STEPS COMPLETED SUCCESSFULLY")
        _print_separator()
