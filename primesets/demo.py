"""A made-up inventory, to look at the program before one's own list is added.

It is shown only while the user asks for it and is never written to the disk: the real inventory,
the mastery marks, the riven mods, the relics, the history and the journal of sales stay as they
are, and every change is refused while the example is on.  After a restart the example is off again.

The parts, riven mods and relics below are invented; nobody's account looks like this.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

# part (its name on warframe.market) -> how many
ITEMS: Dict[str, int] = {
    "rhino_prime_blueprint": 1, "rhino_prime_chassis_blueprint": 3, "rhino_prime_neuroptics_blueprint": 1,
    "rhino_prime_systems_blueprint": 1,
    "mesa_prime_blueprint": 1, "mesa_prime_chassis_blueprint": 1, "mesa_prime_neuroptics_blueprint": 1,
    "mesa_prime_systems_blueprint": 1,
    "saryn_prime_blueprint": 2, "saryn_prime_chassis_blueprint": 2, "saryn_prime_neuroptics_blueprint": 2,
    "saryn_prime_systems_blueprint": 2,
    "wukong_prime_blueprint": 1, "wukong_prime_chassis_blueprint": 1, "wukong_prime_neuroptics_blueprint": 1,
    "wukong_prime_systems_blueprint": 1,
    "soma_prime_blueprint": 1, "soma_prime_barrel": 1, "soma_prime_receiver": 2, "soma_prime_stock": 1,
    "paris_prime_blueprint": 1, "paris_prime_grip": 1, "paris_prime_lower_limb": 1, "paris_prime_string": 1,
    "paris_prime_upper_limb": 1,
    "orthos_prime_blueprint": 2, "orthos_prime_blade": 4, "orthos_prime_handle": 2,
    "akstiletto_prime_blueprint": 1, "akstiletto_prime_barrel": 2, "akstiletto_prime_link": 1,
    "akstiletto_prime_receiver": 2,
    "nikana_prime_blueprint": 1, "nikana_prime_blade": 1, "nikana_prime_hilt": 1,
    "carrier_prime_blueprint": 1, "carrier_prime_carapace": 1, "carrier_prime_cerebrum": 1, "carrier_prime_systems": 1,
    "odonata_prime_blueprint": 1, "odonata_prime_harness_blueprint": 1, "odonata_prime_systems_blueprint": 1,
    "odonata_prime_wings_blueprint": 1,
    "tigris_prime_blueprint": 1, "tigris_prime_barrel": 1, "tigris_prime_receiver": 1, "tigris_prime_stock": 1,
    "gara_prime_blueprint": 1, "gara_prime_chassis_blueprint": 1, "gara_prime_neuroptics_blueprint": 1,
    "khora_prime_blueprint": 1, "khora_prime_chassis_blueprint": 1, "khora_prime_neuroptics_blueprint": 1,
    "lex_prime_blueprint": 1,
    "nekros_prime_blueprint": 1, "nekros_prime_chassis_blueprint": 1, "nekros_prime_neuroptics_blueprint": 1,
    "volt_prime_blueprint": 1, "volt_prime_chassis_blueprint": 1,
    "galatine_prime_blueprint": 1, "galatine_prime_blade": 1,
    "burston_prime_blueprint": 1, "burston_prime_barrel": 1, "burston_prime_receiver": 1,
}

# set -> the mastery mark shown in the example
MASTERY: Dict[str, str] = {
    "rhino_prime_set": "mastered", "mesa_prime_set": "mastered", "saryn_prime_set": "mastered",
    "wukong_prime_set": "none", "soma_prime_set": "mastered", "orthos_prime_set": "mastered",
    "akstiletto_prime_set": "mastered", "nikana_prime_set": "mastered", "carrier_prime_set": "mastered",
    "odonata_prime_set": "mastered", "tigris_prime_set": "owned",
}

# riven mods of the example: (weapon, the mod's own name)
RIVENS = [
    ("soma", "Crita-visitis"), ("latron", "Sati-toxidra"), ("boar", "Vexi-hexatron"), ("tatsu", "Visi-critatis"),
    ("akarius", "Igni-satidra"), ("fragor", "Crita-vexitis"), ("ocucor", "Acri-satitio"), ("hate", "Visi-croniata"),
]

# void relics of the example: (relic, refinement, how many)
RELICS = [
    ("Lith A13", "intact", 6), ("Lith B7", "intact", 3), ("Meso K9", "flawless", 1), ("Neo N21", "intact", 2),
    ("Neo F3", "radiant", 1), ("Axi A22", "intact", 2), ("Axi D6", "exceptional", 1), ("Axi S21", "intact", 1),
]

_since: Optional[str] = None


def on() -> bool:
    return _since is not None


def since() -> Optional[str]:
    """When the example was switched on -- it stands where the date of the inventory is shown."""
    return _since


def switch(value: bool) -> None:
    global _since
    _since = datetime.now().astimezone().isoformat(timespec="seconds") if value else None
