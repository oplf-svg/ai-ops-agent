"""Grades what the agent answered. It is code: no model, no network, no package. See docs/contract.md."""


class Broken(Exception):
    """A recording, a table or a run that cannot be trusted. That is never a miss of the model, so grading stops."""
