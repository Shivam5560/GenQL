"""A malformed semantic/<datasource>.yaml fails validation wholesale before
any row is written — proven here at the parsing boundary the CLI command
uses, without needing a real file or a database."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from genql.domain.entities.semantic_overlay import SemanticOverlay

VALID_YAML = """
datasource: local
objects:
  "tpcds.store_sales":
    description: "Point-of-sale line items."
    columns:
      ss_ext_sales_price:
        unit: USD
metrics:
  - name: net_sales
    sql_expression: "ss_ext_sales_price - ss_ext_discount_amt"
    grain: line_item
"""

INVALID_YAML = """
datasource: local
metrics:
  - name: net_sales
    grain: line_item
"""  # missing required sql_expression


def test_valid_yaml_parses_into_a_semantic_overlay() -> None:
    overlay = SemanticOverlay.model_validate(yaml.safe_load(VALID_YAML))

    assert overlay.objects["tpcds.store_sales"].columns["ss_ext_sales_price"].unit == "USD"


def test_invalid_yaml_raises_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        SemanticOverlay.model_validate(yaml.safe_load(INVALID_YAML))


def test_a_rules_block_parses_into_rule_overlays() -> None:
    overlay = SemanticOverlay.model_validate(
        yaml.safe_load(
            """
            datasource: local
            rules:
              - name: default_period
                dimension: time_range
                value: fiscal_year_to_date
                description: An unqualified period means the fiscal year to date.
              - name: active_only
                dimension: filter
                value: status = 'active'
                description: Customers means active customers unless stated otherwise.
            """
        )
    )

    assert [r.name for r in overlay.rules] == ["default_period", "active_only"]
    assert overlay.rules[0].dimension == "time_range"


def test_an_overlay_with_no_rules_block_defaults_to_empty() -> None:
    overlay = SemanticOverlay.model_validate(yaml.safe_load("datasource: local\n"))

    assert overlay.rules == ()


def test_a_rule_missing_a_required_field_fails_validation() -> None:
    with pytest.raises(ValidationError):
        SemanticOverlay.model_validate(
            yaml.safe_load(
                """
                datasource: local
                rules:
                  - name: default_period
                    dimension: time_range
                """
            )
        )
