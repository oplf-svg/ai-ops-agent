"""Three baselines for failures. None of them uses a model. A score says little without something beside it."""

import collections
import json
import math
import re

from grader.fields import NONE

_WORD = re.compile("[a-z]{3,}")
# What somebody looks at who has little time.
LOUD = ("warning", "error")


def words(text):
    return frozenset(_WORD.findall(text.lower()))


def _said(line):
    """What was written, and the first line of the error that came with it."""
    try:
        data = json.loads(line)
    except ValueError:
        return line
    if not isinstance(data, dict):
        return line
    return f"{data.get('Message', '')}\n{str(data.get('Exception', '')).partition(chr(10))[0]}"


def heard(recording):
    """The words of the loud lines, as they were written."""
    return words("\n".join(_said(text) for id, text in recording.raw.items() if recording.by_id[id].get("level") in LOUD))


class Search:
    """A search for words. It knows the sentences of the causes and the lines of the log, and nothing else."""

    def __init__(self, sentences):
        self._sentences = {cause: words(sentence) for cause, sentence in sentences.items()}
        often = collections.Counter(word for sentence in self._sentences.values() for word in sentence)
        # A word that stands in every sentence says nothing, and one that stands in a single one says most.
        self._weight = {word: math.log(len(self._sentences) / times) for word, times in often.items()}

    def _weigh(self, some):
        # The same whatever the order is, so that chance decides nothing.
        return math.fsum(self._weight[word] for word in some)

    def name(self, recording):
        """The cause of whose sentence the largest share was heard, the first of those that are alike. "none" if nothing was."""
        there = heard(recording)
        best, most = NONE, 0.0
        for cause, sentence in self._sentences.items():
            whole = self._weigh(sentence)
            share = self._weigh(sentence & there) / whole if whole else 0.0
            if share > most:
                best, most = cause, share
        return best


def by_table(table, recording):
    """The only cause that could be shown, if somebody showed all that there is."""
    possible = table.possible(recording)
    return possible.pop() if len(possible) == 1 else NONE


def compare(table, failures):
    """How many failures each of them gets right: of those whose cause can be known, and of the others."""
    search = Search(table.sentences)
    ways = {'always "I don\'t know"': lambda recording: NONE, "a search for words": search.name, "the table itself": lambda recording: by_table(table, recording)}
    return {way: tuple(sum(name(recording) == case.truth for case, recording in failures if case.knowable is known) for known in (True, False)) for way, name in ways.items()}


def report(table, failures):
    known = sum(case.knowable for case, _ in failures)
    lines = [f"| Baseline, without a model | right of {known} whose cause can be known | right of {len(failures) - known} that nobody can know |", "|---|---|---|"]
    return "\n".join(lines + [f"| {way} | {right} | {silent} |" for way, (right, silent) in compare(table, failures).items()]) + "\n"
