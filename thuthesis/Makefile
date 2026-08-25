# Makefile for ThuThesis

PACKAGE = thuthesis
THESIS  = thuthesis-example
AUV_THESIS = auv-thesis
AUV_THESIS_AUX = $(addprefix $(AUV_THESIS).,aux bbl bcf blg fdb_latexmk fls lof log lot out run.xml synctex.gz toc xdv)

SOURCES = $(PACKAGE).ins $(PACKAGE).dtx
CLSFILE = dtx-style.sty $(PACKAGE).cls

LATEXMK = latexmk

# Native Windows GNU Make otherwise bypasses the Cygwin shell and cannot run
# Cygwin's extensionless awk shim in the post-build gate.
ifdef SystemRoot
	SHELL := C:/cygwin64/bin/bash.exe
	AWK = awk
	THESIS_LOG_CHECK = powershell.exe -NoProfile -Command "if (Select-String -Path '$(AUV_THESIS).log' -Pattern 'Undefined control sequence|Citation .* undefined|Reference .* undefined|There were undefined references|Rerun to get cross-references right|Please \(re\)run Biber' -Quiet) { Select-String -Path '$(AUV_THESIS).log' -Pattern 'Undefined control sequence|Citation .* undefined|Reference .* undefined|There were undefined references|Rerun to get cross-references right|Please \(re\)run Biber'; exit 1 }"
else
	SHELL := /usr/bin/env bash
	AWK = awk
	THESIS_LOG_CHECK = $(AWK) 'BEGIN { failed = 0 } /Undefined control sequence|Citation .* undefined|Reference .* undefined|There were undefined references|Rerun to get cross-references right|Please \(re\)run Biber/ { print; failed = 1 } END { exit failed }' $(AUV_THESIS).log
endif

# make deletion work on Windows
ifdef SystemRoot
	RM = del /Q
else
	RM = rm -f
endif

.PHONY: all all-dev clean clean-auv-thesis distclean-auv-thesis preview-auv-thesis distclean dist thesis auv-thesis viewthesis viewauvthesis doc viewdoc cls check save test FORCE_MAKE

thesis: $(THESIS).pdf

auv-thesis: $(AUV_THESIS).pdf

preview-auv-thesis: auv-thesis
	$(MAKE) clean-auv-thesis

all: thesis

all-dev: doc all

cls: $(CLSFILE)

$(CLSFILE): $(SOURCES)
	xetex $(PACKAGE).ins

doc: $(PACKAGE).pdf

$(PACKAGE).pdf: cls FORCE_MAKE
	$(LATEXMK) $(PACKAGE).dtx

$(THESIS).pdf: cls FORCE_MAKE
	$(LATEXMK) $(THESIS)

# The maintained AUV thesis sources are the TeX files under thuthesis/data/
# and ref/auv-references.bib.  Legacy Markdown migration/sync tools must never
# run implicitly here because they can overwrite newer thesis edits.
$(AUV_THESIS).pdf: cls FORCE_MAKE
	$(LATEXMK) $(AUV_THESIS)
	@test -s $(AUV_THESIS).pdf
	@$(THESIS_LOG_CHECK)

viewdoc: doc
	$(LATEXMK) -pv $(PACKAGE).dtx

viewthesis: thesis
	$(LATEXMK) -pv $(THESIS)

viewauvthesis: auv-thesis
	$(LATEXMK) -pv $(AUV_THESIS)

save:
ifeq ($(target),)
	bash testfiles/save.sh
else
	bash testfiles/save.sh $(target)
endif

test:
ifeq ($(target),)
	l3build check
else
	bash testfiles/test.sh $(target)
endif

clean:
	$(LATEXMK) -c $(PACKAGE).dtx $(THESIS) $(AUV_THESIS)
	-@$(RM) -rf *~ main-survey.* main-translation.* _markdown_thuthesis* thuthesis.markdown.*

clean-auv-thesis:
	$(LATEXMK) -c $(AUV_THESIS)
	-@$(RM) $(AUV_THESIS_AUX)

distclean-auv-thesis:
	$(LATEXMK) -C $(AUV_THESIS)
	-@$(RM) $(AUV_THESIS_AUX) $(AUV_THESIS).pdf

cleanall: clean
	-@$(RM) $(PACKAGE).pdf $(THESIS).pdf $(AUV_THESIS).pdf

distclean: cleanall
	-@$(RM) $(CLSFILE)
	-@$(RM) -r dist

check: FORCE_MAKE
ifeq ($(version),)
	@echo "Error: version missing: \"make [check|dist] version=X.Y.Z\""; exit 1
else
	@[[ $(shell grep -E -c '$(version) Tsinghua University Thesis Template|\\def\\version\{$(version)\}' thuthesis.dtx) -eq 3 ]] || (echo "bump version with \"l3build tag\" before release"; exit 1)
endif

dist: check all-dev
	# use l3build for CTAN release (zip with .tds.zip)
	l3build ctan --config utils/build-ctan
	# use gulp for GitHub release (zip with generated file)
	python3 utils/create_release.py --version="v$(version)"
