"""Integrations connecting AgentEval Forge to external systems.

Each subpackage adapts AgentEval Forge's evidence-in / report-out pipeline to a
specific external system through an *explicit contract* — never by importing the
other system's source code at runtime. AgentEval Forge and the systems it judges
remain independent repositories.
"""
