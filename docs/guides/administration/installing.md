An installation of Taktus is called an **instance**. An instance is the program Taktus and the
database it keeps its records in. It can run in two ways: as two containers on one machine, or
on a cluster, which is a group of machines run together by a scheduler.

This page has three parts. The first says what an instance consists of and how it is started.
The second says how it is started on one machine, and what it then answers. The third says
what an instance looks like on a cluster.

Every setting is a variable whose name begins with `TAKTUS_`. Nothing secret is ever written into
such a variable: a variable names a file, and the secret is in that file. The page
*Configuring* lists every secret an instance can be given.
