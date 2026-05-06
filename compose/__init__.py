"""busy-day composer.

Deterministic, rule-based daily composer driven by a seeded RNG. Same
(date, city, generator_ver) -> same song; nothing in this package calls
external models or APIs.
"""

GENERATOR_VER = "v1.0.0"
