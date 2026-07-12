from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Case:
    external_event_id: str
    patient_external_id: str
    channel: str
    message: str
    opened_at: datetime
    must_escalate: bool = False
    red_flags: tuple[str, ...] = ()

    @classmethod
    def from_telegram(
        cls,
        update_id: int,
        chat_id: int,
        message: str,
        red_flags: tuple[str, ...] = (),
    ) -> "Case":
        return cls(
            external_event_id=f"telegram:{update_id}",
            patient_external_id=f"telegram:{chat_id}",
            channel="telegram",
            message=message,
            opened_at=datetime.now(UTC),
            must_escalate=bool(red_flags),
            red_flags=red_flags,
        )
