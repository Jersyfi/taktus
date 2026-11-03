# The documents connector — an inbox over WebDAV, invoices in EN 16931

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over two open standards and no product. The inbox is one folder served over **WebDAV**
(RFC 4918), which file shares, document stores and many portals offer. A document in it is read
as an electronic invoice of **EN 16931**, the European standard, in either of its syntaxes:
UBL 2.1 (`Invoice`, `CreditNote`) or CII D16B (`CrossIndustryInvoice`). XRechnung, Peppol BIS
Billing 3.0 and the XML of ZUGFeRD and Factur-X are documents in one of the two. Everywhere else
it is the capability `documents.invoices` (ADR-0169).

It is proof and example, not a requirement: the control plane runs with it removed, and a
process that reads a document through it falls back to a person.

```
uv run python -m taktus_connectors.einvoice --target https://files.example/finance/inbox/ --port 9113
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
inbox folder's WebDAV address; point it at the fake under `tests/fakes/document_inbox_service.py`
to run without a network. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`documents.invoices=http://documents-connector:9113/mcp`.

How a document reaches the folder is the organisation's: a mail rule that files attachments, a
portal's export, a scanner. A scan or a PDF without its XML is not read: the connector reads the
structured invoice, which a scan is not.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `documents.invoices.list` | read | `limit` (default 100, at most 1000) | `documents`, oldest first: `document` (its file name), `size`, `modified`, `etag`; `complete` |
| `documents.invoices.read` | read | `document`, a file name in the folder | `document`, `digest` (SHA-256 of its bytes), `syntax`, `type` (`invoice` or `credit_note`), `type_code`, `number`, `issue_date`, `due_date`, `currency`, `buyer_reference`, `order_reference`, `contract_reference`, `seller` (`name`, `vat_id`), `payment` (`account`), `lines`, `tax`, `totals` |

Each line is `id`, `quantity`, `unit`, `net_amount`, `order_line`, `item`, `tax_category`,
`tax_rate` and `price`, the price of one unit. Each tax category is `category`, `rate`, `base`
and `amount`. The totals are `lines`, `allowances`, `charges`, `without_tax`, `tax`,
`with_tax`, `prepaid`, `rounding` and `payable`. Every amount is the decimal text the document
gave: nothing is computed, so that the `invoice` rule can compute it again ([`standard.py`](standard.py)).

**Defused.** A document that declares a document type or an entity is refused unparsed, and so
is one above 5 MB. A `document` with a slash, a backslash, `..` or a leading dot is refused
before the inbox is asked: a call reaches the folder and nothing else.

Consumption is counted in `quota` units named `requests`: one per request.

## Credentials

One, referenced by name, `DOCUMENTS_TOKEN`: the requesting identity's access to the folder. A
value `user:password` is sent as basic authentication, any other as a bearer token
(`CREDENTIALS.md`).

## Errors

As [`operations.py`](operations.py) maps them: a document that is not such an invoice, or not in
the folder, is `invalid`; 401 `unauthenticated`; 403 `forbidden`; 429, 5xx and a lost connection
`unavailable` and retryable.

## Not here

Moving a document out of the inbox once handled: a run reads one document, and which documents
were handled is in the ledger. A PDF with the XML embedded (ZUGFeRD, Factur-X) is read only as
its XML, filed beside it.
