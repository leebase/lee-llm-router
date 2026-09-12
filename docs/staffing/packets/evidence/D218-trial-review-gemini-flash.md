root agent idle; waiting for 2 background task(s) (bounded by --print-timeout)
Running the full test suite to check for any regressions across the repository.
Waiting for the test suite to complete...
Waiting for the full pytest suite to finish...
# Review Packet — D218-trial (`.json` owned-path extension in derive_class)

- **Author route**: `pi-deepseek-deepseek-v4-1-flash-openrouter` (attempt `router-run-98e00651d0914f31b533545670665075`)
- **Owned paths**: [`src/lee_llm_router/staffing/derive_class.py`](file:///home/lee/projects/lee-llm-router/src/lee_llm_router/staffing/derive_class.py), [`tests/test_staffing_derive_class.py`](file:///home/lee/projects/lee-llm-router/tests/test_staffing_derive_class.py)

---

## 1. Diff Inspection

Command executed:
```bash
git -C /home/lee/projects/lee-llm-router diff -- src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py
```

Output:
```diff
diff --git a/src/lee_llm_router/staffing/derive_class.py b/src/lee_llm_router/staffing/derive_class.py
index b24f938..e3aa06a 100644
--- a/src/lee_llm_router/staffing/derive_class.py
+++ b/src/lee_llm_router/staffing/derive_class.py
@@ -71,6 +71,7 @@ _EXTENSION_LANGUAGES = {
     ".sql": "sql",
     ".yaml": "yaml-config",
     ".yml": "yaml-config",
+    ".json": "yaml-config",
     ".md": "markdown",
     ".markdown": "markdown",
 }
diff --git a/tests/test_staffing_derive_class.py b/tests/test_staffing_derive_class.py
index 45604f5..32ab0b1 100644
--- a/tests/test_staffing_derive_class.py
+++ b/tests/test_staffing_derive_class.py
@@ -151,6 +151,40 @@ def test_keywords_match_owned_path_text(tmp_path: Path):
     assert payload["class"]["domain_tags"] == ["persistence"]
 
 
+def test_json_owned_path_maps_to_yaml_config(tmp_path: Path):
+    packet = tmp_path / "packet.md"
+    packet.write_text(
+        """\
+- Kind: impl
+- Declared size: 1 file, at most 40 changed lines
+- Owned paths: `config/staffing/schema/classes.schema.json`
+- Requirement: Update the schema.
+""",
+        encoding="utf-8",
+    )
+
+    derived = derive_class(packet, classes_path=CLASSES)
+
+    assert derived.language == "yaml-config"
+
+
+def test_json_alongside_yaml_stays_yaml_config(tmp_path: Path):
+    packet = tmp_path / "packet.md"
+    packet.write_text(
+        """\
+- Kind: impl
+- Declared size: 2 files, at most 40 changed lines
+- Owned paths: `config/llm.yaml`, `config/llm.json`
+- Requirement: Keep the two configs aligned.
+""",
+        encoding="utf-8",
+    )
+
+    derived = derive_class(packet, classes_path=CLASSES)
+
+    assert derived.language == "yaml-config"
+
+
 def test_explicit_domain_field_overrides_owned_path_matching(tmp_path: Path):
     packet = tmp_path / "packet.md"
     packet.write_text(
```

---

## 2. Verification Evidence

### Oracle Test Execution
```bash
cd /home/lee/projects/lee-llm-router && .venv/bin/python -m pytest -q tests/test_staffing_derive_class.py
```
Output:
```
......................                                                   [100%]
22 passed in 0.23s
```

### Full Test Suite
```bash
cd /home/lee/projects/lee-llm-router && .venv/bin/python -m pytest -q
```
Output:
```
1705 passed, 1 skipped in 129.54s (0:02:09)
```

### Linters and Formatters
```bash
cd /home/lee/projects/lee-llm-router && .venv/bin/black --check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py
```
Output:
```
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

```bash
cd /home/lee/projects/lee-llm-router && .venv/bin/ruff check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py
```
Output:
```
All checks passed!
```

### Live CLI Invocation
Executed `staff --from-packet` against a packet with owned path `config/staffing/schema/classes.schema.json`:
```bash
.venv/bin/python -m lee_llm_router.doctor staff --from-packet <(cat << 'EOF'
# Test packet
- Kind: impl
- Declared size: 1 file, at most 40 changed lines
- Owned paths: `config/staffing/schema/classes.schema.json`
- Requirement: Update the schema.
EOF
) --json
```
Output snippet demonstrating successful derivation without `PacketClassError`:
```json
{
  "mode": "auto",
  "authority": "policy",
  "role": "impl",
  "class_key": "impl/none/none/xs/yaml-config",
  "class_derivation": {
    "source": "packet",
    "kind": "impl",
    "owned_paths": [
      "config/staffing/schema/classes.schema.json"
    ],
    "class": {
      "class_key": "impl/none/none/xs/yaml-config",
      "role": "impl",
      "oracle_type": "none",
      "domain_tags": [],
      "size_band": "xs",
      "language": "yaml-config"
    }
  }
}
```

---

## 3. Checklist Verification

- **Only the one mapping added**: Yes, exactly `".json": "yaml-config"` was added to `_EXTENSION_LANGUAGES`.
- **No other extension, keyword, or function changed**: Confirmed; lines 71-74 in [`derive_class.py`](file:///home/lee/projects/lee-llm-router/src/lee_llm_router/staffing/derive_class.py#L71-L74) are the only modified lines in the source file.
- **Tests cover the `.json` case**: Confirmed; [`test_json_owned_path_maps_to_yaml_config`](file:///home/lee/projects/lee-llm-router/tests/test_staffing_derive_class.py#L154-L168) tests a standalone `.json` path, and [`test_json_alongside_yaml_stays_yaml_config`](file:///home/lee/projects/lee-llm-router/tests/test_staffing_derive_class.py#L171-L185) tests combined `.yaml` and `.json` paths.
- **No existing assertion weakened**: Confirmed; 2 new tests were added without editing or removing any existing test functions.
- **No new language value introduced**: Confirmed; `"yaml-config"` is one of the eight canonical language values in the closed taxonomy.

---

## 4. Finding Classification

### Contract-blocking Defects
None.

### Non-blocking Hardening Opportunities
- **Mixed language test coverage**: While `test_json_alongside_yaml_stays_yaml_config` verifies that two formats mapped to `"yaml-config"` stay `"yaml-config"`, adding a test verifying that `.json` combined with another language (such as `.py`) derives `"mixed"` would further harden multi-language resolution coverage.

### Future Concerns Outside This Packet
- **Additional configuration file extensions**: Other common configuration formats such as `.toml` or `.ini` are not currently present in `_EXTENSION_LANGUAGES`. If packets ever own such files, they will raise `PacketClassError` unless explicitly mapped into `"yaml-config"`.

---

REVIEW VERDICT: ACCEPT
