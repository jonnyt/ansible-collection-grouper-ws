# Grouper Ansible Collection (`grouper.ws`)

Manage [Internet2 Grouper](https://www.internet2.edu/products-services/trust-identity/grouper/)
folders, groups, loader definitions and JEXL scripted groups idempotently from
Ansible, through the Grouper Web Services (`grouper-ws`) REST API.

## What this collection does, and deliberately does not, do

| Module | Purpose |
| --- | --- |
| `grouper.ws.stem` | Create or update a folder (a *stem*) |
| `grouper.ws.group` | Create or update a group, role or entity |
| `grouper.ws.loader` | Attach or update a SQL or LDAP loader definition on a group |
| `grouper.ws.jexl_script` | Attach or update a JEXL script (ABAC) on a group |
| `grouper.ws.stem_info` | Look up folders |
| `grouper.ws.group_info` | Look up groups |

Three things are intentionally out of scope.

**Membership is never managed.** There is no option to add or remove members,
and there never will be. Grouper group membership is normally owned by a
loader, a provisioner, or a person acting through the UI. A playbook that also
declared membership would fight those owners and silently undo their work on
every run. When membership should come from a source of record, express that
as a loader definition and let Grouper's daemon own it.

**Nothing is ever deleted.** No module removes a stem or a group. Deleting a
Grouper group destroys its memberships and any privileges granted through it,
which is rarely what a converging playbook should do on its own. Removal is a
deliberate, human act; do it in the UI or with `grouper-ws` directly.

**Loaders are never run on demand.** The module writes the definition. Grouper's
loader daemon decides when to act on it.

## Requirements

- `ansible-core` 2.15 or later
- A reachable `grouper-ws` deployment
- An account authorised to use Grouper web services

No Python dependencies beyond ansible-core: the modules use
`ansible.module_utils.urls`, and the JWT options below use `cryptography`, which
ansible-core already requires.

## Installation

```bash
ansible-galaxy collection install git+https://github.com/jonnyt/ansible-collection-grouper-ws.git
```

Or build from a checkout:

```bash
ansible-galaxy collection build
ansible-galaxy collection install grouper-ws-*.tar.gz
```

## Connecting

Every module takes the same connection options. `ws_url` is the base URL up to
and including the context path, **without** `/servicesRest`:

```yaml
ws_url: https://grouper.example.edu/grouper-ws
```

Authenticate with HTTP Basic:

```yaml
username: banderson
password: "{{ grouper_ws_password }}"
```

or with a pre-issued bearer token, sent verbatim, for deployments behind an OIDC
or JWT aware proxy:

```yaml
token: "{{ grouper_ws_token }}"
```

or with Grouper's own JWT authentication, where the collection signs each call:

```yaml
jwt_prefix: "jwtUser_YWMyOTE5NGVkZTE4NDU1NzgxYmJhNjM0NjYwNTFlYzQ=_"
jwt_private_key_path: ~/.grouper/ansible-entity.key
```

Any of these can come from the environment instead: `GROUPER_WS_URL`,
`GROUPER_WS_API_VERSION`, `GROUPER_WS_USERNAME`, `GROUPER_WS_PASSWORD`,
`GROUPER_WS_TOKEN`, `GROUPER_WS_JWT_PREFIX`, `GROUPER_WS_JWT_PRIVATE_KEY`,
`GROUPER_WS_JWT_PRIVATE_KEY_PATH`.

### JWT authentication

In the Grouper UI, someone with `ADMIN` on a **local entity** can download that
entity's private key once and copy the bearer prefix shown beside it. Give
`jwt_prefix` that prefix and point `jwt_private_key_path` at the key, or pass the
key material through `jwt_private_key` from Ansible Vault.

The key never leaves the controller. A fresh JWT is signed for every web service
call, because Grouper rejects one whose issue time is older than
`grouper.selfService.jwt.maxValidTimeInSeconds` — 600 seconds by default. Keep
this host's clock close to the server's.

Grouper hands the key out as bare base64 with no PEM header, despite what its
wiki says. Both that form and a PEM block (PKCS#1 or PKCS#8) are accepted, so
paste it however you have it. The key must not be passphrase protected.

Grant the entity the Grouper privileges it needs, and add it to any group named
by `ws.client.user.group.name` in `grouper-ws.properties`, or every call comes
back 401.

`cryptography` has to be importable by the **interpreter the module runs under**,
which is the target host's Python, not the controller's. Running these modules
against `localhost` with a bare system Python is enough to hit this, even though
ansible-core itself depends on `cryptography`. Set `ansible_python_interpreter`
to the environment that has it if the module reports the library missing.

For a **trusted authority** deployment, use that authority's
`jwtTrusted_<configId>_` prefix and name the subject through `jwt_claims`:

```yaml
jwt_prefix: "jwtTrusted_myAuthority_"
jwt_private_key_path: /etc/grouper/authority.key
jwt_claims:
  subjectSourceId: jdbc
  subjectId: banderson
```

Rather than repeat the connection on every task, set it once with
`module_defaults`. This collection ships an action group for exactly this:

```yaml
- hosts: localhost
  gather_facts: false
  module_defaults:
    group/grouper.ws.all:
      ws_url: "{{ grouper_ws_url }}"
      username: "{{ grouper_ws_username }}"
      password: "{{ grouper_ws_password }}"
  tasks:
    - grouper.ws.stem:
        name: app:hr
        description: Human Resources
```

### About `api_version`

The version in the request path is the **client** version, not the server's.
Grouper only warns when the client version is *newer* than the server, so a
value at or below your server version is always safe. The default is
`v6_0_000`. Lower it to match an older deployment:

```yaml
api_version: v2_6_000
```

### TLS

`validate_certs: false` is available for development stacks with self-signed
certificates. Prefer pointing `ca_path` at the issuing CA.

## Idempotency

`stem` and `group` do not guess. Grouper's `stemSave` and `groupSave` report
per-item result codes, and the modules report `changed` directly from them:

| Grouper result code | `changed` |
| --- | --- |
| `SUCCESS_INSERTED` | yes |
| `SUCCESS_UPDATED` | yes |
| `SUCCESS_NO_CHANGES_NEEDED` | no |

The code is returned as `result_code` so playbooks can assert on it.

**Only what you declare is managed.** Each module reads current state first and
writes back any managed field you did not specify. Omitting `description` from
a task leaves the existing description alone rather than blanking it, so a
folder documented by hand in the UI survives a playbook run.

All modules support check mode and diff mode.

## Examples

### Folders and groups

```yaml
- name: Build the HR folder tree
  grouper.ws.stem:
    name: app:hr:groups
    display_extension: Groups
    description: Groups owned by Human Resources

- name: Create an empty group
  grouper.ws.group:
    name: app:hr:groups:employees
    display_extension: Employees
    description: All active employees, loaded from the HR warehouse

- name: Create a role
  grouper.ws.group:
    name: app:hr:roles:approver
    type_of_group: role
```

Parent folders are created automatically; set `create_parents: false` to
require that they already exist.

`type_of_group` only applies at creation. Grouper cannot convert a group into a
role afterwards, so the module warns and ignores the setting if the object
already exists as something else.

### A SQL loader driving one group

```yaml
- name: Load employees from the HR warehouse
  grouper.ws.loader:
    group: app:hr:groups:employees
    type: SQL_SIMPLE
    sql:
      database: grouper
      schedule_type: CRON
      quartz_cron: "0 0 7 * * ?"
      query: >-
        select net_id as SUBJECT_ID
        from hr_employee
        where status = 'A'
```

### A SQL loader building a tree of groups

```yaml
- name: Build one group per department
  grouper.ws.loader:
    group: app:hr:groups:departments
    type: SQL_GROUP_LIST
    purge_unmanaged: true
    sql:
      database: grouper
      schedule_type: START_TO_START_INTERVAL
      interval_seconds: 3600
      groups_like: "app:hr:groups:departments:%"
      query: >-
        select net_id as SUBJECT_ID,
               'app:hr:groups:departments:' || dept_code as GROUP_NAME
        from hr_employee where status = 'A'
      group_query: >-
        select 'app:hr:groups:departments:' || dept_code as GROUP_NAME,
               dept_name as GROUP_DISPLAY_NAME
        from hr_department
```

### An LDAP loader

```yaml
- name: Load staff from an LDAP group object
  grouper.ws.loader:
    group: app:ldap:groups:staff
    type: LDAP_SIMPLE
    ldap:
      server_id: personLdap
      quartz_cron: "0 15 * * * ?"
      search_dn: ou=groups
      filter: "(cn=staff)"
      subject_attribute: hasMember
      subject_id_type: subjectIdentifier
```

## Loader types

| Type | Settings key | Drives |
| --- | --- | --- |
| `SQL_SIMPLE` | `sql` | This group only |
| `SQL_GROUP_LIST` | `sql` | Many groups from one query |
| `LDAP_SIMPLE` | `ldap` | This group only |
| `LDAP_GROUP_LIST` | `ldap` | Many groups from one search |
| `LDAP_GROUPS_FROM_ATTRIBUTES` | `ldap` | Many groups, one per attribute value |

The group must already exist; create it with `grouper.ws.group` first.

Required settings are validated locally, before any call to Grouper, and the
module names exactly what is missing. Settings that a given loader type does
not accept are rejected rather than silently written — for example
`group_query` on a `SQL_SIMPLE` loader, which only makes sense when one job
drives many groups.

### Getting the job scheduled

Writing the definition is not the same as scheduling the job, and this
collection can only do the first.

Grouper turns loader definitions into Quartz jobs in
`GrouperLoader.scheduleJobs()`, which runs **only when the loader daemon
starts**. No built-in daemon job rescans for definitions added afterwards. A
loader attached by this module is therefore complete and valid in the
database, but has no scheduler job yet, and the UI will report it as not
enabled.

There is no way to fix that from here: the Grouper Web Services API exposes no
loader, daemon or scheduling operation at all. Pick one of these instead:

- **Restart the Grouper loader daemon.** Usually the right answer for a
  playbook driven workflow, and it picks up every pending definition at once.
- **Open the group's Loader tab in the UI and save it.** The UI's save calls
  `validateAndScheduleSqlLoad` / `validateAndScheduleLdapLoad` directly and
  schedules that one job.
- **Use GSH**, which runs inside Grouper and can reach the scheduler.

One distinction worth knowing when reading the UI: its **Enable** and
**Disable** buttons are Quartz `resumeJob` and `pauseJob` against an *already
scheduled* job. A job this module has just defined is not paused — it does not
exist in the scheduler at all. Same symptom, different cause.

### `purge_unmanaged`

By default the module manages only the settings named in the task and leaves
any others in place. That is usually right, but it means switching a loader
from a cron schedule to an interval leaves the old `quartz_cron` behind, where
Grouper may still honour it.

Set `purge_unmanaged: true` to remove loader settings that exist but are not
declared. Only attributes in that loader's own namespace are ever touched.

### Where loader settings actually live

Worth knowing when debugging in the Grouper UI, because the two loader
families are stored in completely different places, and in both cases the
settings hang off the marker assignment rather than off the group:

- **SQL** uses the legacy attribute framework. The group carries the group type
  `etc:legacy:attribute:legacyGroupType_grouperLoader`, and each setting is an
  attribute such as
  `etc:legacy:attribute:legacyAttribute_grouperLoaderQuery` assigned *on that
  group type assignment*.
- **LDAP** uses the modern attribute framework. The group carries the marker
  `etc:attribute:loaderLdap:grouperLoaderLdap`, and each setting is an attribute
  such as `etc:attribute:loaderLdap:grouperLoaderLdapFilter` assigned *on that
  marker assignment*.

If your site has retuned `grouper.attribute.rootStem` or
`legacyAttribute.baseStem`, override `attribute_root_stem` or
`legacy_attribute_stem` to match.

## JEXL scripted groups

Grouper can compute a group's membership from a JEXL script evaluated against
every entity — its attribute based access control. `grouper.ws.jexl_script`
attaches that script to a group:

```yaml
- name: Create the group the script will drive
  grouper.ws.group:
    name: app:vpn:groups:allowed
    description: Staff who are not locked out, computed by Grouper

- name: Compute membership from other groups
  grouper.ws.jexl_script:
    group: app:vpn:groups:allowed
    script: >-
      ${entity.memberOf('ref:staff') && !entity.memberOf('ref:lockout')}
```

As with loaders, the group must exist first, and the module never touches
membership itself: Grouper's JEXL daemons own it.

**No scheduling step.** Unlike a SQL or LDAP loader, a script takes effect
without a daemon restart. The `grouperLoaderJexlScriptIncremental` change log
consumer, every minute by default, recalculates a group as soon as its script
changes, and the daily `grouperLoaderJexlScriptFullSync` job rescans them all.

**One loader per group.** Grouper drives a group from one loader at a time. The
UI swaps them by removing the old one, which this collection never does, so
`jexl_script` refuses a group that already has a SQL or LDAP loader, and
`loader` refuses a group that already has a script. Remove the old definition
in the UI first.

**`subject_source_ids`** chooses which subject sources the script is evaluated
over. Omit it to leave the stored value alone, or pass `[]` to go back to the
global default sources. Grouper only honours it when per group overrides are
enabled and every id is in its list of available sources; otherwise it quietly
uses the defaults.

**The UI's checks do not apply.** The Loader tab analyses a script, shows how
many members it would produce, and enforces configured maximum membership
sizes. All of that is UI only, and Grouper accepts almost any script written
through web services. A script that does not parse is only reported later, by
the daemon. Try a new script in the UI before rolling it out.

Writing a script needs permission to assign the attributes under
`etc:attribute:abacJexlScript`, which usually means a wheel group member. The
group carries the marker
`etc:attribute:abacJexlScript:grouperJexlScriptMarker`, and the script is an
attribute assigned *on that marker assignment*, the same shape as an LDAP
loader. That stem comes from `grouper.rootStemForBuiltinObjects`, not
`grouper.attribute.rootStem`; override `jexl_script_stem` if your site has
retuned it.

## Acting as another subject

Where the authenticated account is permitted to, requests can be made on behalf
of another subject:

```yaml
act_as_subject_id: banderson
act_as_subject_source_id: ldap
```

## Development

The collection has to sit at `ansible_collections/grouper/ws` for
`ansible-test` to find it:

```bash
mkdir -p /tmp/ac/ansible_collections/grouper
cp -r ansible-collection-grouper-ws /tmp/ac/ansible_collections/grouper/ws
cd /tmp/ac/ansible_collections/grouper/ws
```

Sanity and unit tests need no Grouper server:

```bash
ansible-test sanity --python 3.14
ansible-test units --python 3.14
```

Integration tests do. Copy the template and fill it in:

```bash
cp tests/integration/integration_config.yml.template \
   tests/integration/integration_config.yml
ansible-test integration --python 3.14 stem group loader jexl_script
```

Each run writes into a fresh, timestamped folder under `grouper_test_stem`.
Because nothing in this collection deletes anything, **those folders accumulate
and must be removed by hand.**

The LDAP loader target is skipped unless `grouper_test_ldap_server_id` names a
connection that really exists in `grouper-loader.properties`. Pointing it at one
that does not would leave the loader daemon logging errors on every run, with
no way to remove the definition using this collection.

The JEXL script target needs an account that can assign the
`etc:attribute:abacJexlScript` attributes. Set `grouper_test_jexl_script: false`
to skip it.

## Licence

GPL-3.0-or-later. See [COPYING](COPYING).
