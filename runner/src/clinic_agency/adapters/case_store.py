from clinic_agency.domain.cases import Case


class InMemoryCaseStore:
    def __init__(self) -> None:
        self.cases: list[Case] = []
        self._event_ids: set[str] = set()

    def add(self, case: Case) -> bool:
        if case.external_event_id in self._event_ids:
            return False
        self._event_ids.add(case.external_event_id)
        self.cases.append(case)
        return True
