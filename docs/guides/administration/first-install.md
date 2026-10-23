# Installing Taktus from nothing

This page takes a person who has never seen Taktus from an empty machine to a first process
that ran. It assumes no knowledge of the repository. Every command is meant to be typed as it
stands; a word in angle brackets, such as `<tenant>`, is replaced by the value an earlier step
printed.

An installation of Taktus is called an **instance**. An instance is the program Taktus and the
database it keeps its records in. Nothing in this page connects the instance to anyone else:
it runs on your machine, under your control, and sends nothing out (section 7).

## 1. Choose how to install

There are two supported ways.

| Way | Suits | Section |
|---|---|---|
| **One machine**, with Docker Compose | a trial, or a small business on one server | 2 |
| **A cluster**, with the Helm chart and its `small` profile | a business that runs its systems on Kubernetes | 3 |

**Docker Compose** is a tool that starts several containers together from one file. A
**cluster** is a group of machines run together by a scheduler; Kubernetes is the scheduler
this page means. **Helm** is the tool that installs an application on Kubernetes from a
**chart**, a set of templates filled in by a file of values. The chart's **`small` profile** runs
every part of Taktus in one pod, beside its database. A pod is the unit Kubernetes runs.

Both ways end at section 4. From there the steps are the same, except for how a command reaches
the instance:

| Way | A Taktus command is run as |
|---|---|
| One machine | `docker compose -f deploy/docker/compose.yml exec taktus taktusctl …` |
| Cluster | `kubectl -n taktus exec deploy/taktus-all -- taktusctl …` |

`taktusctl` is Taktus's command line. It runs inside the instance, so it reaches the database
without a password of its own: whoever can run it is the instance's administrator.

## 2. One machine, with Docker Compose

### 2.1 What the machine needs

- Linux or macOS, with 2 GB of free memory and 10 GB of free disk.
- Docker Engine with the Compose plugin, version 2.24 or later: `docker compose version`
  prints it.
- `git`, `make`, `curl` and `python3`.
- Access to the internet while the image is built, for its packages. The running instance needs
  none.

### 2.2 Get the release

A **release** is a version of Taktus, named by a tag such as `v0.4.0`. A tag that ends in
`-rc.` and a number, such as `v0.4.0-rc.2`, is a release candidate: a trial version before the
release. List the newest tags, newest first:

```bash
git clone https://github.com/Jersyfi/taktus.git
cd taktus
git tag --sort=-creatordate | head -5
```

Take the newest tag without `-rc`. Where every tag listed is a release candidate, there is no
release yet, and the newest candidate is the one to try. Check it out:

```bash
git checkout <the tag you chose>
```

Every later command of this page runs in this directory.

### 2.3 Start it

```bash
make up
```

This one command does five things. It writes a random database password, and the address of the
database that carries it, into two files under `deploy/docker/secrets/`. It builds the image of
Taktus, which takes several minutes the first time. It starts two containers: PostgreSQL, the
database, and Taktus. Taktus brings the database to its schema when it starts. The command
returns once Taktus answers that it is ready.

Check it yourself:

```bash
curl -fsS http://127.0.0.1:8080/ready
```

It answers `{"status":"ready",…}`. The instance listens on `127.0.0.1` only, so no other
machine reaches it.

**Where port 8080 is taken on the machine**, choose another one and write it into the file
`deploy/docker/.env`, which Docker Compose reads every time:

```bash
echo TAKTUS_HTTP_PORT=8090 > deploy/docker/.env
make up
```

Use that port wherever this page says 8080. The file is never committed. The port belongs in
this file and in no other: in `deploy/docker/taktus.env` (section 2.4) it would change nothing.

**Keep the two files under `deploy/docker/secrets/`.** The database keeps the password it was
created with. A new password in those files would lock Taktus out of its own database.

### 2.4 Settings on one machine

A first install needs no setting. Every setting of Taktus is a variable whose name begins with
`TAKTUS_`; the file `.env.example` lists each of them with what it does.

To set one, write it into `deploy/docker/taktus.env`, one `NAME=value` per line, and run
`make up` again. Those settings are read by Taktus inside its container. The port of section
2.3 is the one exception: it is read by Docker Compose, from `deploy/docker/.env`. That file is yours: it is never committed, and `make up` reads it when it
exists. A secret never goes into it. A secret is a file the setting points at, as the page
*Configuring* describes.

Continue with section 4.

## 3. A cluster, with the Helm chart

### 3.1 What the cluster needs

- Kubernetes, with a default storage class. A **storage class** is what the
  cluster uses to create a disk on request; `kubectl get storageclass` shows which is the
  default.
- Room for one pod of 384 MiB and one database of 256 MiB, and 25 GiB of disk.
- On your workstation: `kubectl`, configured for the cluster with the right to create
  namespaces, and `git`, `make` and `docker`.
- A container registry the cluster can pull from. A **registry** is the service a cluster
  downloads images from.

### 3.2 Get the release and build the image

Take the release as in section 2.2. Then build the image of Taktus from it and push it to your
registry. `<registry>` is your registry's address with its path, for example
`registry.example.com/acme`; `<version>` is the tag without its leading `v`:

```bash
docker build -f deploy/docker/Dockerfile -t <registry>/taktus:<version> .
docker push <registry>/taktus:<version>
```

Install the Helm version the repository is tested with:

```bash
make helm
```

It places `helm` under `.tools/bin/`.

### 3.3 Create the namespaces and the database's secret

A **namespace** is a named part of a cluster. Taktus uses two: one for itself, one for the work
it starts later. Create both, with the labels that keep what runs in the second one restricted:

```bash
kubectl create namespace taktus
kubectl create namespace taktus-execution
kubectl label namespace taktus-execution \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/audit=restricted \
    pod-security.kubernetes.io/warn=restricted
```

A **Secret** is how Kubernetes holds a value that must not be read by everyone. The chart creates
none: it names Secrets you create first. Create the database's password and the address of the
database that carries it, from files only you can read:

```bash
umask 077
python3 -c 'import secrets; print(secrets.token_urlsafe(24), end="")' > db-password
printf 'postgresql://taktus:%s@taktus-database:5432/taktus' "$(cat db-password)" > db-url
kubectl -n taktus create secret generic taktus-database \
    --from-file=password=db-password --from-file=url=db-url
rm db-password db-url
```

### 3.4 Write your values and install

Write a file `taktus-values.yaml` beside the repository's directory, not inside it, so that
it is never committed. From the repository's directory it is `../taktus-values.yaml`:

```yaml
profile: small
image:
  repository: <registry>/taktus
  tag: "<version>"
database:
  passwordSecret: taktus-database
  passwordKey: password
  urlSecret: taktus-database
  urlKey: url
execution:
  namespace: taktus-execution
```

These are all the values a first install needs. Every other key of the chart keeps its default,
and `deploy/k8s/chart/values.yaml` says what each one does. A registry that asks for a login
needs one more: `image.pullSecret`, the name of a pull Secret you created in the namespace
`taktus`.

Install:

```bash
.tools/bin/helm install taktus deploy/k8s/chart --namespace taktus -f ../taktus-values.yaml --wait --timeout 10m
```

The chart starts the database, brings it to its schema with a one-time job, and starts Taktus.
Check that it is ready:

```bash
kubectl -n taktus rollout status deploy/taktus-all
```

To reach the instance from your workstation, forward a local port to it and leave the command
running in a terminal of its own:

```bash
kubectl -n taktus port-forward service/taktus-api 8080:8080
```

The instance is now at `http://localhost:8080` for you alone. Making it reachable for others,
under a name of your own with a certificate, is the chart's `ingress` values: see
`deploy/k8s/README.md`, section 2.

Continue with section 4, and run each `taktusctl` command as `kubectl -n taktus exec
deploy/taktus-all -- taktusctl …`.

## 4. Create the tenant

A **tenant** is one organisation on an instance. Every run, record and person belongs to exactly
one tenant, and no tenant sees another's. Create yours with a name you choose:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl tenant create "Example Software"
```

It prints the tenant's identifier, which Taktus generated, in the form `tnt_…`. Write it down:
it is `<tenant>` from here on. The instance also holds a tenant named `default`, which it
creates itself; leave it unused. This command lists every tenant, its creation time and its
name:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl tenant list
```

## 5. Add yourself and sign in to the web app

An **identity** is a person as Taktus knows them. Its name begins with `idn_`, and the rest
is yours to choose; this page uses `idn_admin`. Add yours to the tenant:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl identity add idn_admin --tenant <tenant>
```

It prints the tenant the identity was added in, and an **account key**, which begins with
`tka_`, once. Taktus keeps only a digest of it
and cannot show it again. Keep it like a password. If it is lost, this command issues a new one, and the old one stops working:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl identity key idn_admin --tenant <tenant>
```

Open `http://localhost:8080/app/` in a browser on the same machine. Use the name `localhost`,
not `127.0.0.1`: the browser keeps the sign-in only for `localhost` or for an address served
over HTTPS. Paste the account key and sign in. The start page shows what your tenant holds,
which is nothing yet. The sign-in lasts twelve hours in every tab, or until *Sign out*.

## 6. Register a process and run it

A **process** is a description of recurring work: its steps, and for each step the method that
does it. It is written in a file called a **bundle**. **Registering** a process stores its bundle
as a version on the instance; a **run** is one execution of that version.

### 6.1 The first process

The image carries a first process that needs nothing outside Taktus:
`examples/processes/first-process.yaml`. It has three steps: a fixed value, a pause of two
seconds, and a second fixed value. It runs at **autonomy level 2**, written `L2` in the web
app. The autonomy level says how much Taktus may do on its own, from 1 to 4; at level 2 a
person confirms every step, the pause included, before it starts. Register it and start a run of it, in one command:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process examples/processes/first-process.yaml --identity idn_admin --tenant <tenant>
```

It prints the run's identifier, in the form `run_…`; that is `<run>`. In the web app, open the
process *First process* and its run. The run's page names the step that waits for you. Confirm
the steps one after the other, each once the run's page shows it waiting:

```bash
docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process examples/processes/first-process.yaml --identity idn_admin --tenant <tenant> --resume <run> --approve greet
docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process examples/processes/first-process.yaml --identity idn_admin --tenant <tenant> --resume <run> --approve settle
docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process examples/processes/first-process.yaml --identity idn_admin --tenant <tenant> --resume <run> --approve confirm
```

Each command prints the run's state and identifier, and nothing about the step. The run's page
in the web app is where you see it move. After the third confirmation the process's page lists
the run as `finished`. The instance works.

### 6.2 Your own processes

A process of your own is registered the same way: copy its bundle into the instance and submit
it. On one machine:

```bash
docker compose -f deploy/docker/compose.yml cp <your-bundle>.yaml taktus:/tmp/<your-bundle>.yaml
docker compose -f deploy/docker/compose.yml exec taktus taktusctl bundle check /tmp/<your-bundle>.yaml
docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process /tmp/<your-bundle>.yaml --identity idn_admin --tenant <tenant>
```

On a cluster, `kubectl -n taktus cp <your-bundle>.yaml <pod>:/tmp/<your-bundle>.yaml` copies it,
where `<pod>` is the name `kubectl -n taktus get pods -l taktus-role=all` prints.
`taktusctl bundle check` holds the bundle to the rules registration holds it to, and changes
nothing. It also names three rules it does not check; registration checks those. The third
command registers the process and starts a run. A process at level 2 then waits at its first
step, and is confirmed as in section 6.1, with `--process /tmp/<your-bundle>.yaml`.

The processes of a business domain come as a **blueprint**: a set of bundles under
`blueprints/<domain>/processes/`. The blueprint `software-operations` describes the operation
of a software business in stages. Its README says which of its processes are bundles in this
release. Each one that is, is registered with the same three commands. Most of them reach
your other systems — the repository service, the error tracker, a chat — and need a
**connector** for each: a separate program through which Taktus reaches that system. The page
*Configuring* names the settings for connectors and their credentials.

## 7. What leaves this instance

Nothing, until you configure it. An instance installed by this page:

- reaches no address outside the machine or the cluster. Each of the following is an address
  you configure, and none is configured: a connector; a language model; a **worker**, a
  separate program that carries out a step Taktus does not do itself, such as running a
  command; a telemetry collector, which receives a record of how long each step took; and a
  backup store;
- sends no product finding. A **product finding** is what a run met that Taktus lacks. Whether
  it may leave the instance is the setting `TAKTUS_FINDINGS_LEVEL`, which is `off` unless you
  change it;
- gives the Taktus project no access. The project holds no account, key or address of your
  instance, and no part of Taktus asks for one.

## 8. Stop it, and start it again

On one machine, `make down` stops both containers, removes them and keeps every volume. A **volume** is where
a container keeps its data. `make up` starts them again, and every run continues at the step
where it stopped. No command of this repository removes a volume; that is always a person's
own act.

`make up` names the image it builds `taktus:local`. A second installation on the same machine
would build the same name over it; run only one per machine.

On a cluster, the database's and the state's volumes stay when the release is uninstalled.

The next page, *Upgrading* (`docs/guides/administration/upgrading.md`), takes the instance to
a newer release. *Configuring* and *Restoring* are the pages of the same guide that list every
setting and credential, and bring an instance back from a backup.
