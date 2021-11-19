PPRVOL1 = D1_User_Manual_V0.1_Draft_Version.pdf
.PHONY: all

all: phase3_host.svd

partsvol1/a.xml: $(PPRVOL1)
	mkdir -p partsvol1
	pdftohtml -nodrm -xml $< partsvol1/a >/dev/null

phase2_result.py: partsvol1/a.xml extract.py
	./extract.py $< > "$@".new && mv "$@".new "$@"

phase3_host.svd: phase2_result.py
	python3 phase3.py $< >$@.new && mv $@.new $@

clean:
	rm -rf partsvol1

distclean: clean
	rm -f phase2_result.py
