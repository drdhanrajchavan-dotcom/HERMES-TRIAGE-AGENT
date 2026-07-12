import pytest
from pydantic import ValidationError

from clinic_agency.domain.roles import Autonomy, RoleConfig


def test_role_config_rejects_unknown_tool() -> None:
    with pytest.raises(ValidationError, match="unknown tool"):
        RoleConfig(
            name="Unsafe Role",
            mission="Do anything",
            model="gpt-test",
            tools=("shell",),
            autonomy=Autonomy.AUTO,
        )


def test_compliance_role_cannot_be_configured_to_bypass_review() -> None:
    with pytest.raises(ValidationError, match="Compliance must use review autonomy"):
        RoleConfig(
            name="Compliance",
            mission="Review every outbound message",
            model="gpt-test",
            tools=(),
            autonomy=Autonomy.AUTO,
        )


def test_valid_booking_role_is_data_driven() -> None:
    role = RoleConfig(
        name="Booking",
        mission="Offer eligible appointment slots",
        model="gpt-test",
        tools=("calendar.read", "calendar.hold"),
        autonomy=Autonomy.REVIEW,
    )

    assert role.tools == ("calendar.read", "calendar.hold")
