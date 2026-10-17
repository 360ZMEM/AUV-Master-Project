# Documentation entry points; implementation and outputs remain in thuthesis/.
.PHONY: auv-thesis auv-middle-defense auv-middle-defense-main auv-middle-defense-school verify-thuthesis
auv-thesis auv-middle-defense auv-middle-defense-main auv-middle-defense-school verify-thuthesis:
	$(MAKE) -C thuthesis $@
