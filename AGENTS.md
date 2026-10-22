# Working on this collection

Ansible collection `grouper.ws`, managing Internet2 Grouper through the
`grouper-ws` REST API.

## Naming

Renamed from `grouper.core` before 0.1.0 shipped, so the collection is named
after its transport. A separate `grouper.gsh` collection may follow later.
Collection names must be Python identifiers (so `grouper-api` is invalid), and
`ws` was chosen over `api` because it matches Grouper's own component name and
GSH is itself API access. If `grouper.gsh` is built, it covers only what WS
cannot do (loader scheduling, daemon operations). It must not duplicate
stem/group/loader management, and the scope rules below apply to it too.

## Scope rules that are decisions, not omissions

Do not "helpfully" add these. Each was chosen deliberately; if a change seems
to need one, raise it rather than implementing it.

- **No membership management.** No module adds or removes group members. The
  user was explicit: this must never be an option. Membership belongs to
  loaders, provisioners and people, and a converging playbook would fight them.
- **No deletion.** No `state: absent`, no `stemDelete`/`groupDelete`. Group
  deletion destroys memberships and privileges. The same goes for loader
  definitions, JEXL scripts and inherited-privilege rules, which is why
  `inherited_privilege` refuses an empty list instead of removing the rule.
- **Privilege grants are the one exception, by the user's choice.**
  `grouper.ws.privilege` is *exact per subject*: it revokes that subject's
  unlisted direct privileges, and `[]` revokes them all. It never touches
  another subject. Do not widen this to other subjects (no
  `replaceAllExisting`), and do not extend it to rules.
- **No member privilege.** The user listed MEMBER among group privileges.
  Grouper has none (`AccessPrivilege.java`), and granting membership is
  membership management, so it was dropped with the user's agreement.
- **No on-demand loader runs.** The module writes the definition; Grouper's
  daemon decides when to act.
- **Only declared attributes are managed.** Every module reads current state
  and writes back managed fields the task did not specify, so omitting
  `description` never blanks an existing one. Keep this property when adding
  fields.

## Grouper API facts that cost real effort to establish

All of the following were read out of the Grouper source tree
(`github.com/Internet2/grouper`), not from memory. Re-verify against source.

Two things make that much easier than it looks:

- The default branch is **`GROUPER_6_BRANCH`**, not `master`. `raw.githubusercontent`
  paths under `master` return 404, which reads like a wrong path rather than a
  wrong branch.
- The wiki still returns HTTP 403 to automated fetches, but the repo **mirrors it**
  under `grouper-misc/grouper-docs/wikiMirror/spaces/Grouper/...` as Markdown. Fetch
  the mirror instead of fighting the 403.

`gh api search/code -f q='<term> repo:Internet2/grouper'` finds the file; `curl`
on `raw.githubusercontent.com/Internet2/grouper/GROUPER_6_BRANCH/<path>` reads it.

### Idempotency comes from Grouper

`stemSave` and `groupSave` return a **per-item** `resultMetadata.resultCode` of
`SUCCESS_INSERTED`, `SUCCESS_UPDATED` or `SUCCESS_NO_CHANGES_NEEDED`
(`WsStemSaveResult.java`). `changed` is derived from that, not from a local
diff. `save_changed()` in `plugins/module_utils/grouper.py` owns the mapping.

Check mode has no result code, so it must predict one locally, and the
prediction has to match Grouper's own comparison or check mode reports changes
that a real run never makes. `StemSave`/`GroupSave` compare the description
**trimmed** (`StringUtils.trim`, ~`GroupSave.java:870`, `StemSave.java:563`) and
the display extension exactly, and the WS layer passes values through
untrimmed. A whitespace-only difference is therefore never written and never
converges. `save_needed()` mirrors this; keep the two in step. Modules that
report the local diff in both modes (loader, jexl_script, inherited_privilege)
cannot show this split, but `privilege` can: check mode trusts the
getMemberships read, a real run trusts the assign result codes.

### Loader settings are assignments *on an assignment*

This is the single most important detail, and the easiest to get wrong. For
both loader families the marker is assigned to the **group**, and every
individual setting is assigned to the **marker assignment**, with
`attributeAssignType: group_asgn`.

Evidence: `Group.getAttributeValue()` resolves values via
`value.getAttributeAssign().getOwnerAttributeAssign()`, and
`GrouperLoader.runJobOnceForGroup()` reads the LDAP type through
`attributeAssign.getAttributeValueDelegate().retrieveValueString(...)` on the
marker assignment.

Two different frameworks, from `grouper.base.properties`:

| | SQL (`SQL_SIMPLE`, `SQL_GROUP_LIST`) | LDAP (`LDAP_*`) |
| --- | --- | --- |
| Marker | `etc:legacy:attribute:legacyGroupType_grouperLoader` | `etc:attribute:loaderLdap:grouperLoaderLdap` |
| Setting | `etc:legacy:attribute:legacyAttribute_grouperLoaderQuery` | `etc:attribute:loaderLdap:grouperLoaderLdapFilter` |
| Source of names | `GrouperLoader.java` constants | `LoaderLdapUtils.java` `ATTR_DEF_EXTENSION_*` |

Prefixes come from `legacyAttribute.groupType.prefix` (`legacyGroupType_`),
`legacyAttribute.attribute.prefix` (`legacyAttribute_`),
`grouper.attribute.rootStem` (`etc:attribute`) and `legacyAttribute.baseStem`
(`etc:legacy:attribute`). All are overridable per site, hence the
`attribute_root_stem` / `legacy_attribute_stem` module options.

The write is a single `assignAttributesBatch` call: entry 0 assigns the marker
to the group, every later entry references it with
`wsOwnerAttributeAssignLookup: {batchIndex: "0"}`. This works identically
whether the loader is new or being updated, which is why there is no
create/update branch.

### Required and allowed loader settings

Taken from `GrouperLoaderType#attributeRequired` / `#attributeOptional`, per
type, and encoded in `plugins/module_utils/loader_spec.py`. Two traps:

- `grouperLoaderLdapGroupDisplayExtensionExpression` appears in `LDAP_SIMPLE`
  only inside a comment reading `// not allowed:`. It is genuinely unsupported
  and does not exist in `LoaderLdapUtils`. Do not add it.
- `GrouperLoaderType` does **not** list `grouperLoaderGroupQuery`,
  `grouperLoaderGroupTypes` or `grouperLoaderGroupsLike` as optional for
  `SQL_GROUP_LIST`, but they are defined by the `grouperLoader` group type and
  are valid. `ALLOWED_OPTIONS` adds them back on purpose.

Group loader types are exactly these five: `SQL_SIMPLE`, `SQL_GROUP_LIST`,
`LDAP_SIMPLE`, `LDAP_GROUP_LIST`, `LDAP_GROUPS_FROM_ATTRIBUTES`.
`ATTR_SQL_SIMPLE` is owned by an attribute def, not a group, and `OTHER_JOB`,
`MAINTENANCE`, `CHANGE_LOG`, `MESSAGE_LISTENER`, `PSP_FULL_SYNC` are daemon
jobs. None of those belong in this module.

### Delete previously managed groups replaces `groups_like`

Added in Grouper 6.3.0 (GRP-7073/7074), as `delete_previously_managed_groups`.

- Names: `grouperLoaderDeletePreviouslyManagedGroups` (SQL, legacy prefix, in
  `GrouperLoader.java`) and `grouperLoaderLdapDeletePreviouslyManagedGroups`
  (`LoaderLdapUtils.java`). `attributeOptional` lists it only for `SQL_GROUP_LIST`,
  `LDAP_GROUP_LIST` and `LDAP_GROUPS_FROM_ATTRIBUTES`, the same set as `groups_like`.
- `syncGroupList` honours it **only while the like string is blank**, so the two are
  mutually exclusive. The UI save (`UiV2GrouperLoader` ~1780/~1831) blanks
  `groupsLike` when it is switched on. The user chose to do the same: `true` removes a
  stored `groups_like` in the same batch, even without `purge_unmanaged`
  (`implied_removals`). Both in one task is a validation error.
- The UI writes `T`, so the module writes `T`/`F` and normalises stored
  `true`/`false` before comparing (`normalize_current`).
- When blank it falls back to the global `loader.deleteGroupsNoLongerInSource`, so an
  explicit `false` is meaningful and is stored, not removed.
- Grouper deletes only groups carrying this loader's `loaderMetadata`. The module
  itself deletes nothing, so the no-deletion rule still holds.

### There is no way to schedule or enable a loader job over WS

Asked for, and checked properly: `GrouperServiceRest` exposes ~64 operations
and **not one** touches loaders, daemons, Quartz or scheduling. Do not add an
`enabled` / `schedule` / `run_now` option to `grouper.ws.loader`; it cannot
be implemented on this transport.

- Jobs are created in Quartz by `GrouperLoaderType.scheduleLoads()` /
  `scheduleLdapLoads()`, called from `GrouperLoader.scheduleJobs()`, which runs
  **only in `GrouperLoader.main()` at daemon startup**.
- The only other in-tree callers of `validateAndScheduleSqlLoad` /
  `validateAndScheduleLdapLoad` are the UI's
  `UiV2GrouperLoader.editGrouperLoaderSave`.
- `GrouperDaemonSchedulerCheck` (`otherJob.schedulerCheckDaemon`, every 30 min)
  only repairs stuck BLOCKED/ACQUIRED triggers. It does **not** rescan for new
  definitions. No other built-in `otherJob` does either.
- The UI's Enable/Disable buttons are `UiV2GrouperLoader.enableJob` /
  `disableJob`, which are Quartz `resumeJob` / `pauseJob` on an already
  scheduled job. `GrouperLoader.isJobEnabled()` reads Quartz trigger state, so
  "not enabled" for a freshly defined loader means *no trigger exists yet*,
  not *paused*.
- Assignments this collection writes come out `enabled=T`, verified on the
  live stack, so the definition side is genuinely complete.

Automating the scheduling step would need a second, non-WS transport (GSH over
SSH, a container exec, or a daemon restart handler). The user was offered that
and **chose to leave it documented only**, keeping the collection purely
WS-based with no extra dependencies. Do not reopen this without being asked.

### JEXL scripted (ABAC) groups

`grouper.ws.jexl_script`. Source of truth: `abac/GrouperAbac.java` (names),
`misc/GrouperCheckConfig.java` (attribute defs, ~2690 and ~4950), the UI save
in `UiV2GrouperLoader.java` (~1664), and the daemons
`GrouperLoaderJexlScriptFullSync` / `GrouperLoaderJexlScriptIncremental`.

- **Not a `GrouperLoaderType`**, which is why it is a separate module and not
  a sixth `loader` type. The UI calls it loader type `JEXL_SCRIPT`, but that
  string exists only in the UI.
- Same shape as LDAP: marker `grouperJexlScriptMarker` (def assignToGroup,
  marker) on the group, and `grouperJexlScriptJexlScript` /
  `grouperJexlScriptSubjectSourceIds` (def assignToGroupAssn, string, scoped
  to the marker) as `group_asgn` on it. `marker_assign.py` serves all three.
- The stem is `grouper.rootStemForBuiltinObjects` + `:attribute:abacJexlScript`,
  **not** `grouper.attribute.rootStem`. Hence `jexl_script_stem` is a separate
  option rather than reusing `attribute_root_stem`.
- `grouperJexlScriptJexlLastGroupSync` is written by the daemons. Never manage it.
- **No scheduling gap.** The incremental consumer (cron `0 * * * * ?`)
  recalculates on `ATTRIBUTE_ASSIGN_VALUE_ADD/DELETE` of the script or
  source-id attribute, and the full sync scans every marker. The loader
  "restart the daemon" caveat does not apply here.
- **Grouper validates nothing on write.** `GrouperAbac.validScript()` returns
  null before any check (the double-quote check after it is dead code), and
  `analyzeJexlScript()` trims and accepts the script with or without `${…}`.
  So the module only rejects a blank script. Do not add syntax checks that
  Grouper does not make.
- Source ids: the UI stores them sorted and joined with `", "` (TreeSet), and
  removes the attribute when they equal the global default.
  `effectiveSubjectSourceIds()` silently falls back to the defaults unless
  override is allowed and each id is available, and always strips
  `g:isa`/`g:gsa`. The module normalises before comparing.
- **One loader per group.** The UI removes the other marker when switching.
  The user chose to *refuse* instead, since we never delete. `jexl_script`
  checks for SQL/LDAP markers, and `loader` checks for the JEXL marker, each
  with a single `find_markers` call.
- WS bypasses UI-only checks: script analysis and the
  `maxAbacMembershipSizeForSubject` tiers.

### Privileges, verified from source and on the live stack

`grouper.ws.privilege` and `grouper.ws.inherited_privilege`. Name tables live in
`plugins/module_utils/privilege_spec.py`, rules in `rule_spec.py`.

- Names: `NamingPrivilege.java` (`stemAdmin`, legacy alias `stem`, `create`,
  `stemAttrRead`, `stemAttrUpdate`, `stemView`), `AccessPrivilege.java`
  (`admin`, `update`, `read`, `view`, `optin`, `optout`, `groupAttrRead`,
  `groupAttrUpdate`), and `AttributeDefPrivilege.java` (`attr*`, plus
  `attrDefAttrRead` / `attrDefAttrUpdate`).
- **Write** with `POST grouperPrivileges` / `WsRestAssignGrouperPrivilegesRequest`:
  a group or stem lookup (never both), `privilegeType` `access`/`naming`,
  `privilegeNames[]`, `allowed`. Per-item codes are `SUCCESS_ALLOWED`,
  `SUCCESS_ALLOWED_ALREADY_EXISTED`, `SUCCESS_NOT_ALLOWED`,
  `SUCCESS_NOT_ALLOWED_DIDNT_EXIST` and the two `*_EXISTS_EFFECTIVE` variants
  (`GrouperServiceLogic.assignGrouperPrivileges`). **Never send
  `replaceAllExisting`.** It revokes the privilege from every *other* subject.
- **Read with getMemberships, not getGrouperPrivilegesLite.** Ask for
  `fieldType` `access`/`naming` with `memberFilter: Immediate` and map
  `listName` (`readers`, `stemAdmins`, `creators`, …, from `Field.java`) back to
  the privilege. The lite call's `revokable` flag looks like "immediate" but
  is not reliable. `GrouperPrivilegeAdapter` carries `revoke` across loop
  iterations without resetting it, and on 6.5.0 direct grants to GrouperAll
  come back `revokable=F`.
- **Grouper refuses `admin`, `update` and `groupAttrUpdate` to GrouperAll**
  ("GrouperAll can't get a manage privilege"), as an HTTP 500 carrying the whole
  stack trace in `resultMessage`. `_extract_message` now condenses it, and
  `_condense_stack_trace` says each `Caused by` reason once.
- `getSubjects` does **not** return subjects in request order, so
  `resolve_subject` only ever asks for one.
- **Inherited privileges are rules.** `RuleApi.inheritGroupPrivileges` /
  `inheritFolderPrivileges` / `inheritAttributeDefPrivileges` call `addAttribute`
  for `<attribute root>:rules:rule` on the stem. That marker is multi-assign,
  so a new rule needs `add_attr`, because `assign_attr` would land on an existing
  one. The settings go on it as `stem_asgn`: act-as `g:isa`/`GrouperSystem`,
  `ruleCheckType` `stemCreate`/`groupCreate`/`attributeDefCreate`,
  `ruleCheckStemScope` `ONE`/`SUB`, `ruleThenEnum`
  `assign{Stem,Group,AttributeDef}PrivilegeTo…Id`, `ruleThenEnumArg0`
  `"sourceId :::: subjectId"`, `ruleThenEnumArg1` `", "`-joined, and the
  optional `ruleIfConditionEnum` `nameMatchesSqlLikeString` + arg0. All three
  check types honour the name pattern, in both firing and `runDaemon`.
- Write **exactly** that shape. `RuleSubjectActAs.allowedToActAs` lets a
  non-wheel caller act as GrouperSystem only for this shape, and only while
  `rules.allowActAsGrouperSystemForInheritedStemPrivileges` is on (the default).
- `ruleValid` is computed by `GrouperAttributeAssignValueRulesConfigHook` during
  the WS write, which also clears the rule engine cache. Verified: it reads `T`
  straight after the batch, and a group created over WS immediately afterwards
  received the privileges. The module reads `ruleValid` back and fails on
  anything but `T`, as `RuleApi.assertRuleValid` does.
- Existing children are **not** covered at write time. The UI calls
  `RuleApi.runRulesForOwner`, which WS lacks. They catch up when `otherJob.rules`
  runs (`0 0 7 * * ?`). Documented, not worked around.
- Packed subject strings (`SubjectFinder.findByPackedSubjectString`) use four
  colons for an id, six for an identifier, and eight for either. The longest
  separator is checked first.
- Updating an existing rule by `wsOwnerAttributeAssignLookup: {uuid: …}` works,
  and rewriting an unchanged value reports `changed: F`.

### JWT authentication, verified from source

Source of truth:
`grouper/src/grouper/edu/internet2/middleware/grouper/authentication/GrouperPublicPrivateKeyJwt.java`,
with dispatch in `GrouperServiceJ2ee.java` (~line 960) and verification in
`GrouperPassword.verify()`.

- The server matches the **whole header** against `^Bearer jwtUser_([^_]+)_(.*)$`.
  Because of `[^_]+`, the prefix segment is standard base64 with `=` padding,
  never base64url. `GrouperServiceJ2ee` dispatches on four literal prefixes:
  `jwtUser_`, `jwtTrusted_`, `oidc_`, `oidcWithRedirectUri_`.
- **`iat` is required** — `issuedAt == null` fails outright — and must satisfy
  `iat + grouper.selfService.jwt.maxValidTimeInSeconds >= now`, default 600s.
  `exp` is optional and only checked when present. Nothing else is read: the
  identity comes from the prefix, not the payload. Hence a JWT is signed per
  request, never cached.
- **Never send a `kid`.** `GrouperPassword.getPublicKeyById(keyId)` discards its
  argument and returns the entity's stored public key, so `kid` is pure
  decoration — but the Java example on the wiki implements `getPrivateKeyId()` as
  the private key string, so its published sample JWT has **the entire private
  key in the header**. Do not copy that example.
- **The key is PKCS#8, not PKCS#1.** The wiki tells you to add a
  `-----BEGIN RSA PRIVATE KEY-----` header, but the key Grouper downloads is
  base64 PKCS#8 DER (it starts `MIIEvgIBADANBgkqhkiG9w0BAQEFAASC`, and the
  generate example parses it with `PKCS8EncodedKeySpec`). Adding the PKCS#1
  header the wiki suggests produces a key that will not parse.
  `load_private_key()` in `plugins/module_utils/grouper_jwt.py` sidesteps this by
  accepting bare base64 and both PEM wrappers.
- **A bad JWT is a 401, but a bad *prefix* is a 500.** `GrouperServiceJ2ee` sends
  401 only when `decode()` returns **null** — bad signature, `exp` past, `iat`
  too old, IP not in the CIDR list, credential expired. When `decode()` **throws**
  the exception escapes as a 500 with a Tomcat stack trace, and that is what a
  prefix naming no member does: `MemberFinder.findByUuid(..., true)` raises
  `MemberNotFoundException` before the JWT is read at all. Verified on the live
  stack. `UNKNOWN_JWT_MEMBER_MARKERS` in `grouper.py` exists to turn that back
  into a sentence about `jwt_prefix`.
- `jwtTrusted_` (`GrouperTrustedJwt.java`) additionally reads a `subjectSourceId`
  claim plus one of `subjectId` / `subjectIdentifier` / `subjectIdOrIdentifier`,
  under claim names the authority's config chooses. The `jwt_claims` option
  covers this; there is no separate code path.

`no_log=False` is **not** needed on `jwt_private_key_path`. Ansible's `no_log`
name heuristic (`PASSWORD_MATCH` in `module_utils/basic.py`) only matches
`pass`/`password`/`passphrase`, in both 2.15 and 2.21 — not `key`, `secret` or
`token`. Checked, because the opposite is widely assumed.

### Enums, verified from source

- Schedule: `CRON`, `START_TO_START_INTERVAL`
- LDAP search scope: `OBJECT_SCOPE`, `ONELEVEL_SCOPE`, `SUBTREE_SCOPE`
- LDAP subject id type: `subjectId`, `subjectIdentifier`, `subjectIdOrIdentifier`
- Type of group: `group`, `role`, `entity`
- Exact-match filters: stems use `FIND_BY_STEM_NAME`, groups use
  `FIND_BY_GROUP_NAME_EXACT` (the stem enum has no `_EXACT` variant)
- Stem/group scope: `ONE_LEVEL`, `ALL_IN_SUBTREE`

### Request shapes

Everything is `POST {ws_url}/servicesRest/{api_version}/{resource}` with a
single-key envelope in and a single-key envelope out. `GrouperClient.post()`
handles wrapping, unwrapping, `WsRestResultProblem`, and the
`resultMetadata.success == 'T'` check.

The version in the path is the **client** version. Grouper warns only when it
exceeds the server version (`GrouperWsVersionUtils.assignCurrentClientVersion`),
so a lower value is always safe. Default is `v6_0_000`. The user's local
stack reported server version **6.4.0** and has since been upgraded to **6.5.0**; it accepts every client version
probed from `v2_5_000` to `v7_0_000` without complaint.

## Testing

`ansible-test` refuses to run unless the collection sits at a real
`ansible_collections/grouper/ws` path — a symlink does not work, because the
path is resolved before the check. Copy or rsync it:

```bash
rsync -a --delete --exclude .git --exclude tests/output --exclude __pycache__ \
  --exclude .env --exclude .venv --exclude venv \
  <repo>/ /tmp/ac/ansible_collections/grouper/ws/
cd /tmp/ac/ansible_collections/grouper/ws
ansible-test sanity --python 3.14
ansible-test units --python 3.14
```

**Exclude the virtualenv or sanity cannot run.** A venv in the repo root is
~22k files, and copying it makes `pep8` die with `OSError: [Errno 7] Argument
list too long` — which names the sanity venv's python, not the copied one, so it
reads like a broken install rather than a file-count problem. Same for
`tests/output` left behind by a previous run.

Both must stay green: 24 sanity tests, 222 unit tests as of the check-mode description fix.
Unit tests need `pytest`, `pytest-xdist`, `pytest-mock` and `cryptography` in
the venv (`tests/unit/requirements.txt` declares the last one).

Integration tests have been run green against the user's Grouper 6.4.0
stack: stem 28 ok, group 22 ok, loader 33 ok, 0 failed. The loader
structure was additionally verified by querying the assignments back
directly, confirming the marker sits on the group and every setting is a
`group_asgn` assignment owned by it.

`jexl_script` verified green against the same stack, run as the JWT entity:
38 ok, 10 changed, 0 failed, 3 deliberately ignored (blank script, and the
conflict refusal in each direction). Read back directly: marker on the group,
script as a `group_asgn` owned by it, both `enabled=T`.

`privilege` and `inherited_privilege` verified green against the 6.5.0 stack,
run as the JWT entity. `privilege` gave 37 ok, 11 changed, 0 failed and 3
deliberately ignored (a group-only privilege on a stem, an unknown subject,
and GrouperAll refused `admin`). `inherited_privilege` gave 28 ok, 9 changed,
0 failed and 1 ignored (the empty list). In the same session `jexl_script`
(38 ok), `loader` (35 ok) and `stem` (30 ok) were re-run green after the
`marker_assign` refactor. Their group extensions carry the run id, so they do
not trip the veto below.

**The user's stack has `veto.group.unique.extension` enabled**, so a group
*extension* must be unique site-wide, not just within its folder. Targets that
create fixed extensions (`group`, `jexl_script`: `source`, `target`,
`sqlloaded`) fail with `HookVeto` on a second run until earlier run folders
are deleted. That is the environment, not a regression.

Integration tests need a live Grouper and a filled-in
`tests/integration/integration_config.yml` (gitignored). They write into a
fresh timestamped folder per run and **cannot clean up after themselves**,
since the collection has no delete. Say so when reporting results.

`setup_grouper` creates that folder with basic auth whenever
`grouper_ws_username` is set, JWT only otherwise. So a stale password blocks
every target including `jwt_auth`, even when the JWT credential is perfectly
good. Comment the username and password out to run the suite as the entity,
which then needs CREATE on `grouper_test_stem`.

`jwt_auth` verified green against the 6.4.0 stack: 19 ok, 3 changed, 0 failed,
1 deliberately ignored (the expired-JWT case, which must 401).

## Gotchas already hit

- **Colon-space in doc YAML.** `C(Authorization: Bearer <token>)` in a
  `DOCUMENTATION` string is a YAML parse error. A colon with no following space
  is fine. `validate-modules` reports this as an opaque scanner error, so check
  the doc blocks first.
- **`validate-modules` requires a GPLv3 header** in the first 20 lines of every
  module. The collection is therefore GPL-3.0-or-later, matching the Ansible
  ecosystem norm, not the Apache-2.0 it started as.
- **`attributes:` in DOCUMENTATION needs a `description`** for each of
  `check_mode` and `diff_mode`, not just `support`.
- **pylint sanity bans `_` as a variable name.** Use `unused_x`.
- **`changelogs/config.yaml` must exist** or the `changelog` sanity test fails.
- **Integration targets are roles, so Ansible's reserved variable names win.**
  A block var named `role_name` silently became the string `group` (the role's
  own name), and the module then tried to save a group literally called
  `group`. `register: roles` collides the same way. Prefix test variables
  (`test_group_name`, `found_roles`) and check new ones against
  `ansible.vars.reserved.get_reserved_names()`.
- **`failed_when: false` makes `is failed` permanently false.** Asserting that
  a task was rejected needs `ignore_errors: true`; with `failed_when: false`
  the assertion can never fire and the test passes vacuously.

## Local stack

`https://localhost:1443/grouper-ws` is the user's development deployment; the
UI at `https://localhost/grouper` returns a JSP error but the web service
itself is healthy. It uses a self-signed certificate, so
`validate_certs: false`.
