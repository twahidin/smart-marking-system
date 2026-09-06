import importlib


class SubjectRouter:
    """Resolves subject names to their prompt configuration modules."""

    KNOWN_SUBJECTS = ("math", "language", "science")

    def resolve(self, subject: str) -> str:
        s = subject.strip().lower()
        if s not in self.KNOWN_SUBJECTS:
            raise KeyError(f"Unknown subject: {subject!r}. Known: {list(self.KNOWN_SUBJECTS)}")
        return s

    def marker_prompt_config(self, subject: str) -> dict:
        module = importlib.import_module(f"sms.subjects.{self.resolve(subject)}.prompt")
        return {
            "background": module.MARKER_BACKGROUND,
            "steps": module.MARKER_STEPS,
            "output_instructions": module.MARKER_OUTPUT_INSTRUCTIONS,
            "reviewer_background": module.REVIEWER_BACKGROUND,
            "reviewer_steps": module.REVIEWER_STEPS,
            "reviewer_output_instructions": module.REVIEWER_OUTPUT_INSTRUCTIONS,
        }
