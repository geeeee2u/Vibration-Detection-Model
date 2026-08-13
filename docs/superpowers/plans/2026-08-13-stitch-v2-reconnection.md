# Stitch v2 Dashboard Reconnection Implementation Plan

**Goal:** Apply the v2 Stitch layouts while preserving existing FastAPI data bindings and role-based access behavior.

**Layout mapping:** `industrial_sentinel_6` → overview, `industrial_sentinel_5` → analysis, `industrial_sentinel_2` → alarms, `industrial_sentinel_1` → performance, and `industrial_sentinel_4` → administrator settings. The technician denial state remains client-rendered so it displays the required Korean access message.

## Tasks

1. Replace the five frontend shells with the mapped v2 Stitch HTML, retain common scripts, add page identifiers, direct navigation URLs, and data targets required by the existing application script.
2. Adapt the shared frontend script to populate v2 elements and keep the account switcher, settings access denial, API calls, and charts working.
3. Update layout regression tests, run the full Python suite, and verify all routes plus administrator/technician flows in the browser.
