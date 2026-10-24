# Documentation entry points; implementation and outputs remain in thuthesis/.
.PHONY: auv-thesis clean-auv-thesis distclean-auv-thesis auv-middle-defense auv-middle-defense-main auv-middle-defense-school verify-thuthesis
auv-thesis clean-auv-thesis distclean-auv-thesis auv-middle-defense auv-middle-defense-main auv-middle-defense-school verify-thuthesis:
	$(MAKE) -C thuthesis $@

# Isolated bibliography tooling; does not load ROS pytest plug-ins.
BIB_AUDIT_PYTHON ?= $(HOME)/.local/share/auv-bib-audit/venv/bin/python
BIB_AUDIT_OUT ?= docs/thesis/bibliography/20261022
.PHONY: bib-audit bib-audit-offline bib-audit-acceptance bib-audit-check test-bib-audit
bib-audit:
	$(BIB_AUDIT_PYTHON) tools/bib_audit.py --output $(BIB_AUDIT_OUT)
bib-audit-offline:
	$(BIB_AUDIT_PYTHON) tools/bib_audit.py --offline --output $(BIB_AUDIT_OUT)
bib-audit-acceptance:
	$(BIB_AUDIT_PYTHON) tools/check_bib_audit.py --report $(BIB_AUDIT_OUT) --compiled
bib-audit-check:
	$(BIB_AUDIT_PYTHON) tools/check_bib_audit.py --report $(BIB_AUDIT_OUT) --compiled --require-release-ready
test-bib-audit:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(BIB_AUDIT_PYTHON) -m pytest -q tests/test_bib_audit.py
