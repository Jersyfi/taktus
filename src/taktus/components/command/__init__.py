"""Owns channel normalisation, command, plan, commissioning.

Every channel — CLI, chat, web, schedule, event — produces the same `Command` (shared kernel),
and a command becomes a `Plan` through the same use case. Commissioning is an explicit,
recorded act (control-plane.md §3): the plan carries who commissioned it and when, and only a
commissioned plan reaches the run component. The dialogue that develops a plan arrives later;
in this version a plan is commissioned in one step from a process version's steps.
"""
