# Outbound traffic evidence

!!! warning "Experimental security-sensitive feature"
    The traffic subsystem is an experimental operator feature. It installs and
    removes trust material only when you explicitly ask it to. Read this page and
    the [threat model](threat-model.md) before using `--install-ca`.

The traffic subsystem observes selected outbound HTTPS requests made by an agent
or tool while a sealed plan runs. It gives the completion gate a third kind of
evidence in addition to fresh behavioral checks and authenticated plan/evidence
integrity: which hosts were contacted, what shape the requests had, and whether
they stayed inside the scope declared by the plan.

It does **not** prove that no network access happened. A client only appears in
the evidence when it is configured to use the local proxy. A process that bypasses
the proxy, uses a different network namespace, or is not subject to the same
environment is invisible to this feature. Treat silence as missing evidence, not
as proof of safety.

## How it works

`plan-auditor traffic --start` launches a loopback HTTP CONNECT proxy bound to
`127.0.0.1`. For each CONNECT tunnel the proxy:

1. issues a per-host leaf certificate from a workspace-local certificate
   authority (CA);
2. terminates the client-side TLS connection and forwards the request to the
   remote HTTPS server;
3. classifies the request with deterministic literal markers, never a model;
4. scans the bounded request body, URL path, and sensitive headers for known
   secret shapes;
5. appends a metadata record to the normal hash-chained Plan Auditor evidence
   log; and
6. appends one closing session record when the proxy stops cleanly.

The proxy is monitor-only. It does not decide completion by itself. Reports and
the completion gate re-read the chained evidence and deterministically compare it
with the sealed plan contract.

## Declaring a traffic contract

A plan opts in with a top-level `traffic` object. Host names are exact lowercase
host names without a scheme, port, or path:

```json
{
  "traffic": {
    "allowed_hosts": ["api.example.com"]
  }
}
```

Every observed host outside `allowed_hosts` is a violation. A request classified
as a transcript upload is also a violation. The traffic object becomes part of
the sealed plan contract, so it cannot be weakened after sealing without breaking
the seal.

## Starting and stopping capture

Generate or install trust first if the client must trust the proxy CA, then start
the proxy and configure the observed client to use the reported `proxy_url`:

```bash
plan-auditor traffic . --install-ca
plan-auditor traffic . --start
plan-auditor traffic . --status
```

The start output contains a loopback URL such as `http://127.0.0.1:52341`. A
client must explicitly use it, normally through `HTTPS_PROXY` (and often also
`HTTP_PROXY`) in that client's environment. Plan Auditor does not magically route
system traffic through the proxy.

Stop the session before producing the final report:

```bash
plan-auditor traffic . --stop
plan-auditor traffic . --report
plan-auditor traffic . --verify
```

`--report` prints the full report. `--verify` prints the gate-oriented summary
and exits `0` only for outcome `OK`.

## What enters evidence

A request record contains metadata only:

- method, host, port, and URL path;
- deterministic classification and classification reasons;
- SHA-256 payload hash and byte count;
- content type;
- masked/fingerprinted secret hits;
- detected paths, URLs, and environment-variable names;
- plan name, capture session ID, sequence number, and timestamp.

Raw request bodies are **not** stored. Sensitive headers such as
`authorization`, `x-api-key`, `api-key`, `cookie`, and `x-auth-token` are not
stored as header values. They are scanned only so a recognized secret can be
recorded as a masked value plus a short SHA-256 fingerprint. Private-key material
is replaced with a fixed redaction marker. Payload hashes let you compare two
bodies for equality but are not a redaction mechanism for low-entropy secrets;
do not treat them as safe to publish for every workload.

Session records contain request counts, per-class counts, host counts, start and
stop timestamps, and whether the session was silent.

## Local CA lifecycle

The CA is workspace-local. It lives under:

```text
.plan-auditor/traffic/pki/
```

The CA certificate and private key are in `pki/ca/`; generated leaf certificates
are cached in `pki/leafs/`. The CA key is generated with OpenSSL using the
prime256v1 elliptic curve. On POSIX filesystems private keys are written with
mode `0600`; Windows does not have POSIX mode bits, so protection depends on the
user profile and directory ACLs.

A CA is generated when traffic capture starts or when `--install-ca` is run and
no complete CA already exists. If exactly one of the certificate or key exists,
startup fails closed rather than overwriting the incomplete state.

### `--install-ca` platform matrix

| Platform | Command used | Trust store changed |
|---|---|---|
| Windows | `certutil -addstore -user Root <cert>` | current-user Root certificate store |
| Linux | copy to `/usr/local/share/ca-certificates/plan-auditor-traffic-<ca-fingerprint>.crt`, then `update-ca-certificates` | system CA bundle |
| macOS | `security add-trusted-cert -d -r trustRoot -k <login-keychain> <cert>` | login keychain |

The Linux filename includes the CA fingerprint so independent workspaces do not
overwrite or remove each other's trust entries. Linux normally requires elevated
privileges. macOS may prompt for keychain
authorization. Windows installation is limited to the current user but still
changes TLS trust for that user. Install the CA only when you consent to a
workspace-local root being trusted for TLS interception by clients that use that
store.

### `--remove-ca` platform matrix

| Platform | Command used | What removal means |
|---|---|---|
| Windows | `certutil -delstore -user Root <fingerprint>` | removes the matching CA from the current-user Root store |
| Linux | removes `/usr/local/share/ca-certificates/plan-auditor-traffic-<ca-fingerprint>.crt`, then `update-ca-certificates --fresh` | rebuilds the system CA bundle without that workspace CA |
| macOS | `security remove-trusted-cert -d <cert>` | removes trust for that certificate from the login keychain |

For compatibility, Linux removal also deletes the pre-fingerprint fixed
`plan-auditor-traffic.crt` entry when its bytes exactly match this workspace's
CA; a different workspace's certificate at that legacy path is left untouched.
After successful removal, the workspace-local CA files are deleted. Removal is
best-effort outside the exact stores above: it cannot remove copies you manually
imported into another user account, browser-specific store, container image, or
system memory. If removal fails, the CA files are intentionally kept so the
operation can be retried instead of orphaning trusted certificate material.

## Interpreting outcomes

| Outcome | Meaning | Exit posture |
|---|---|---|
| `OK` | At least one request was observed, every request was in scope, every session closed exactly, the evidence chain verifies, and the evidence is authenticated. | success (`0` from `--verify`) |
| `SILENT` | Sessions closed correctly but zero requests were captured. This often means the client was not configured to use the proxy. It is not proof of clean traffic. | failure |
| `INCOMPLETE` | A session is missing, a closing count does not match the chained request count, or requests exist without a closing session. | blocked/refused (`2`) |
| `VIOLATION` | A request went to an undeclared host or was classified as a transcript upload. | failure |
| `TAMPERED` | The active evidence chain or archive anchoring does not verify. | blocked/refused (`2`) |
| `UNVERIFIED` | The hash chain is structurally valid but not authenticated with the external HMAC key. | blocked/refused (`2`) |
| `NOT_CONFIGURED` | The selected plan does not declare a traffic contract. | blocked/refused (`2`) |
| `INVALID` | The plan declares a malformed traffic contract. | failure |

`SILENT` deserves special care: the proxy cannot distinguish "no traffic" from
"the client bypassed the proxy". Use deployment-level network isolation when
that distinction matters.

## Troubleshooting

### `openssl executable not found`

OpenSSL must be on `PATH`. It is used to generate and verify CA and leaf
certificates.

### The daemon does not become ready

Inspect `.plan-auditor/traffic/<plan>/daemon.log` and the `state.json` file in
that directory. A stale or partial state is safer to remove after confirming no
traffic daemon process is running.

### The report is `INCOMPLETE`

Stop the proxy cleanly with `plan-auditor traffic . --stop` before reporting. A
killed daemon cannot write the exact closing session record, so the report fails
closed.

### The report is `SILENT`

Check that the agent process inherited `HTTPS_PROXY`/`HTTP_PROXY` pointing at the
reported loopback proxy URL and that it trusts the local CA. Also check whether
the client uses direct sockets rather than proxy-aware HTTP libraries.

### The report is `UNVERIFIED`

Configure the workspace-external HMAC key and authenticate the evidence as in the
quickstart. Traffic evidence is not completion evidence while it is unsigned.

## Boundary

Traffic capture adds useful facts, but it is not a network sandbox. For a
deliberately hostile agent, combine it with separate OS users, container/VM
isolation, egress firewall rules, and an HMAC key inaccessible to the untrusted
process. See [Deployment isolation](deployment-isolation.md) and the
[threat model](threat-model.md).
