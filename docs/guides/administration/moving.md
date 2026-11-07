## Moving a tenant to another instance

A tenant moves with everything Taktus holds of it: its processes, runs, ledger, provenance
records, decisions, identities and stored files. The move is an **export** on the instance it
leaves and an **import** on the instance it goes to. Both need the database; an instance whose
state is files under its state directory is for development and exports nothing.

```bash
taktusctl tenant export <tenant> --out tenant.json            # on the instance it leaves
taktusctl tenant import tenant.json                            # on the instance it goes to
```

The import writes only into a tenant that holds nothing on that instance. A fresh instance's
tenant `default` holds nothing, and is where an export of `default` goes. After writing, the
import checks the tenant where it now lives and prints one line per check:

- `ledger verifies` — the ledger's chain holds from its first entry;
- `chains as exported` — every chain ends at the entry the export names;
- `provenance verifies` — every run's record of what produced each result holds.

If a check fails, the command exits with code 1 and names what differs. Nothing is undone on its
own: remove the database, or the tenant's rows, as after a failed restore, and import again.

A run that was waiting when the tenant left — for a person, for time to pass — continues on the
new instance where it waited.

The holder of the administration key can do the same on the HTTP surface:
`GET /administration/tenants/<tenant>/export` and `POST /administration/tenants/import` with the
export as the body.

**Keep the file as you keep a backup.** It holds the tenant's data in clear, and the digests of
its account keys. Taktus does not encrypt it.
