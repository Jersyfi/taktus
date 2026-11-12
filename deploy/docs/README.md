# The documentation site on web hosting

The documentation site is a directory of static files: HTML, style sheets, scripts and a search
index that the reader's browser reads. It needs no program on the server. Any web hosting that
serves files can serve it (DEC-0234, NTC-0272).

## Building it

```bash
make docs-site
```

The site is then under `build/docs-site/site/`, which git ignores. It is built from the committed
tree: a change that is not committed is not in it. Each page names the commit it was taken from.

## Uploading it over SFTP

SFTP copies files to a server over an encrypted connection. The operator of the hosting provides
three values: the host, the user, and the directory the site is served from. None of them is
written into this repository. The password or the key stays with the operator.

```bash
sftp <user>@<host> <<'EOF'
cd <directory>
put -r build/docs-site/site/* .
EOF
```

`put -r` copies every file and directory, replacing those of the same name. It removes nothing.
A page that is no longer in the guides stays on the server until it is deleted there by hand.

## Asking for a password (optional)

Web hosting that runs Apache reads a file `.htaccess` in the directory it serves. With the
following lines, it asks every reader for a name and a password (*basic authentication*):

```apache
AuthType Basic
AuthName "Taktus documentation"
AuthUserFile <absolute path to .htpasswd>
Require valid-user
```

`.htpasswd` holds each reader's name and a digest of their password. Create it with Apache's
tool `htpasswd -c .htpasswd <name>`, or with the hosting's control panel. Put it outside the
directory that is served, so that nobody can download it. Serve the site over HTTPS only: basic
authentication sends the password with every request.

Neither file is part of the build, and neither belongs in this repository. Upload them once, as
above; `put -r` of the site leaves them in place. Removing `.htaccess` makes the site public.

The Taktus project's own site is public and asks for no password (DEC-0235).
