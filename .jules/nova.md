## 2024-05-18 - Quick Presets with Animated Transitions
**Learning:** Combining functional UI updates (like toggles and sliders) with visual, animated lerping and instant toast notifications significantly enhances user engagement and clarity, transforming a static configuration panel into a responsive, satisfying experience.
**Action:** Always consider using animated transitions (e.g., `_animate_slider`) and localized toast feedback when building "macro" actions or quick presets that modify multiple states simultaneously, ensuring users intuitively understand the impact of their actions. Use tracking animation IDs to cancel previous conflicting animations to prevent jittery visuals.
## 2025-03-04 - Adding Missing UI Toggles for Backend Configs
**Learning:** Sometimes the backend engine (e.g., `AutomationEngine`) fully supports a feature (like `auto_accept`), but the UI toggle is simply missing. Adding it using existing UI patterns (`_add_toggle_compact`) unlocks existing functionality without backend changes.
**Action:** When adding a new toggle, check if the config key already exists in the save list (`save_config`) to ensure the state persists correctly.
