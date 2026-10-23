# The gallery

The gallery is where a person new to Taktus chooses a first process (UC-10.4, ADR-0136). The web
app's page *Gallery* shows what this directory holds. Each directory here is one **gallery
blueprint**, for a typical small organisation:

| Blueprint | For | Its process |
|---|---|---|
| [`family`](family/gallery.yaml) | a household | the week's shopping list |
| [`club`](club/gallery.yaml) | a club or an association | the reminder of the next meeting |
| [`small-business`](small-business/gallery.yaml) | a small business | the invoices to follow up |

A gallery blueprint is open files only. `gallery.yaml` holds `kind: gallery`, a `title`, whom it
is `for` and a `summary`, in plain words. Its processes are the bundles under `processes/`, in
the format every bundle has; `taktusctl bundle check blueprints/gallery` checks them.

The gallery offers a process only where registration's checks accept its bundle, and only at
autonomy level 1 or 2. Its **choices** are the inputs its schedule trigger gives: a person sets
them, and the process is proposed with them. Each process here is two rule steps that reach
nothing outside Taktus, so that its rehearsal runs to its end on an instance with no connector.

**Removable.** Removing a blueprint's directory removes it from the gallery at the next reading,
and from nothing else: no other process, setting or test names it. The image carries this
directory; `TAKTUS_GALLERY_DIRECTORY` names the one an instance reads, and an empty setting is
an empty gallery. **Never compulsory.** A process is registered from its own file as before
(`docs/guides/administration/first-install.md`, section 7).
