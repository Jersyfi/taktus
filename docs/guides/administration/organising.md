This page sets up who works with Taktus and where things belong. Every command is a `taktusctl`
command, run inside the instance as *Installing from nothing* shows in its section 1. Each takes
`--tenant <tenant>`. The web app's page *Administration* does the same for a person whose role
holds the right `tenant.administer`.

## People and roles

An **identity** is a person as Taktus knows them. A **role** is a name for what people do, such as
`finance-lead`. Taktus gives work, decisions and rights to roles, never to a person.

```bash
taktusctl identity add idn_ada --role finance-lead --tenant <tenant>   # prints the account key once
taktusctl identity roles idn_ada --role finance-lead --role payroll --tenant <tenant>   # replaces her roles
taktusctl identity key idn_ada --tenant <tenant>                       # a new key; the old one stops working
```

## Rights

A **right** lets the holders of a role do one act. A right is granted to a role, never to a
person.

```bash
taktusctl identity grant --role finance-lead --right process.approve --tenant <tenant>
taktusctl identity withdraw --role finance-lead --right process.approve --tenant <tenant>
taktusctl identity rights --tenant <tenant>                            # every role and its rights
```

| Right | Lets the role |
|---|---|
| `process.create` | register the first version of a new process |
| `process.approve` | register a new version of a process, which makes it the active version |
| `autonomy.set` | set the autonomy level of a new process, or approve a version that raises it |
| `process.steer` | state the targets per process and figure; until a role holds it, the owner states them |
| `run.steer` | pause or cancel a run that does not act on the person's behalf |
| `tenant.administer` | administer identities, keys, roles, rights, channel links and unit quotas in the web app |
| `structure.shape` | name the levels of the structure, add units, place things in them |
| `project.company` | create a project for the whole company |
| `agent.start`, `agent.answer`, `agent.take-over`, `agent.steer` | let a person's own agent start a process, answer a decision request, take over a running step, or send a running step a message |

The first three are checked once any role of the tenant holds one of them. Until then,
registration does not ask for them.

## The structure

The **structure** is the organisation as a tree of units: the company, its departments, their
teams. Every process, agent, connector, model, skill and budget is placed in exactly one unit.
Where a process is placed decides who sees it, what it may use, and where its runs are counted.

```bash
taktusctl structure levels company department team --tenant <tenant>       # names the levels, the top first
taktusctl structure unit finance --parent <tenant> --name Finance --tenant <tenant>
taktusctl structure place process payroll --unit finance --tenant <tenant>   # places or moves it
taktusctl structure show --tenant <tenant>                                  # the whole tree, as JSON
```

The top unit is the tenant itself. A run keeps the unit it started in, even after its process
moves.

## Projects

A **project** is a unit for one piece of work. Anyone creates one for themselves, for their team
or for a project team. A project for the whole company needs the right `project.company`.

```bash
taktusctl structure project close-books --circle team --unit finance --name "Closing the books" --identity idn_ada --tenant <tenant>
```

`--circle` is `alone`, `team`, `project_team` or `company`. A project refers to tickets and
documents, and copies nothing (`structure refer`). A project created `alone` is private: it
appears in no other unit and in no figure above it. Only its owner shares it (`structure share`).
People see their projects in the web app, on the page *Structure*.
