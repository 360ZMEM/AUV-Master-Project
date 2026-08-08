LATEXMK ?= latexmk
DEFENSE = auv-defense
DEFENSE_AUX = $(addprefix $(DEFENSE).,aux bbl blg fdb_latexmk fls log nav out snm synctex.gz toc xdv)

.PHONY: beamer beamer-en defense preview-defense doc clean clean-defense distclean-defense cleanall

beamer:
	pdflatex -synctex=1 -interaction=nonstopmode main
	bibtex main
	pdflatex -synctex=1 -interaction=nonstopmode main
	pdflatex -synctex=1 -interaction=nonstopmode main

beamer-en:
	pdflatex -synctex=1 -interaction=nonstopmode main-en
	bibtex main-en
	pdflatex -synctex=1 -interaction=nonstopmode main-en
	pdflatex -synctex=1 -interaction=nonstopmode main-en

defense:
	python3 ../tools/sync_latex_references.py --check
	$(LATEXMK) -xelatex -interaction=nonstopmode -halt-on-error $(DEFENSE).tex

preview-defense: defense
	$(MAKE) clean-defense

doc:
	xelatex thubeamer.dtx
	makeindex -s gind.ist -o thubeamer.ind thubeamer.idx
	makeindex -s gglo.ist -o thubeamer.gls thubeamer.glo
	xelatex thubeamer.dtx
	xelatex thubeamer.dtx

clean:
	rm -f *.toc *.bbl *.blg *.out *.aux *.log *.bak *.thm *.synctex.gz *.fdb_latexmk *.fls *.glo *.gls *.idx *.ilg *.ind *.nav *.snm *.hd

clean-defense:
	$(LATEXMK) -c $(DEFENSE).tex
	-@$(RM) $(DEFENSE_AUX)

distclean-defense:
	$(LATEXMK) -C $(DEFENSE).tex
	-@$(RM) $(DEFENSE_AUX) $(DEFENSE).pdf

cleanall:
	rm -f *.toc *.bbl *.blg *.out *.aux *.log *.bak *.thm *.synctex.gz *.fdb_latexmk *.fls *.glo *.gls *.idx *.ilg *.ind *.nav *.snm *.hd *.sty *.ins
