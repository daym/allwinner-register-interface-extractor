R40 NDFC.NDFC_USER_DATAn is now completely missing. Why?
^ WARNING:root:'NDFC_USER_DATAn': Offset2 is too complicated: 'Offset: 0x0050+ N*0x04', ['Offset: 0x0050 + N*0x04']

OK: Debug on TCON0_FRM_TAB_REG why it doesn't detect an one-off array and fucks up addressOffset

Detect "format is 3.24." and similar.

Test with TCON_CEU_COEF_MUL_REG (N=0,1,2,4,5,6,8,9,10), which also misses array (but is more complicates in that it falls outside of a cluster that would exist)

D1 CER PWM might be a bitfield!
A64: AC (peripheral) has AC_ADC_DAPLAT, not anymore

See *_offsets for the to-be arrays/clusters.
!!! Offset ambiguous: MP_OCSC_URCOEF D0 vs E0 in R40

Find arrays that are NOT inferring an entire cluster.

Test sets
	A64 USB_HCI1 is missing the "part" headers
		Reason: Misparsing of the first part header by extract.py (possibly not fixable); Skipping of the other part headers entirely by extract.py (because they don't start at table_left)
		Solution: Complete those. But also, the register names are all wrong.
	Multiple clusters for one register (totally normal):
		TSD_CTLR for TSD0, TSD1
		Inside each of those, find (common) instances.
	instances, N and none, no subclusters:
		PWM, DMA, PIO, NDFC (NDFC_USER_DATAn missing on R40), MP (bad, INPUT vs OUTPUT have different sizes), CSI0 (only in detail), TVD, TVE_TOP (very good)
	instances, different sets:
		TCON_TOP is a different module with a subheader in the summary.
		TCON_LCD0 likewise.
		TCON_LCD1 likewise.
		TCON_TV0 likewise.
		TCON_TV1 likewise.
		TCON_TOP does not have any loopy things.
		TCON_LCD0,TCON_LCD1 have sporadic and very different loopy things.
		TCON_TV0,TCON_TV1 likewise.
		TVE_TOP (a peripheral):
			TVE (a cluster): only NONE
			TVE_TOP (a cluster): N in [0,1,2,3]
		TVE0
			TVE (a cluster): only NONE
			TVE_TOP (a cluster): N in [0,1,2,3]
		TVE1
			TVE (a cluster): only NONE
			TVE_TOP (a cluster): N in [0,1,2,3]
		What is the "TVE_TOP" peripheral? I guess that's okay, because we don't really handle groupings like "TV Encoder".

Instance checks:
	Register offsets must be unique

Clock Sources before Register List!
Maybe also External Signals.

3.1. Memory Mapping

R40:
	GP_DATA_REGn disappeared
	CAPTURE_RISE_REG etc disappeared
	GMAC_ADDR_LOWN disappeared
	TVD_ADC_CFG disappeared

R40 Clock Sources:
	Module List: TSC, TSG OFFSET, TSF0 OFFSET, ...
	Summary: Uses {TSC, TSG, TSF, TSD} " + 0x"...
	Register: Uses {TSC, TSG, TSF, TSD} " + 0x"...
	So evaluator needs to support TSC, TSCG, TSF, TSD; although if it's grouped, that could be revisited

D1 offsets: grep Offset phase2_result.py  |sort |uniq |sed -e 's;Offset:;;' |grep "[^'x0-9A-F ,]" >D1_offsets

|grep 'not used in any peripheral'
|grep 'automatically adding'
|grep "[A-Z]_</name>" phase3_host.svd

R40 indirect access

  The Audio Codec Analog Part is configured by the ADDA_PR_CFG_REG Register which definition is below.
  The ADDA_PR_RST bit can reset this register. ADDA_PR_CFG_REG defines the analog register address which we would
  control, and the ADDA_PR_RW decides the operation is to read or write. When the operation is to read, we would read
  the analog register's data from the ADDA_PR_RDAT. When the operation is to write, we would write the
  ADDA_PR_WDAT value to the ADDA_PR_CFG_REG register.

R40 register name subgroups (['#', foo]):
	phase3 needs to handle those (since the offsets are not unique otherwise)

A64 Table 3-6. Peripherals Security Feature Table

Move special-case "HcPeriodCurrentED(PCED)" from extract.py to phase3.py
Clean "Module_List" at strategic places (h3 is too early)

D1: "(Read)LocalPowerStatus" apparently not matched

register HMIC_CTRL1: weird long field names why? MDATA_Threshold_Debounce
Typo in original: "corase"

# Clean up

* enumeratedValue sometimes come twice--with differing level of detail!  Currently, both are emitted--which is not good.  The longer one should be preferred if it has any underscores in the result.

# Offset handling

* Offset: 0x0140+N*0x04(N=0,1,2)
* Offset: 0x0028+N*0x100(N=0~3)
  Name: CSI0_C0~3_BUF_CTL_REG
* WARNING:root:Offset is too complicated: 'Offset:'
* WARNING:root:Offset is too complicated: 'Offset: 0x0050+N*0x0100+P*0x0004 '
* WARNING:root:Offset is too complicated: 'Offset: 0x002C+N*0x04 (N=0~3)'
* 0x0060+N*0x0100+P*0x0004 (N=0–1)(P=0–3)
Example for offset handling (D1): PLIC_PRIO_REGn at 0x0000+n*0x0004 (0<n<256)
	that's only for one register
Example for bigger register field (D1):
	DMAC_EN_REGN: 0x0100 + N*0x0040
	DMAC_PAU_REGN: 0x0104 + N*0x0040
	DMAC_DESC_ADDR_REGN: 0x0108 + N*0x0040
	DMAC_CFG_REGN: 0x010C + N*0x0040
	...
	DMAC_PKG_NUM_REGN: 0x0130 + N*0x0040
Example for N and P and bigger field (D1):
	MSGBOX_RD_IRQ_EN_REG: 0x0020+N*0x0100 (N=0~1)
	MSGBOX_RD_IRQ_STATUS_REG: 0x0024+N*0x0100 (N=0-1)
	MSGBOX_FIFO_STATUS_REG: 0x0050+N*0x0100+P*0x0004 (N=0–1)(P=0–3)
	Example MSGBOX1: receiving message; RISC-V(writes) -msgbox1-> DSP(reads)
	Example MSGBOX2: transmitting message; DSP(writes) -msgbox2-> RISC-V(reads)
	CPU 1: DSP
	CPU 2: RISC-V
	Here, P is The channel numbers between two communication CPU. (this description is part of the document)
	Here, N is the CPU# that communicates with the current CPU (this description is part of the document)
		DSP has the msgbox where DSP receives things from the CPU at N = 1
		RISC-V has the msgbox where the RISC-V receives things from the DSP at N=1
		IRQ is common for all the channels (i.e. there are entries like "0x0020 + N * 0x0100" with NO "P" at all)
		Implicit:
			DSP:
				N = 1 receiving from there
				N = 0 sending over that
			RISC-V:
				N = 1 receiving from there
				N = 0 sending over that
		This should be collected into a cluster.
		Currently, there's NO cluster functionality at all.
		In order to do clustering, ensure:
			all N and P coefficients stay the same
			intercept addresses are close together (for that, need to figure out range and plug it)
			Alternative: Group together registers into register cluster dependent on respective "Register List" table
				(assuming the register names in that table are unique over the whole document)

# Errors in document

* ['3:2 ', '/ ', '/ ', 'DBI_TXCS  FSM for DBI Transmit  00: IDLE  01: SHIF  10: DUMY  11: READ '] cannot be accessed
* ASRCEN: Field name could not be determined: ['31:1 ', 'R ', '0x0 ', '/ ']
* ASRCMANCFG: Field name could not be determined: ['30:26 ', 'R ', '0x0 ', '/ ']
* ASRCRATIOSTAT: Field name could not be determined: ['31:30 ', 'R ', '0x0 ', '/ ']
* ASRCRATIOSTAT: Field name could not be determined: ['27:26 ', 'R ', '0x0 ', '/ ']
* FsinEXTCFG: Field name could not be determined: ['31:17 ', 'R ', '0x0 ', '/ ']
* MCLKCFG: Field name could not be determined: ['31:17 ', 'R ', '0x0 ', '/ ']

# Usability

* Fish out register description, too (it's before "Offset:" and bold and probably table-cell, not h4)
* Emit <alternateGroup>

# Inapplicable elements

* TODO: Maybe hide DSP_MSGBOX

# Allwinner R40

* ADDA_PR_CFG_REG maybe verify (seems mainly fine)
* NDFC_USER_DATAn(n=0~15) = Module_List
* HcRevision: It's split up for no reason!
  * See also (IMPORTANT! Sometimes this splits up one thing into two registers)
      grep "^[^']*=" phase2_result.py  |sort |uniq -d
* Some of the registers have an empty "fields" element.  Warn about that.
* svd2rust should unify one-bit types!
