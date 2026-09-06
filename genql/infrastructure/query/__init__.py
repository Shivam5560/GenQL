"""Per-datasource assembly for the online query path.

Same role as `infrastructure/catalog/`: it knows which registry key to
resolve for a given datasource and hands the service a ready object, so no
service ever imports a registry.
"""
