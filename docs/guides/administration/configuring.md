An instance is configured through variables whose names begin with `TAKTUS_`. The file
`.env.example` in the repository lists every one of them, by name only. An instance checks them
when it starts, and a wrong one stops it with a message that names the variable.

A **credential** is a secret that lets Taktus act somewhere else: a key, a token, a password.
Taktus never reads a credential from a variable directly. The variable names a file, and the
credential is in that file. Each credential is referred to by its **parameter**: the name under
which it is supplied, never its value.

The file can be written by hand, or filled from a secret store you already use: a password
manager or a vault with a command-line tool that prints one value. On one machine, copy
`deploy/docker/secret-store.example.json` to `deploy/docker/secret-store.json`, name the store's
command and, for each file under `deploy/docker/secrets/`, the value's reference in the store.
`make up` then reads every value from the store before it starts, and
`python3 deploy/docker/secret_store.py --interval 300`, run as a service of the machine, carries
a rotation in the store into the files. On a cluster, whatever fills the Secrets the chart names
from your store keeps them current. Taktus itself reads only the files.

This page lists every parameter, what it is for, what it may do, and how it is replaced.
