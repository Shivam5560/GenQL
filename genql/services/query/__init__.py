"""The five online-pipeline stages, one service per file.

Every service here is constructor-injected with ports only. None of them
imports a repository, a driver, or LangGraph — which is what lets the whole
pipeline be exercised in unit tests with fakes and no infrastructure at all.
"""
