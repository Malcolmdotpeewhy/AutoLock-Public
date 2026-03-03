"""
Rune Manager
Handles rune page creation, validation, and application.
"""
import json
import os

# pylint: disable=too-many-branches


class RuneManager:
    """Manages rune pages and summoner spells."""

    def __init__(self, lcu, assets):
        self.lcu = lcu
        self.assets = assets

        # --- Spell IDs ---
        self.spells = {
            "FLASH": 4,
            "SMITE": 11,
            "TELEPORT": 12,
            "IGNITE": 14,
            "EXHAUST": 3,
            "GHOST": 6,
            "HEAL": 7,
            "BARRIER": 21,
            "CLEANSE": 1,
        }

        # --- Standard Rune Pages (Archetypes) ---
        # IDs are Riot's Perk IDs.
        self.pages = {
            "AD_CARRY": {
                "name": "Agent V8: ADC (Lethal Tempo)",
                "primaryStyleId": 8000,  # Precision
                "subStyleId": 8100,  # Domination
                "selectedPerkIds": [
                    8021,  # Fleet
                    9111,  # Triumph
                    9104,  # Alacrity
                    8014,  # Coup
                    8139,  # Taste of Blood
                    8106,  # Ult Hunter
                    5005,  # AS
                    5008,  # Adaptive
                    5001,  # Health Scaling (Repl. Armor)
                ],
                "current": True,
            },
            "MAGE_BURST": {
                "name": "Agent V8: Mage (Electrocute)",
                "primaryStyleId": 8100,  # Domination
                "subStyleId": 8200,  # Sorcery
                "selectedPerkIds": [
                    8112,  # Electrocute
                    8126,  # Cheap Shot
                    8138,  # Eyeball
                    8106,  # Ult Hunter
                    8210,  # Manaflow
                    8237,  # Scorch
                    5008,
                    5008,
                    5001,  # Health Scaling
                ],
                "current": True,
            },
            "FIGHTER": {
                "name": "Agent V8: Fighter (Conqueror)",
                "primaryStyleId": 8000,  # Precision
                "subStyleId": 8400,  # Resolve
                "selectedPerkIds": [
                    8010,  # Conqueror
                    9111,  # Triumph
                    9104,  # Alacrity
                    8299,  # Last Stand
                    8444,  # Second Wind
                    8242,  # Unflinching
                    5005,
                    5008,
                    5001,  # Health Scaling
                ],
                "current": True,
            },
            "TANK": {
                "name": "Agent V8: Tank (Grasp)",
                "primaryStyleId": 8400,  # Resolve
                "subStyleId": 8000,  # Precision
                "selectedPerkIds": [
                    8437,  # Grasp
                    8446,  # Demolish
                    8429,  # Conditioning
                    8451,  # Overgrowth
                    9111,  # Triumph
                    9103,  # Legend: Tenacity
                    5005,
                    5001,  # Health Scaling
                    5013,  # Tenacity
                ],
                "current": True,
            },
        }

    def apply_loadout(self, role, champ_id=None, set_runes=True, set_spells=True):
        """Apply runes and spells based on role/champion."""
        if not self.lcu.is_connected:
            return

        if set_runes:
            # Smart Selection: Class Based (Priority) -> Role Based (Fallback)
            page_key = "FIGHTER"  # Global Default

            tags = []
            if champ_id:
                tags = self.assets.get_champ_tags(champ_id)

            if "Marksman" in tags:
                page_key = "AD_CARRY"
            elif "Tank" in tags:
                page_key = "TANK"
            elif "Fighter" in tags:
                page_key = "FIGHTER"
            elif "Mage" in tags:
                page_key = "MAGE_BURST"
            elif "Assassin" in tags:
                page_key = "MAGE_BURST"
            elif "Support" in tags:
                # Sub-classify Support
                if "Tank" in tags or "Fighter" in tags:
                    page_key = "TANK"
                else:
                    page_key = "MAGE_BURST"

            # Fallback to Role if tags didn't catch (or no champ_id)
            elif role:
                if role == "BOTTOM":
                    page_key = "AD_CARRY"
                elif role in ("MIDDLE", "UTILITY"):
                    page_key = "MAGE_BURST"
                elif role in ("TOP", "JUNGLE"):
                    page_key = "FIGHTER"

            self._set_rune_page(self.pages[page_key])

        if set_spells:
            # Determine Spells
            spell1 = self.spells["FLASH"]
            spell2 = self.spells["IGNITE"]  # Default

            if role == "JUNGLE":
                spell2 = self.spells["SMITE"]
            elif role == "TOP":
                spell2 = self.spells["TELEPORT"]
            elif role == "BOTTOM":
                spell2 = self.spells["HEAL"]
            elif role == "UTILITY":
                spell2 = self.spells["EXHAUST"]  # or Ignite

            self._set_summons(spell1, spell2)

    def apply_saved_page(self, page_name):
        """Apply a locally saved rune page."""
        if not os.path.exists("rune_pages.json"):
            return

        try:
            with open("rune_pages.json", "r", encoding="utf-8") as f:
                saved_pages = json.load(f)
        except Exception:  # pylint: disable=broad-exception-caught
            return

        # 2. Find page
        target = next((p for p in saved_pages if p["name"] == page_name), None)
        if target:
            self._set_rune_page(target)

    def _set_rune_page(self, page_data):
        # 0. Validate and Fix IDs
        page_data = self._validate_page(page_data)

        # 1. Get Current Page ID
        current = self.lcu.request("GET", "/lol-perks/v1/currentpage")
        if current and current.status_code == 200:
            pid = current.json().get("id")
            if current.json().get("isEditable"):
                self.lcu.request("DELETE", f"/lol-perks/v1/pages/{pid}")

        # 2. Create Page
        self.lcu.request("POST", "/lol-perks/v1/pages", page_data)

    def _validate_page(self, page_data):
        """Ensures all perk IDs in page_data exist in the current patch. Replaces invalid ones."""
        # Load Rune Data on demand
        rune_structure = self.assets.get_runes_data()  # List of Trees
        if not rune_structure:
            return page_data  # Can't validate

        # Map: TreeID -> SlotIndex -> [PerkIDs]
        tree_map = {}

        for tree in rune_structure:
            tid = tree["id"]
            tree_map[tid] = []
            for slot in tree.get("slots", []):
                slot_ids = [r["id"] for r in slot.get("runes", [])]
                tree_map[tid].append(slot_ids)

        original_perks = page_data.get("selectedPerkIds", [])
        primary_style = page_data.get("primaryStyleId")
        sub_style = page_data.get("subStyleId")

        # Reconstruct the page from scratch using the Structure + Preferences.
        final_list = []

        # Primary: 4 slots
        if primary_style in tree_map:
            for options in tree_map[primary_style]:
                # Look for a match
                match = next((p for p in original_perks if p in options), None)
                if match:
                    final_list.append(match)
                elif options:
                    final_list.append(options[0])  # REPAIR

        # Sub: Need 2 perks from Sub Tree (excluding keystone)
        if sub_style in tree_map:
            sub_candidates = []
            # Gather valid selections from original that are in sub tree (excluding Keystone slot 0)
            for slot_idx, options in enumerate(tree_map[sub_style]):
                if slot_idx == 0:
                    continue  # Skip Keystone

                match = next((p for p in original_perks if p in options), None)
                if match:
                    sub_candidates.append(match)

            # Verify we have enough
            if len(sub_candidates) >= 2:
                final_list.extend(sub_candidates[:2])
            else:
                # Fill missing
                count = len(sub_candidates)
                final_list.extend(sub_candidates)

                for slot_idx, options in enumerate(tree_map[sub_style]):
                    if slot_idx == 0:
                        continue
                    if count >= 2:
                        break

                    if options:
                        if not any(x in options for x in final_list):
                            final_list.append(options[0])
                            count += 1

        # Shards (Stat Mods)
        # S14 Valid IDs: 
        # Row 1: 5008 (Adap), 5005 (AS), 5007 (Haste)
        # Row 2: 5008 (Adap), 5010 (MS), 5001 (HP Scale)
        # Row 3: 5011 (HP Flat), 5013 (Tenacity), 5001 (HP Scale)
        valid_shards = [5001, 5005, 5007, 5008, 5010, 5011, 5013]
        
        shards = [
            p for p in original_perks if p in valid_shards
        ]
        
        # Mapping deprecated to reasonable defaults if found in old pages
        deprecated_map = {
            5002: 5001, # Armor -> HP Scaling
            5003: 5013, # MR -> Tenacity (or HP)
        }
        
        # Recover deprecated
        for p in original_perks:
            if p in deprecated_map and len(shards) < 3:
                # Avoid adding if we already have it (though duplicates allowed in different rows)
                 if p not in shards: # simple check
                     shards.append(deprecated_map[p])

        if len(shards) < 3:
            # Add defaults
            defaults = [5008, 5008, 5001]  # Adaptive, Adaptive, HP Scaling
            shards.extend(defaults[: (3 - len(shards))])
        
        final_list.extend(shards[:3])

    def _set_summons(self, s1, s2):
        self.lcu.request(
            "PATCH",
            "/lol-champ-select/v1/session/my-selection",
            {"spell1Id": s1, "spell2Id": s2},
        )
