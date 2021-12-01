include config.mk
.PHONY: all

all: phase3_host.svd lib.rs

partsvol1/a.xml: $(PPRVOL1)
	mkdir -p partsvol1
	pdftohtml -nodrm -xml $< partsvol1/a >/dev/null
	# Invalid multibyte character
	sed -i -e 's;\xcb\xce\xcc\xe5;;' partsvol1/a.xml

phase2_result.py: partsvol1/a.xml extract.py
	./extract.py $< $(PPRVOL1) > "$@".new && mv "$@".new "$@"

phase3_host.svd: phase2_result.py phase3.py
	python3 phase3.py $< >$@.new && mv $@.new $@

lib.rs: phase3_host.svd
	svd2rust --target riscv -i phase3_host.svd

clean:
	rm -rf partsvol1

distclean: clean
	rm -f phase3_host.py
	rm -f phase2_result.py
