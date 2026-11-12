## Answering a data-protection request

A person whose data Taktus has processed may ask what is held of them, ask for a copy, ask for
it to be corrected, or ask for it to be erased. This part shows how such a request is answered.
The person who asks is called the **subject**.

### Preparing a request

Open *Data protection* in the web app. Choose the kind of request — access, rectification,
erasure or portability — and enter the subject's identifier: the value your organisation's
systems use for them, such as a customer number. Then choose *Prepare*.

Taktus looks for every run that served one of the subject's cases. It finds them through the
records it keeps of each result and through what each run was started with. The prepared request
shows how many runs and objects it found. Preparing changes nothing.

### Carrying it out

Open the request. Taktus says back what it will do. Before it does anything, you state that you
checked who asked: that the person is the subject, or may act for them. Without that statement
nothing is carried out.

- An **erasure** removes the content of the subject's runs. Something another run still needs is
  kept, and the page says how much. Afterwards Taktus verifies that its records are still intact.
  An erasure cannot be undone.
- An **access** or **portability** request gives you a file to save. Taktus keeps no copy.
- A **rectification** is done by you, at the system the data came from. Taktus records that you
  did it.

If anything changed since the request was prepared, the confirmation is refused. Withdraw the
request and prepare a new one, so that you confirm exactly what you were shown. A request you do
not want to carry out is withdrawn.

Taktus's records name the request and who acted on it, never the subject.

### The processing evidence

*The processing evidence*, linked from the same page, lists what is processed for your
organisation, where, by which integration and how long it is kept. It is generated from the
configuration and the records, never written by hand. It is not legally reviewed, and it says
so.

On the instance's machine the same acts are `taktusctl subject` and `taktusctl evidence`.
