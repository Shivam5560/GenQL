"""A RuleReader that reads nothing, selected when rules are switched off.

The alternative — making AmbiguityGateService's `rules` optional and branching
inside `_defaults` — would put a feature flag in the middle of the one method
whose logic is already the subtlest in the gate. A reader that returns an empty
tuple produces exactly the same gate behaviour as a datasource with no rules
authored, which is a state the gate already handles and is already tested for.

Deleting rules entirely was the other option and is not what `rules_enabled`
means: the table, the writer, the overlay loader and the CLI command are all
still here, and flipping the setting back turns them on with no code change.
"""

from __future__ import annotations

from genql.domain.entities.rule import Rule


class DisabledRuleReader:
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        return ()
