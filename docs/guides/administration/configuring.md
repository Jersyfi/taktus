An instance is configured through variables whose names begin with `TAKTUS_`. The file
`.env.example` in the repository lists every one of them, by name only. An instance checks them
when it starts, and a wrong one stops it with a message that names the variable.

A **credential** is a secret that lets Taktus act somewhere else: a key, a token, a password.
Taktus never reads a credential from a variable directly. The variable names a file, and the
credential is in that file. Each credential is referred to by its **parameter**: the name under
which it is supplied, never its value.

This page lists every parameter, what it is for, what it may do, and how it is replaced.
