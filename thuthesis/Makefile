# Makefile for ThuThesis

PACKAGE = thuthesis
THESIS  = thuthesis-example
AUV_THESIS = auv-thesis
AUV_THESIS_AUX = $(addprefix $(AUV_THESIS).,aux bbl bcf blg fdb_latexmk fls lof log lot out run.xml synctex.gz toc xdv)

SOURCES = $(PACKAGE).ins $(PACKAGE).dtx
CLSFILE = dtx-style.sty $(PACKAGE).cls

LATEXMK = latexmk
SHELL  := /usr/bin/env bash

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

$(AUV_THESIS).pdf: cls FORCE_MAKE
	python3 ../tools/migrate_thesis_chapters.py --check
	python3 ../tools/sync_latex_references.py --check
	$(LATEXMK) $(AUV_THESIS)

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
