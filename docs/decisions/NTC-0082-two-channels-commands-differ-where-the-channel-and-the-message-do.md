# NTC-0082 — Two channels' commands differ where the channel and the message do

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#148](https://github.com/Jersyfi/taktus/pull/148), for issue #84

## 1. What was decided

UC-1.1 §2 and issue #84 require that the same instruction arriving through two channels
produces two commands "equal in every field except the channel and the identity of the
message". No test checked it. This notice states what the test that now does reads those words
as, field by field of the shared kernel's `Command`.

- **The channel** is three fields. `channel` is the capability. `reply_to` is where in that
  channel the answer goes: a conversation and a thread, or an issue and a comment. `context` is
  what the channel's connector reported about where the message stands: a conversation and a
  message, or a repository, an issue and a comment. The connector names these keys; the test
  removes exactly the keys of the intake event's own context.
- **The identity of the message** is three values. `id` is the command's own identifier.
  `event_id` in the context is the source system's identifier for the delivery. `sender` in the
  context is the account as that system names it; one person has a different account in each
  system. `event` in the context, the kind of event, belongs to the channel as well.
- **Everything else is equal**, and the test says so for each field: `identity` and `org_path`,
  which the identity port completes; `intent`; `received_at`; and what remains of `context` —
  today `identity_provisional`. The set of fields in which the two commands differ is exactly
  `id`, `channel`, `context`, `reply_to`.

The test is `tests/adapters/connectors/test_chat_channel.py::
test_the_same_instruction_through_two_channels_is_the_same_command`. It sends the instruction as
a message in a chat conversation and as a comment on an issue, through the chat connector and
the repository connector, each running as a process of its own against the fake of its service.
The `command` component's own handlers turn both into commands.

## 2. The evidence

- `contracts/shared/v1/Command.json`: `reply_to` "says where the reply goes: back into the same
  channel", and `context` is the "Channel context: the repository, the issue or pull request,
  the thread". Both are per channel by definition.
- `src/taktus/components/command/application/service/complete_intake.py` builds the command's
  context from the intake event's context plus `event`, `event_id`, `sender` and
  `identity_provisional`. The first three name the event and who sent it as the source system
  names them.
- The test passes, and the differing fields are asserted as a set, so that a field that starts
  to differ is a failure and not a silent widening.

## 3. What was considered

- **Every field but `channel` and `id` equal.** Not taken: `reply_to` must differ, because UC-1.1
  §2 also requires that the reply goes "to the thread or conversation it arrived in". A reading
  under which two channels share a reply address contradicts the next line of the same section.
- **Comparing `context` as a whole.** Not taken: it would fail for every pair of channels, since
  a conversation and an issue are not the same thing, and a test that cannot pass verifies
  nothing.
- **A decision request on the reading.** Not taken: the reading follows from the shared kernel's
  own definition of the three fields, and it changes nothing the use case requires. Should the
  owner read the words otherwise, the test is where the reading is written down and can change.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The tests now cover the
equality of two channels' commands, under the reading stated here. What UC-1.1 requires is
unchanged (M3.15); only how its condition is checked is new.
