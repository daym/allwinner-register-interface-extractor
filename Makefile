include config.mk
.PHONY: all

all: phase3_host.svd lib.rs

partsvol1/a.xml: $(PPRVOL1)
	mkdir -p partsvol1
	pdftohtml -nodrm -xml $< partsvol1/a >/dev/null
	# Invalid multibyte character
	sed -i -e 's;\xcb\xce\xcc\xe5;;' -e 's;\xce\xa2\xc8\xed\xd1\xc5\xba\xda;;' partsvol1/a.xml

phase2_result.py: partsvol1/a.xml extract.py
	./extract.py $< $(PPRVOL1) > "$@".new && mv "$@".new "$@"

phase3_host.svd: phase2_result.py phase3.py
	python3 phase3.py $< >$@.new && mv $@.new $@

lib.rs: phase3_host.svd partsvol1/a.xml Makefile
	svd2rust --target "$(subst CA53,none,$(subst CA7,none,$(subst RISC,riscv,$(subst XuanTie C906 RISC-V CPU,riscv,$(shell xmllint --xpath 'string(/device/cpu/name)' $<)))))" -i phase3_host.svd

clean:
	rm -rf partsvol1

distclean: clean
	rm -f phase3_host.py
	rm -f phase2_result.py
