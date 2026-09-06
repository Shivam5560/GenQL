from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember


@runtime_checkable
class DomainWriter(Protocol):
    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]: ...

    def write_members(self, members: Sequence[DomainMember]) -> int: ...
