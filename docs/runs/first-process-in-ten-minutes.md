# A first process in ten minutes

The record of UC-10.4: how long it takes from the install command to the end of a first
rehearsed process. Every time here was recorded by `make start`'s clock
(`deploy/docker/start.py`, ADR-0136 §6), from the host's clock at the start and the rehearsal
run's own record at the end. None is an estimate.

The path is: `make start`; sign in to the web app with the printed key; open the gallery;
choose a process and its choices; rehearse it. The clock stops when the rehearsal has finished.

## Without a person

`make verify-first-process` (`deploy/docker/first-process.sh`) goes the path through the HTTP
surface, with no time spent reading or typing. It measures what the machine takes. It installed
under a compose project of its own, with new volumes, and chose the first process the gallery
offers: the club's reminder of the next meeting.

**2026-10-23**, a development machine: macOS 25.6, arm64, 14 processors. Its network was not
recorded.

| Stage | Build cache used | No build cache |
|---|---|---|
| the image built | 15.8 s | 43.5 s |
| the containers ready | 8.9 s | 11.8 s |
| the first tenant and its key | 1.6 s | 2.3 s |
| to the rehearsal's start | 0.1 s | 0.7 s |
| the rehearsal | 0.9 s | 0.6 s |
| **total** | **27.2 s** | **59.0 s** |

"No build cache" is `TAKTUS_FIRST_NO_CACHE=1`: the base images pulled again and no cached layer
used, as on a new machine. The packages the build downloads came over the network both times.
The nightly ring runs the same on a new runner every night, and fails above ten minutes.

What it does not measure: the time a person needs to read the screen, to find the gallery, to
understand the choices and to decide. That is the rest of the ten minutes, and only a trial
with a person measures it.

## With a person

Not yet. A person new to Taktus, who is not technical, goes the same path with the installation
guide alone, and `make start`'s clock records the time. Arranging the trial is the owner's
(NEED-0034). Its record will hold the time, the stages, the machine, the network, and every
place the person stopped, each fixed or recorded as a finding. It names nobody (principle 14).
