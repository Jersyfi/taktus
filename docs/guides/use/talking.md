You can talk to Taktus in four places. Taktus proposes; nothing is done until you say yes.

## Where you talk, and what you can do there

| Where | How | What you can do |
|---|---|---|
| **Web app, "Ask Taktus"** | open `#/ask` and write | anything: plan a process, ask for a change or a new process, rehearse, commission, roll back, start a process. Each proposal shows as a card with **Yes, do it** and **No** |
| **Chat** | write in the chat Taktus reads | the fixed phrases below; anything else is answered by Taktus's conversation, as on the web |
| **Command line** | `taktusctl` | for the people who run Taktus: `taktusctl --help` lists everything |
| **Your own agent** | an MCP client with your agent key | the tools below, within the rights of your roles |

The web page and the chat are one conversation: what you started in one, you can continue in
the other. Nobody else sees it.

## How a conversation goes

1. You write what you want, in your own words.
2. Taktus answers briefly. Where it can do something for you, it says exactly what: "Open a plan
   draft for “answer supplier invoices”".
3. You say **yes** or **no**. Only a yes does it. Taktus then says what came of it, with links.

Each answer is formed by a run of its own, with its own budget, and shows in the ledger. The
conversation answers only where the people who run Taktus switched it on
(`TAKTUS_CONVERSATION_PROCESS`); otherwise the page says so.

## The fixed phrases of the chat

These are read first, exactly, before the conversation. The words are your organisation's
phrasebook; these are the English ones.

| You write | Taktus does |
|---|---|
| `status` | lists your runs that have not ended |
| `pause <run>`, `cancel <run>` | halts the run at its next step; a cancelled run never resumes |
| `show overview`, `show run <run>`, `show process <process>`, `show origin <run>/<step>` | the page as text, with its link |
| `what can i ask for`, `catalogue` | the processes you may start |
| `start <process>` | read back; starts on your `yes` |
| `change process <process>: <words>` | Taktus works out a proposed change; nothing changes yet |
| `rehearse <proposal>` | runs the proposal without any effect outside |
| `commission <proposal>` | read back; the proposal becomes the active version on your `yes` |
| `roll back <process>@<version>` | read back; that version is current again on your `yes` |
| `take over <run> <step>`, `show takeover <takeover>`, `hand back <takeover>: <result>` | you take a running step over, see it, and hand its result back |
| `message <run> <step>: <text>` | sends a running step a message |
| `spend <run>`, `spend process <process>` | where a run or a process spends |
| `session <project>`, `session <project>: <text>` | a session with a project's knowledge |
| `yes`, `confirmed` / `no` | confirms or drops what was read back to you |
| `done`, `provided` | in the thread of a report: what it asked for is done |

## Your own agent

Your own agent — Claude Code, Claude Desktop or any other MCP client — reaches Taktus as you,
and never as more than you.

**1. Get an agent key.** Create it with your account key:

```
curl -X POST -H "Authorization: Bearer $TAKTUS_ACCOUNT_KEY" https://<instance>/<prefix>/identity/agent-key
```

The answer holds `agent_key`, which begins with `tkg_`. A new key replaces the old one. An
administrator can issue one too, on the page *Administration*. The agent key opens only the
agent's endpoint; your account key never goes into the agent.

**2. Connect your agent.** The endpoint is `https://<instance>/<prefix>/mcp`, over MCP's
streamable HTTP transport, with the header `Authorization: Bearer <agent key>`. A client that
cannot send that header cannot reach it. The configuration of Claude Code (`.mcp.json`), and of
other clients that take a remote server by URL and header:

```json
{
  "mcpServers": {
    "taktus": {
      "type": "http",
      "url": "https://<instance>/<prefix>/mcp",
      "headers": { "Authorization": "Bearer ${TAKTUS_AGENT_KEY}" }
    }
  }
}
```

With Claude Code: `claude mcp add --transport http taktus https://<instance>/<prefix>/mcp
--header "Authorization: Bearer $TAKTUS_AGENT_KEY"`. Keep the key in your own secret store or
an environment variable, never in a file you share.

**3. What it may do.** It always reads. It acts only where a role you hold was granted the
right; ask the people who administer Taktus.

| Tools | Right needed |
|---|---|
| `list_processes`, `list_runs`, `get_run`, `list_decisions`, `get_decision`, `show_takeover`, `list_plans`, `get_plan`, `list_proposals`, `get_proposal` | none |
| `start_process` | `agent.start` |
| `answer_decision`, `confirm_decision` | `agent.answer` |
| `take_over_step`, `hand_back` | `agent.take-over` |
| `steer_step` | `agent.steer` |
| `open_plan`, `answer_plan`, `set_plan`, `commission_plan` | `agent.plan` |
| `ask_change`, `ask_description`, `rehearse_proposal`, `commission_proposal`, `discard_proposal`, `rollback_process` | `agent.change` |
| `confirm_act` | the right of the act it confirms |

`commission_plan`, `commission_proposal` and `rollback_process` do nothing at first: they come
back read back, and only `confirm_act` does them. A decision answer counts only after
`confirm_decision`. Every call is in the ledger with you as its actor.
