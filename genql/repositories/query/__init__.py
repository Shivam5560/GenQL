"""Repositories the online query pipeline reads and executes through.

Separate from `repositories/semantic/` because nothing here writes: this
package holds the read side of the store and the one component that touches a
warehouse driver at query time.
"""

from genql.repositories.query.decomposition_strategy import DecompositionStrategy
from genql.repositories.query.execution_plan_strategy import ExecutionPlanStrategy

__all__ = ["DecompositionStrategy", "ExecutionPlanStrategy"]
