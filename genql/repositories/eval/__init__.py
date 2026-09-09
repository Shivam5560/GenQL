"""Repositories that read and write the golden-set evaluation harness's files.

File I/O only: reading YAML fixtures and writing a JSON run report. Neither
touches a database driver, which is why both live beside each other here
rather than in `genql/repositories/warehouse/`.
"""

from genql.repositories.eval.json_report_repository import JsonReportWriter
from genql.repositories.eval.yaml_golden_set_repository import YamlGoldenSetReader

__all__ = ["JsonReportWriter", "YamlGoldenSetReader"]
