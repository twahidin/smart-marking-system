from atomic_agents.context import BaseDynamicContextProvider

from sms.memory.db import Database


class RubricNotesProvider(BaseDynamicContextProvider):
    """Injects active learned rubric notes for a subject into the system prompt."""

    def __init__(self, db: Database, subject: str, limit: int = 5):
        super().__init__(title="Rubric Notes (learned)")
        self.db = db
        self.subject = subject
        self.limit = limit

    def get_info(self) -> str:
        rows = self.db.query(
            "SELECT note FROM rubric_notes WHERE subject = ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (self.subject, self.limit),
        )
        if not rows:
            return ""
        return "\n".join(f"- {r['note']}" for r in rows)


class ExemplarCasesProvider(BaseDynamicContextProvider):
    """Injects recent active exemplar cases for a subject as few-shot context."""

    def __init__(self, db: Database, subject: str, limit: int = 5):
        super().__init__(title="Exemplar Cases (learned)")
        self.db = db
        self.subject = subject
        self.limit = limit

    def get_info(self) -> str:
        rows = self.db.query(
            "SELECT topic, q_id, answer_text, awarded, max_score, why_it_matters "
            "FROM exemplar_cases WHERE subject = ? AND status = 'active' ORDER BY id DESC LIMIT ?",
            (self.subject, self.limit),
        )
        if not rows:
            return ""
        return "\n".join(
            f"- [{r['topic']}] {r['answer_text']}: {r['awarded']}/{r['max_score']} ({r['why_it_matters']})"
            for r in rows
        )
