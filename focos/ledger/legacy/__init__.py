"""One-time imports from ledgers focos no longer talks to (Sure pg_dump). Imported accounts keep their old
provider prefix (for example ``sure:<uuid>``) and are read only up to a per-account cutoff so they never
double count with the live feed that replaced them."""
