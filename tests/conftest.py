"""Shared fixtures for Rocky Mountain Power tests."""
import importlib.util
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

# Load rocky_mountain_power.py directly to avoid importing the HA-dependent __init__.py
_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "custom_components",
    "rocky_mountain_power",
    "rocky_mountain_power.py",
)
_spec = importlib.util.spec_from_file_location("rmp", os.path.abspath(_MODULE_PATH))
rmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rmp)
sys.modules["rmp"] = rmp


@pytest.fixture(autouse=True)
def mock_recorder_before_hass(recorder_db_url: str) -> None:
    """Prepare the recorder database before the hass fixture starts.

    Our integration declares ``"dependencies": ["recorder"]``, so the
    recorder component must already be ready when HA processes deps.
    This fixture is a dependency of the ``hass`` fixture provided by
    ``pytest-homeassistant-custom-component`` and ensures the recorder
    database URL is resolved before ``hass`` marks itself as set up.
    """


@pytest.fixture
def rmp_credentials():
    """Return RMP credentials from environment, or skip if not set."""
    username = os.getenv("RMP_USERNAME")
    password = os.getenv("RMP_PASSWORD")
    if not username or not password:
        pytest.skip("RMP_USERNAME and RMP_PASSWORD not set in .env")
    return {"username": username, "password": password}


# --- Mock XHR response data for unit tests ---

USER_ME_RESPONSE = '{"id": "user-123-uuid"}'

ACCOUNT_LIST_RESPONSE = """{
    "getAccountListResponseBody": {
        "accountList": {
            "webAccount": [
                {
                    "accountNumber": "1234567890",
                    "accountName": "Test User"
                }
            ]
        }
    }
}"""

METER_TYPE_RESPONSE = """{
    "getMeterTypeResponseBody": {
        "isAMIMeter": true,
        "startDateForAMIAcctView": "2024-01-15",
        "endDateForAMIAcctView": "2024-02-14",
        "projectedCost": "170",
        "projectedCostHigh": "195",
        "projectedCostLow": "144",
        "noDaysIntoBillingCycle": 9
    }
}"""

MONTHLY_USAGE_RESPONSE = """{
    "getUsageHistoryAndGraphDataV1ResponseBody": {
        "usageHistory": {
            "usageHistoryLineItem": [
                {
                    "usagePeriod": "Oct 2023",
                    "usagePeriodEndDate": "2023-10-12",
                    "invoiceAmount": "$143",
                    "elapsedDays": 29,
                    "kwhUsageQuantity": 1124.0,
                    "missingDataFlag": "N"
                },
                {
                    "usagePeriod": "Nov 2023",
                    "usagePeriodEndDate": "2023-11-10",
                    "invoiceAmount": "$98",
                    "elapsedDays": 29,
                    "kwhUsageQuantity": 756.0,
                    "missingDataFlag": "N"
                }
            ]
        }
    }
}"""

MONTHLY_USAGE_NO_ELAPSED_DAYS = """{
    "getUsageHistoryAndGraphDataV1ResponseBody": {
        "usageHistory": {
            "usageHistoryLineItem": [
                {
                    "usagePeriod": "Oct 2023",
                    "usagePeriodEndDate": "2023-10-12",
                    "invoiceAmount": "$143",
                    "kwhUsageQuantity": 1124.0,
                    "missingDataFlag": "N"
                }
            ]
        }
    }
}"""

DAILY_USAGE_RESPONSE = """{
    "getUsageForDateRangeResponseBody": {
        "dailyUsageList": {
            "usgHistoryLineItem": [
                {
                    "usagePeriodEndDate": "2023-10-24",
                    "dollerAmount": "$5",
                    "numberOfDays": 1,
                    "kwhUsageQuantity": "37.85",
                    "missingDataFlag": "N"
                },
                {
                    "usagePeriodEndDate": "2023-10-25",
                    "dollerAmount": "$7",
                    "numberOfDays": 1,
                    "kwhUsageQuantity": "42.10",
                    "missingDataFlag": "N"
                }
            ]
        }
    }
}"""

HOURLY_USAGE_RESPONSE = """{
    "getIntervalUsageForDateResponseBody": {
        "response": {
            "intervalDataResponse": [
                {
                    "readDate": "2023-11-22",
                    "readTime": "01:00",
                    "usage": "1.682"
                },
                {
                    "readDate": "2023-11-22",
                    "readTime": "02:00",
                    "usage": "1.450"
                },
                {
                    "readDate": "2023-11-22",
                    "readTime": "24:00",
                    "usage": "0.890"
                }
            ]
        }
    }
}"""

EMPTY_MONTHLY_RESPONSE = """{
    "getUsageHistoryAndGraphDataV1ResponseBody": {
        "usageHistory": {
            "usageHistoryLineItem": []
        }
    }
}"""

EMPTY_DAILY_RESPONSE = """{
    "getUsageForDateRangeResponseBody": {
        "dailyUsageList": {
            "usgHistoryLineItem": []
        }
    }
}"""

EMPTY_HOURLY_RESPONSE = """{
    "getIntervalUsageForDateResponseBody": {
        "response": {
            "intervalDataResponse": []
        }
    }
}"""

ACCOUNT_INFO_RESPONSE = """{
    "getAccountInfoResponseBody": {
        "accountInfo": {
            "currentDueAmountDueDate": "2026-03-23",
            "totalDueAmount": 115.59,
            "enrolledPaymentProgram": "APP",
            "paymentsSinceLastStatement": 0.0,
            "currentStatementDate": "2026-02-27",
            "currentEndBalance": 115.59,
            "currentDueAmount": 115.59,
            "currentStatementDueDate": "2026-03-23",
            "nextStatementDate": "2026-03-30",
            "lastPaymentAmount": 119.93,
            "nextStatementDueDate": "2026-04-21",
            "lastPaymentDate": "2026-02-20",
            "pastDueAmount": 0.0
        },
        "operationResult": {
            "returnStatus": 1
        }
    }
}"""

ACCOUNT_INFO_EMPTY_RESPONSE = """{
    "getAccountInfoResponseBody": {
        "accountInfo": {},
        "operationResult": {
            "returnStatus": 1
        }
    }
}"""

MULTI_ACCOUNT_LIST_RESPONSE = """{
    "getAccountListResponseBody": {
        "accountList": {
            "webAccount": [
                {
                    "mailingAddressLine1": "9984 S EDEN POINT CIR SOUTH JORDAN UT 84095",
                    "isBusiness": false,
                    "status": "Active",
                    "accountNumber": "25656074-001 9",
                    "customer": {"idn": 25656074},
                    "accountNickname": "9984 S"
                },
                {
                    "mailingAddressLine1": "1058 W 570 N OREM UT 84057",
                    "isBusiness": false,
                    "status": "Active",
                    "accountNumber": "54802745-001 2",
                    "customer": {"idn": 54802745},
                    "accountNickname": "1058 W 570 N Orem"
                }
            ]
        }
    }
}"""
