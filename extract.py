#!/usr/bin/env python3

from lxml import etree
import sys
import re
import os
import logging
logging.basicConfig(level=logging.INFO)
from logging import debug, info, warning, error, critical

re_digits = re.compile(r"^[0-9]+$")

fontspec_to_meaning = [
  # D1
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '32'}, "h0"),
  ({'color': '#000000', 'family': 'Arial', 'size': '23'}, "h2"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '18'}, "h3"), # "Register Description"
  ({'color': '#000000', 'family': 'Arial', 'size': '15'}, "h4"), # "0x0000 PLL_CPU Control Register (Default Value: 0x4A00_1000)"
  ({'color': '#0000ff', 'family': 'ABCDEE+Calibri', 'size': '15'}, "table-cell"), # really a register reference--but we don't care
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '15'}, "table-cell"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '16'}, "table-cell"), # D1 new version
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '13'}, "table-cell"), # used once
  ({'color': '#000000', 'family': 'Calibri', 'size': '120'}, "garbage"),

  # R40, A64
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '15'}, "h4"), # Note: A64 sometimes abuses this as h3
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '16'}, "h4"), # R40
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '90'}, "garbage"),
  ({'color': '#005ebd', 'family': 'ABCDEE+Calibri,Bold', 'size': '19'}, "h3"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '21'}, "h3"), # CPU Architecture
  ({'color': '#0f0f00', 'family': 'ABCDEE+Calibri,Bold', 'size': '21'}, "h3"), # Register List in A64
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '23'}, "h2"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '18'}, "h3-garbage-if-empty"), # Otherwise it throws off table header detection--and the text is empty anyway
  ({'color': '#000000', 'family': 'Times New Roman,BoldItalic', 'size': 15}, "garbage-if-empty"),
  ({'color': '#000000', 'family': 'Times New Roman', 'size': '15'}, "garbage-if-empty"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '36'}, "h0"),

  #V3s 
  ({'color': '#000000', 'family': 'SimSun', 'opacity': '0.298039', 'size': '88'}, "garbage"),
  ({'color': '#ff0000', 'family': 'ABCDEE+Calibri', 'size': '15'}, "garbage"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,BoldItalic', 'size': '15'}, "note"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Italic', 'size': '15'}, "garbage"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '14'}, "table-cell"), #MII_CMD

  #H3
  ({'color': '#000000', 'family': 'Calibri', 'opacity': '0.298039', 'size': '106'}, "garbage"),

  #H5
  ({'color': "#0f0f00", 'family': 'TMRLMS+Calibri,Bold', 'size': '21'}, "h3"),
  ({'color': "#000000", 'family': 'TMRLMS+Calibri,Bold', 'size': '27'}, "h2"),
  ({'color': "#000000", 'family': 'TMRLMS+Calibri,Bold', 'size': '15'}, "h4"),
  ({'color': "#000000", 'family': 'ESYINA+Calibri', 'size': '15'}, "table-cell"),
  ({'color': "#0000ff", 'family': 'TMRLMS+Calibri,Bold', 'size': '15'}, "table-cell"),
  ({'color': "#000000", 'family': 'CRTXUU+Calibri', 'size': '15'}, "table-cell"),
  ({'color': "#000000", 'family': 'EHFMCY+Calibri,Italic', 'size': '15'}, "table-cell"),
  ({'color': "#000000", 'family': 'TMRLMS+Calibri,Bold', 'size': '36'}, "h2")
]

def hashable_fontspec(d):
  result = tuple(sorted(d.items()))
  return result

def xdict(fontspec_to_meaning):
  return dict([(hashable_fontspec(k),v) for k, v in fontspec_to_meaning])

# Check for dupes
assert len(xdict(fontspec_to_meaning)) == len(fontspec_to_meaning)
fontspec_to_meaning = xdict(fontspec_to_meaning)

with open(sys.argv[1], encoding="UTF-8") as f:
  tree = etree.parse(f)

def quote(s):
  if s.startswith("3"):
    s = "_" + s
  return s.replace(" ", "_").replace("/", "_").replace("-", "_").replace("[", "_").replace("]", "_")

class State(object):
  def __init__(self):
    self.in_table = False
    self.in_table_header = False
    self.table_columns = []
    self.table_column_lefts = []
    self.table_left = 0
    self.offset = None
    self.in_offset = False
    self.h3 = None
    self.h4 = None
    self.page_number = None
    self.in_register_name_multipart = False
    self.table_header_autobolder = False
    self.prev_table_name = None
    self.all_table_names = set()
    self.in_module = None

  def fixed_table_name(self, rname):
    h4 = "" if not self.h4 else self.h4.split("(")[0].strip()
    rname = rname.split("(n=")[0] # "NDFC_USER_DATAn(n=0~15)" in R40
    if self.in_module and rname.startswith(self.in_module[:-2]): #bulk fix prefixes
        rname = rname.split("_")[1:]
        rname.insert(0, self.in_module)
        rname = "_".join(rname)     
    if h4.startswith("TSC Port Output Multiplex Control Register") and rname == "TSC_TSFMUXR": #H5
       rname = "TSC_OUTMUXR"    
    if h4.startswith("CSI Channel_0 Horizontal Size Register") and rname == "CSI0_C0_INT_STA_REG": #H5
       rname = "CSI0_C0_HSIZE_REG"
    if rname == "HcPeriodCurrentED(PCED)": # R40
        rname = "HcPeriodCurrentED" # FIXME
    rname = rname.replace("_C0~3", "") # in R40 # FIXME
    if rname == "LOMIXSC" and self.offset == "0x02": # Bug in R40: Uses the same register name twice for different offsets
        rname = "ROMIXSC"
    #elif rname == "DMA_IRQ_PEND_REG0" and self.offset == "0x0010": # Bug in R40: Actually, Offset 0x0010 is REG1 and not REG0 again.
    #  rname = "DMA_IRQ_PEND_REG0"
    elif h4 == "DMA IRQ Pending Status Register 1" and rname == "DMA_IRQ_PEND_REG0" and self.offset == "0x0014": # Bug in R40: Actually, Offset 0x0014 is REG1 and not REG0 again.
        rname = "DMA_IRQ_PEND_REG1"
    elif h4 == "ADDA_PR Configuration Register" and rname == "ADDA_PR_CFG_REG" and self.offset == "0x0300": # Bug in R40: Actually, This is a duplicate.
        rname = "AC_PR_CFG"
    elif h4 == "KEYADC Data 0 Register" and rname == "KEYADC_DATA" and self.offset == "0x000C": # R40
        rname = "KEYADC_DATA0"
    elif h4 == "KEYADC Data 1 Register" and rname == "KEYADC_DATA" and self.offset == "0x0010": # R40
        rname = "KEYADC_DATA1"
    elif h4 == "PE Configure Register 3" and rname == "PE_CFG2" and self.offset == "0x009C" and h4 == "PE Configure Register 3": # R40
        rname = "PE_CFG3"
    elif h4 == "TCON1 Basic5 Register" and rname == "TCON1_BASIC4_REG" and self.offset == "0x00A8": # R40
        rname = "TCON1_BASIC5_REG"
    elif h4 == "OHCI Control Register" and rname == "HcRevision" and self.offset == "0x0404": # R40
        rname = "HcControl"
    elif h4 == "TSC Port Output Multiplex Control Register" and rname == "TSC_TSFMUXR" and self.offset == "0x0028": # R40
        rname = "TSC_OUTMUXR"
    elif h4 == "0x41C ADC DAP Left Low Average Coef Register" and rname == "AC_ADC_DAPLHAC" and self.offset == "0x41C": # A64
        rname = "AC_ADC_DAPLLAC"
    elif h4 == "0x434 ADC DAP Right Attack Time Register" and rname == "AC_ADC_DAPRDT" and self.offset == "0x434": # A64
        rname = "AC_ADC_DAPRAT"
    elif h4 == "0x440 ADC DAP Left Input Signal Low Average Coef Register" and rname == "AC_ADC_DAPLHNAC" and self.offset == "0x440": # A64
        rname = "AC_ADC_DAPLLNAC"
    elif h4 == "0x448 ADC DAP Right Input Signal Low Average Coef Register" and rname == "AC_ADC_DAPRHNAC" and self.offset == "0x448": # A64
        rname = "AC_ADC_DAPRLNAC"
    elif h4 == "0x698 DRC0 Smooth filter Gain Low Release Time Coef Register" and rname == "AC_DRC0_SFHRT" and self.offset == "0x698": # A64
        rname = "AC_DRC0_SFLRT"
    elif h4 == "0x798 DRC1 Smooth filter Gain Low Release Time Coef Register" and rname == "AC_DRC1_SFHRT" and self.offset == "0x798": # A64
        rname = "AC_DRC1_SFLRT"
    elif h4 == "CSI Channel_0 horizontal size Register" and rname == "CSI0_C0_INT_STA_REG" and self.offset == "0x0080": # A64
        rname = "CSI0_C0_HSIZE_REG"
    elif h4 == "TCON1 IO Polarity Register" and rname == "TCON1_IO_POL_REG" and self.offset == "0x00F4": # A64
        rname = "TCON1_IO_TRI_REG"
    elif h4 == "HcControl Register" and rname == "HcRevision" and self.offset == "0x404": # A64
        rname = "HcControl"
    elif h4 == "0x0010 DMAC IRQ Pending Status Register 0" and rname == "DMAC_IRQ_PEND_REG0" and self.offset == "0x0010": # D1
        rname = "DMAC_IRQ_PEND_REG0" # ok
    elif h4 == "0x0014 DMAC IRQ Pending Status Register 1" and rname == "DMAC_IRQ_PEND_REG0" and self.offset == "0x0010": # D1
        rname = "DMAC_IRQ_PEND_REG1"
        self.offset = "0x0014" # OOPS!
    elif h4 == "0x0028 THS Alarm Off Interrupt Status Register" and rname == "THS_ALARM_INTS" and self.offset == "0x0028": # D1
        rname = "THS_ALARM0_INTS"
    elif h4 == "TSC Status Register" and rname == "TSC_TSFMUXR" and self.offset == "0x20":
        pass
    elif rname == "TSC_TSFMUXR" and self.offset == "0x28": # h4 wrong; A64
        rname = "TSC_OUTMUXR"
    elif rname == "TSC_TSFMUXR" and self.offset == "TSG+0x00": # h4 wrong; A64
        rname = "TSG_CTLR"
    elif h4 == "Crypt Enable Register" and rname == "CRY_CONFIG_REG" and self.offset == "0x218": # A64
        rname = "CRY_ENABLE_REG"
    elif h4 == "PWM Control Register" and rname == "PWM_CTR_REG" and self.offset == "0x0060+N*0x20(N= 0~7)": # R40
        rname = "PWM_CONT_REG" # not counter
    elif h4 == "System Internal 32K Clock Auto Calibration Register" and rname == "INTOSC_CLK_AUTO_CALI_REG" and self.offset == "0x0314": # R40
        rname = "INTOSC_32K_CLK_AUTO_CALI_REG"
    elif model == "V3s":    
      if rname == "DA16CALI_DATA" and self.offset == "0x17": #V3s
          rname = "BIAS16CALI_DATA"
      if rname == "DA16CALI_SET" and self.offset == "0x18": #V3s
          rname = "BIAS16CALI_SET"    
      elif rname == "HSIC_STATUS" and self.offset == "0x824": #V3s
          rname = "HSIC_PHY_STATUS"
    if model in ["V3s", "H3"]:
      if rname == "SD_CTRL" and self.offset == "0x0044": #V3s H3
          rname = "SD_FUNS"                     
    if model == "H3":
      if rname == "PG_EINT_CFG":
        rname = "PG_EINT_CFG3_REG"                              
    return rname

  def start_table(self, rname):
      #print("RNAME", rname, file=sys.stderr)
      orig_rname = rname
      # TODO: The TCON_ (R40) and SPI_ (D1) are legitimately there multiple times. What to do with those?
      if (self.prev_table_name == rname or rname in self.all_table_names) and rname != "Module List" and rname != "Register List" and not rname.startswith("TCON_") and not rname.startswith("SPI_"): # same-named things? Probably a mistake in the original PDF. Make sure we have both.
        error("Table {!r} (offset: {!r}) is started again, even though we already saw the contents entirely.".format(rname, self.offset))
        sys.exit(1)
        rname = rname + "Q"
      self.finish_this_table()
      self.all_table_names.add(rname)
      print()
      print("# START TABLE", rname)
      print("{} = Module_List, [".format(quote(rname)))
      self.in_table = rname
      self.prev_table_name = orig_rname
      self.table_columns = []
      self.table_left = None
      self.table_column_lefts = []
      self.in_table_header = True
      self.table_header_autobolder = self.h3 and (self.h3.lower().rstrip().endswith("register description") or self.h3.lower().rstrip().endswith("register list"))
  def in_column_P(self, left, column_index):
      x_left = self.table_column_lefts[column_index]
      x_next_left = self.table_column_lefts[column_index + 1] if column_index + 1 < len(self.table_column_lefts) else 9999999
      return x_left <= left < x_next_left
  def finish_this_table(self):
    if self.in_table:
      assert not self.in_offset, self.in_table
      #if self.in_table_header:
      #   import pdb
      #   pdb.set_trace()
      assert not self.in_table_header, self.in_table
      print("]]")
      print()
      self.in_table = False
  def process_text(self, text, attrib, xx):
    #if text.strip() == "TV Encoder Sync and VBI Level Register": # "TCON_TV1": # and self.in_table: # "TCON_LCD0,TCON_LCD1": # "7.5.3.3.": # "MSGBOX (RISC-V)":
    #  print(attrib)
    #  import pdb
    #  pdb.set_trace()
    if  self.h4 and "SPC Configuration Table" in self.h4:
      if self.h4 and attrib["meaning"] != 'h3': #H5 skip non-register table
       return
      else:
       self.h4 = '' 
    if self.in_register_name_multipart: # A64. It has "Register Name: <b>Foo</b>"
      if text.strip() in ["TVD_3D_CTL5", "TVD_HLOCK3", "TVD_ENHANCE2"]:
        # Work around misplaced "<b>" in "Register Name; xxx <b></b>" in "D1-H_User Manual_V1.2.pdf"
        next = attrib["getnext"]()
        xxnext = set(xnode.tag for xnode in next.iterchildren() if xnode.tag != "a")
        xxnexttext = "".join(text for text in next.itertext())
        assert xxnext == {"b"} and xxnexttext.strip() == ""
        # Fix up attribute
        xx = {"b"}
      assert (attrib["meaning"] == "h4" and xx == {"b"}) or attrib["meaning"] == "table-cell" or attrib["meaning"] == "h3" or not text.strip(), (self.page_number, attrib, xx, text)
      if text.strip(): # and self.in_table_header:
        self.in_register_name_multipart = False
        # Note: This has another copy!
        rname = text.strip()
        if text.strip() == "Bit": # entirely missing name
          rname = "".join(c for c in self.h4.split("(")[0] if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
        rname = self.fixed_table_name(rname)
        if self.in_table != rname:
          #assert text.strip() != "Read/Write"
          self.finish_this_table()
          self.start_table(rname)
          if model == "V3s":
            if rname == "CE_KEY[n]" and self.offset =="0x 0 4+4*n ":
               self.offset = "0x04+4*n "
            if rname == "CE_CNT[n]" and self.offset =="0x 3 4+4*n ":
               self.offset = "0x34+4*n "   
            if rname == "AC_PR_CFG" and not self.offset: #V3s missing or wrong formatted offsets
              self.offset = '0x400'
            if rname == "CE_CTL" and self.offset == '0x  ':
              self.offset = "0x0" 
          elif model == "H3":
            if rname == "AC_PR_CFG" and not self.offset:
               self.offset = "0x2DE9C0"
          assert self.offset is not None, (rname, self.page_number)
          print("{!r},".format("Offset: " + self.offset))
          self.offset = None
        if text.strip() != "Bit":
          return
    text = text.replace("Offset :0x", "Offset: 0x")
    text = text.replace("…", "...").replace("......", "...").replace("‘", "`") \
        .replace("’", "`").replace("“", "`").replace("”", "`").replace("–", "-") \
        .replace("—", "-").replace("≤", "<=").replace("³", " ").replace("①", "1.") \
        .replace("②", "2.").replace("¼", "25%").replace("½", "50%").replace("⃝",",")
    if model == "V3s":
      if attrib["meaning"] == "table-cell" and text.lower().startswith("analog domain register"): #V3s
         attrib["meaning"] = "h4"
         xx = {"b"}
      if self.in_table and self.in_table == "AC_ROMIXSC" and text.startswith("MIXMUTE "): #V3s
        text = "RMIXMUTE "
      if self.in_table and self.in_table == "CSI0_CLK_REG" and text == "000":
        text = ""
        attrib["meaning"] = ""
      if self.in_table and self.in_table == "CSI0_CLK_REG" and text == "OSC24M ":
        text = "000: OSC24M"
      if attrib["meaning"] == "garbage-if-empty" and text.startswith("AC_DIG_CLK_REG"): #V3s wrong text id
        attrib["meaning"] = "table-cell"
      if self.h3 == "USB OTG Register List " and text.startswith("EHCI Capability Register"): #kill wrong h4
        attrib["meaning"] = ""
      if self.in_table == "CALIBRATION_CTRL" and text.startswith("Description"): #V3s description with bad text id
        attrib["meaning"] = "table-cell"
      if self.in_table == "SD_NTSR_REG" and (text.startswith("31 ") or text.startswith("30:6 ")):
        attrib["meaning"] = "table-cell"
      if (self.in_table and (self.in_table.startswith("CSI0_") or self.in_table.startswith("CCI_") or self.in_table.endswith("_DMA_STA")) and \
        (text.startswith("/") or text.startswith("R/W") or text.startswith("0x") or text.startswith("0 ") or \
          text.startswith("R ") or text.startswith("0x7fff") or text.startswith("1 ") or text.startswith("S_TRAN_"))):
        attrib["meaning"] = "table-cell"
      if self.in_table and self.in_table.startswith("ADDR0") and text.startswith("st"):
        attrib["meaning"] = "table-cell"
      if self.in_table and self.in_table.startswith("ADDRx") and text.startswith("："):
        text = ":"
        attrib["meaning"] = "table-cell"
      if (self.in_table == "Module List" and self.h4 == "CMAP module " and text == "+" ):
        attrib["meaning"] = "table-cell"
      if self.in_table == "PF_PULL0_REG" and text.startswith("0x5140"):
        text = "0x0"
      if self.in_table == "VDD_RTC_REG" and text.startswith("0x100"):
         text = "0x4"
    if self.in_table and self.in_table == "PORTSC":
      if "(WKDSCNNT_E)" in text:
        text = "WKDSCNNT_E"
      elif "(WKCNNT_E)" in text:
        text = "WKCNNT_E"
    if self.in_table and self.in_table == "SMHC_THLD_REG" and text.strip().startswith("BCIG(for SMHC2 only)"):
       text = "BCIG"    
    if self.in_table and self.in_table == "USBCMD" and text.strip().replace("  ", " ").startswith("R/W or"):
       if model == "H5":
          text = "R/W"
       else:
          attrib["meaning"] = "garbage" 
    if self.in_table and self.in_table in ["BUS_SOFT_RST_REG3", "BUS_CLK_GATING_REG2"] and text.strip().startswith("I2S/PCM "):
       text = text.replace("I2S/PCM ", "I2S_PCM_") 
    if self.in_table and self.in_table in ["TCON0_GINT0_REG","TCON_GINT0_REG"] and text.startswith("26: "):
       text = "26"
    if self.in_table and self.in_table == "TSC_PPARR" and text == "31:":
       text = "31:8"  
    if self.in_table and self.in_table == "PG_EINT_CFG3_REG":
       if text == "_REG":
          attrib["meaning"] = "garbage"     
    if self.in_table == "I2S/PCM 0_CLK_REG" and text.startswith("00: PLL_AUDIO (8X) "):
       text = "00: PLL_AUDIO(8X) " 
    if self.in_table == "CE_CTR" and text == "DIE_ID ":
       attrib["meaning"] = "garbage"   
    if self.in_table in ["NDFC_ERR_CNT1", "NDFC_ERR_CNT2"] and text.endswith("COR_NUM "):
       text = "ECC_COR_NUM"                
    if self.in_table and attrib["meaning"] == "note":
      if int(attrib["left"]) < self.table_column_lefts[-1]:
        self.finish_this_table()
      else:
        attrib["meaning"] = "table-cell"    
    if attrib["meaning"] == "garbage":
      return
    if attrib["meaning"] in ["garbage-if-empty", "h3-garbage-if-empty"] and text.strip() == "":
      return
    if attrib["meaning"] == "h3-garbage-if-empty":
      attrib["meaning"] = "h3"
    if self.in_table == "TSF_CSR" and attrib["meaning"] == "table-cell" and text.startswith("TSFGSR"):
       print("'R/W', \r'0',") #A64 restore missing
    #print(">" + text + "<", attrib, xx, file=sys.stderr)
    #if text.strip() == "Module Name" and self.page_number == '81':
    #  import pdb
    #  pdb.set_trace()
    if self.in_offset:
      if text.startswith("Register Name:"):
          self.in_offset = False
      else:
          self.offset = "{} {}".format(self.offset, text)
    if text.strip().startswith("Copyright©Allwinner Technology") or text.strip().startswith("Copyright© 2021 Allwinner Technology") or text.strip().startswith("Copyright ©"):
      return
    if attrib["meaning"] == "h0" and xx == {"b"}: # and text == "Contents"
      self.finish_this_table()
    if attrib["meaning"] == "h4" and xx == {"b"} and text.strip().endswith("Register List"): # A64 abuses this as h3 (rarely)
      self.h3 = text
      attrib["meaning"] = "h3"
    if attrib["meaning"] == "h3" and xx == {"b"}: # and text.strip().endswith(" Register Description"):
      self.finish_this_table()
      if text.strip() == "Register List": # new module starts
        print("Module_List = None")
      self.h3 = text
      if self.h3.strip() == "CPU Architecture":
          # Alternative: Make it detect as h4.
          self.start_table("CPU Architecture")
          self.table_left = int(attrib["left"])
          self.table_columns = ["Item"]
          self.table_column_lefts = [self.table_left]
          self.in_table_header = False
          print("'Item'], [[")
    if attrib["meaning"] == "h2" and xx == {"b"}:
      self.finish_this_table()
    if attrib["meaning"] == "h4" and xx == {"b"} and text.strip().startswith("Offset:"):
      self.in_offset = True
      self.offset = text.strip().replace("Offset:", "").strip() # FIXME: append
      # TODO: It could have parts between "Offset:" and "Register Name:"
      return
    elif attrib["meaning"] == "table-cell" and text.strip().startswith("Offset:"): # A64
      self.in_offset = True
      self.offset = text.strip().replace("Offset:", "").strip() # FIXME: append
      # TODO: It could have parts between "Offset:" and "Register Name:"
      return
    elif attrib["meaning"] == "h4" and xx == {"b"} and text.strip().startswith("Address:"): # R40
      self.in_offset = True
      self.offset = text.strip().replace("Address:", "").strip() # FIXME: append
      # TODO: It could have parts between "Offset:" and "Register Name:"
      return
    elif attrib["meaning"] == "h4" and xx == {"b"} and text.strip().startswith("Base Address:"):
      self.offset = text.strip().replace("Offset:", "").strip()
    elif attrib["meaning"] in ["h4", "table-cell"] and (text.strip().lower().startswith("module name") or text.strip() == "Register Name") and not self.in_table_header: # module table. Case when "Module Name" is a column twice in the same table is also handled.  A64 sometimes doesn't have xx == {"b"}
      #self.finish_this_table()
      # Using the same name here so chaining into a tree works
      rname = "Module List"
      if text.strip().lower().startswith("module name"):
        cname = "module name" 
        self.in_module = ""
      else: 
         cname = "register name"
      #if self.table_columns != ["Item"] and self.table_columns != ['Module Name ', 'Base Address '] and self.table_columns != ['Register Name ', 'Offset ', 'Description ']:
      if self.in_table != rname or (self.in_table and len(self.table_columns) > 0 and self.table_columns[0].strip().lower() != cname):
        self.finish_this_table()
        self.start_table(rname)
        #print("{!r}, ".format(text))
        #return
        #assert self.offset is not None, rname
        #print("Offset", self.offset)
        #self.offset = None
    elif text.strip() == "Register Name": # attrib["meaning"] == "h4" and xx == {"b"} and text.strip() == "Register Name": # summary; ignore
      self.finish_this_table()
    elif attrib["meaning"] == "h4" and xx == {"b"} and text.strip() == "Symbol": # 3.12.5 Register List Symbol table; ignore
      self.finish_this_table()
    elif attrib["meaning"] == "h4" and xx == {"b"} and text.strip().startswith("0x"):
      self.finish_this_table()
    elif text.strip().startswith("Register Name:"): # A64 does not match: attrib["meaning"] == "h4" and xx == {"b"} and text.strip().startswith("Register Name:"):
      rname = text.strip().replace("Register Name:", "").strip()
      if rname.strip() == "":
        self.in_register_name_multipart = True
        return
      else: # see copy of this in "if self.in_register_name_multipart"
        rname = self.fixed_table_name(rname)
        if self.in_table != rname:
          self.finish_this_table()
          self.start_table(rname)
          assert self.offset is not None, (rname, self.page_number)
          print("{!r},".format("Offset: " + self.offset))
          self.offset = None
        return
    elif attrib["meaning"] == "h4" and xx == {"b"} and self.in_table and not self.in_table_header and not self.in_offset: # sneakily start another table
      left = int(attrib["left"])
      if left == self.table_left:
          #if left in self.table_column_lefts:
          i = self.table_column_lefts.index(left)
          xcolumn = self.table_columns[i]
          if text != xcolumn:
              if len([c for c in text if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]) >= 3 and len([c for c in text if c in "abcdefghijklmnopqrstuvwxyz"]) == 0 and len(text.strip()) >= 3: # that's a R40 subheader--for example in "7.2.4. Register List".
                  print("], ['#', {!r}], [".format(text))
                  self.h4 = text # TODO: print it somehow
              elif text.strip().endswith(" Register") and [x.strip() for x in self.table_columns] == ['Register Name', 'Offset', 'Description']: # D1
                  print("], ['#', {!r}], [".format(text))
                  self.h4 = text # TODO: print it somehow
              else:
                  self.finish_this_table()
      elif model == "V3s" and left < self.table_left: #V3s
        self.finish_this_table()   
    if self.in_table and self.in_table_header and text.strip() != "":
      if self.h3 and (self.h3.lower().rstrip().endswith("register description") or self.h3.lower().rstrip().endswith("register list")) and attrib["meaning"] == "table-cell":
           if len(self.table_columns) > 0:
             if self.table_left is not None and abs(self.table_left -  int(attrib["left"])) <= 1:
               self.table_header_autobolder = False
           if self.table_header_autobolder:
             # A64 does not bold most table headers, so we have to fake it here.
             xx.add("b")
             attrib["meaning"] = "h4"
           #else:
           #  self.in_table_header = False
           #  print("], [[")

      if attrib["meaning"] == "h4" and len(self.table_columns) > 0:
        assert len(self.table_columns) > 0, (self.in_table, text)
        assert int(attrib["left"]) >= self.table_left, (self.in_table, text, self.page_number)
        if int(attrib["left"]) == self.table_left:
          warning("ignored h4 of {!r} in table {!r} since it's most likely a typo".format(text, self.in_table))
          if model == "H5":
            attrib["meaning"] = "garbage" #TSC on page 663
          else:
            attrib["meaning"] = "table-cell"
          xx = {}
      if attrib["meaning"] == "h4" and xx == {"b"}:
        if len(self.table_columns) == 0:
          self.table_left = int(attrib["left"])
        else:
          assert int(attrib["left"]) > self.table_left, (self.in_table, text)
        if self.table_columns and self.table_columns[-1].lower().startswith("description") and text.strip().lower() != "hc" and text.strip().lower() != "hcd": #description is last field. Drop garbage. H3 USB
          attrib["meaning"] = "garbage"
        else:  
          self.table_columns.append(text)
          self.table_column_lefts.append(int(attrib["left"]))
      else:
        print("], [[")
        self.in_table_header = False
    #else: # could be complicated
    #  self.offset = None
    if self.in_table:
      #text {'meaning': 'h3'} Register Description
      #text {'meaning': 'h4'} 0x0000 PLL_CPU Control Register (Default Value: 0x4A00_1000) 
      #text {'meaning': 'h4'} Offset: 0x0000 
      #text {'meaning': 'h4'} Register Name: PLL_CPU_CTRL_REG 
      #text {'meaning': 'h4'} Bit 
      #text {'meaning': 'h4'} Read/Write  Default/Hex  Description 
      #text {'meaning': 'table-cell'} 31:17 
      #if attrib["meaning"] == "h4" and self.in_table and not self.in_table_header: # error in PDF
      #  attrib["meaning"] == "table-cell"
      if attrib["meaning"] == "h4" and self.in_table and self.in_table_header:
          print("{!r}, ".format(text))
      elif attrib["meaning"] == "table-cell":
        if self.table_left is not None and abs(self.table_left -  int(attrib["left"])) <= 1:
            print("], [") # next row  
        if text.strip().startswith("Register Name: "):
          rname = text.strip().replace("Register Name: ", "")
          assert rname == self.in_table
        elif int(attrib["left"]) >= 780 and text.startswith("  ") and re_digits.match(text.strip()): # page number
          pass
        elif self.in_table != "CPU Architecture" and self.table_left is not None and int(attrib["left"]) < self.table_left:
          self.finish_this_table()
        elif model in ["H3", "H5"] and self.in_table == "Module List" and text.startswith("AC_PR_CFG"):
          print("{!r}, \r'0x2DE9C0', \r'AC Parameter Configuration Register', ".format(text))
          self.finish_this_table()
        else:
          if self.in_table == "Module List":
            if text.strip() == "TCON0":
              self.in_module = "TCON0"
            elif text.strip() == "TCON1":
              self.in_module = "TCON1"
            if text.replace("  ", " ").strip() == "0x0040+N*0x20 IRQ Enable For User N(N=0,1)":
              print("{!r} ,".format("0x0040+N*0x20"))
              text = "IRQ Enable For User N(N=0,1)"
            elif text.replace("  ", " ").strip() == "0x0050+N*0x20 IRQ Status For User N(N=0,1)":
              print("{!r} ,".format("0x0050+N*0x20"))
              text = "IRQ Enable For User N(N=0,1)"  
            elif text.replace("  ", " ").strip() == "0x100+N*0x4 Spinlock Lock Register N (N=0~31)":
              print("{!r} ,".format("0x100+N*0x4"))   
              text = "Spinlock Lock Register N (N=0~31)"
            elif text == "0x0110+N*0x04  TCON CEU Coefficient Register0(N=0,1,2,4,5,6,8,9,10) ":
               print("{!r} ,".format("0x0110+N*0x04"))
               text = "TCON CEU Coefficient Register0(N=0,1,2,4,5,6,8,9,10)"
            elif text == "0x011C+N*0x10  TCON CEU Coefficient Register1(N=0,1,2) ":
               print("{!r} ,".format("0x011C+N*0x10"))
               text = "TCON CEU Coefficient Register1(N=0,1,2)"
            elif text == "0x0140+N*0x04  TCON CEU Coefficient Register2(N=0,1,2) ":
               print("{!r} ,".format("0x0140+N*0x04"))
               text = "TCON CEU Coefficient Register2(N=0,1,2)" 
            elif text == "0x0304+N*0x0C  TCON1 Fill Data Begin Register(N=0,1,2) ":
               print("{!r} ,".format("0x0304+N*0x0C"))
               text = "TCON1 Fill Data Begin Register(N=0,1,2)" 
            elif text == "0x0308+N*0x0C  TCON1 Fill Data End Register(N=0,1,2) ":
               print("{!r} ,".format("0x0308+N*0x0C"))
               text = "TCON1 Fill Data End Register(N=0,1,2)" 
            elif text == "0x030C+N*0x0C  TCON1 Fill Data Value Register(N=0,1,2) ":
               print("{!r} ,".format("0x030C+N*0x0C"))
               text = "TCON1 Fill Data Value Register(N=0,1,2)" 
          elif self.in_table in ["AC_ADC_DAP_OPT", "AC_DAPOPT"]:
            text = text.replace("setting(include", "setting (include")  
          elif self.in_table == "HMIC_CTRL":
            if text in ["00: disable"]:
                text = text.replace("00", "0")
            elif text in ["11: enable"]:
                text = text.replace("11", "1")
          elif self.in_table == "APT_REG" and text.strip() == "0x10":
             text = "0x2"
          elif self.in_table in ["HP_CAL_CTRL", "MDET_CTRL", "PHIN_CTRL"] and text.strip() == "100":
             text = "0x4" 
          elif self.in_table in ["PHIN_CTRL", "PHOUT_CTRL"] and text.strip() == "011":
             text = "0x3"
          elif self.in_table in ["VDD_RTC_REG"] and text.strip() == "0x100":
             text = "0x4"   
          elif self.in_table in ["OWA_FSTA"] and text.strip() == "0x80": #H5
             text = "0x20"      
          elif self.in_table == "SRC_BISTCR" and "SRC1 and SRC2" in text:
             text = text.replace("SRC1 and SRC2", "")
          elif self.in_table == "AC_ADC_DAPNTH" and text.strip().endswith("(-90dB)"):
             text = text.replace("(-90dB)", "")
          elif self.in_table in ["PH_EINT_CTL_REG", "PH_EINT_STATUS_REG"]:
            if text.startswith("(n=0~11)  R/W "):
             print("{!r} ,".format("(n=0~11)"))
             text = "R/W "   
          elif self.in_table == "NDFC_TIMING_CFG" and text == "11 ":
             print("{!r},\r{!r},".format(text, "R/W")) 
             text = "0 "
          elif self.in_table == "USBSTS" and text.endswith("(USBERRINT) ") or text.endswith("(USBINT) "):
             text = text.replace("(USBINT) ","").replace("(USBERRINT) ","")    
          print("{!r}, ".format(text))
      elif attrib["meaning"] == "h4" and self.in_table and not self.in_table_header and len(self.table_columns) >= 3 and self.in_column_P(int(attrib['left']), len(self.table_columns) - 1):
        # This can be a repeated table column header--in which case we don't care--or a bolded field name--which we very much want. Distinguish those.
        words = text.split()
        columns = []
        for w in self.table_columns:
            columns.extend(w.split())
        if any(word not in columns for word in words if word):
            print("{!r}, ".format(text))
        else:
            print("# repeated table header {} {!r}".format(text, attrib))
      else:
        if text.strip() != "": #dont print spaces
          print("# ??? {} {!r}".format(text, attrib))
    if attrib["meaning"] == "h4" and not self.in_table:
      self.h4 = text

def hashable_fontspec(d):
  result = tuple(sorted(d.items()))
  return result

def resolve_fontspec(fontspecs, id):
  # Note: Would work completely: just return (('color', '#000080'), ('family', 'BAAAAA+LiberationSerif'), ('size', '12'))
  for xid, xfontspec in fontspecs:
    # fontspec  {'id': '0', 'size': '21', 'family': 'BAAAAA+LiberationSerif', 'color': '#000000'}
    if xid == id:
      xfontspec = hashable_fontspec(xfontspec)
      return xfontspec
  assert False, (id, fontspecs)

def meaning_of_fontspec(fontspec, xx):
  try:
    meaning = fontspec_to_meaning[fontspec]
  except KeyError:
    #warning("Font {!r} was unknown.  Assuming it's uninteresting.".format(dict(fontspec)))
    meaning = None
  if meaning == "table-cell":
    if xx == {"b"}:
      meaning = "h4"
    else:
      pass
  elif meaning == "headline" and not (xx == {"b"}):
    meaning = None
  return meaning

def traverse(state, root, indent = 0, fontspecs = []): # fontspecs: [(id, node with attribs: size, family, color)]
  for node in root.iterchildren(): # DFS
    attrib = node.attrib # filter it!
    xx = set(xnode.tag for xnode in node.iterchildren() if xnode.tag != "a")
    if xx == {"b"}:
       if not any(True for xnode in node.iterchildren() if xnode.tag == "b" and xnode.text.strip() != ""): # "foo <b> </b>"
         xx = set()
    if node.tag == "page":
       state.page_number = dict(node.attrib)["number"]
    if node.tag == "fontspec":
      # need to mutate because scoping rules are that way
      xnode = dict(node.attrib)
      del xnode["id"]
      fontspecs.insert(0, (node.attrib["id"], xnode))

    attrib["meaning"] = ""
    if node.tag == "text":
      #print("TOP", attrib["top"], file=sys.stderr)
         #return
      #print("STILL OK", node.text, file=sys.stderr)
      top = int(attrib["top"])
      attrib = dict([(k,v) for k, v in attrib.items() if k not in ["top", "width", "height"]])
      #x = list(attrib.keys())
      #assert x == ["font"] or x == []
      if node.text is None or set(xnode.tag for xnode in node.iterchildren() if xnode.tag == "a"): # for example if there are <a ...>
        text = "".join(text for text in node.itertext()) # XXX maybe recurse
      else:
        text = node.text
      if "font" in attrib: # resolve reference
        font_id = attrib["font"]
        fontspec = resolve_fontspec(fontspecs, font_id)
        try:
          attrib["meaning"] = meaning_of_fontspec(fontspec, xx) or ""
          #if not attrib["meaning"]:
          #    print("^ Page {}: Text {!r}: Unknown font".format(state.page_number, text), file=sys.stderr)
        except KeyError as e:
          info("Text for failure below is: {}".format(text))
          raise e
        if not attrib["meaning"]:
          attrib["font"] = str(fontspec)
        else:
          del attrib["font"]
      if top >= 1183 or top < 90: # outside of payload area
         attrib["meaning"] = "garbage"
      #print("QQ", state.in_table, node.tag, attrib, text)

    #if attrib["meaning"] in ["h1", "h2", "h3", "h4", "table-cell"]:
    if node.tag == "text":
      attrib["getnext"] = node.getnext
      state.process_text(text, attrib, xx)
    if node.tag == "b":
      pass
    else:
      traverse(state, node, indent + 1, fontspecs)

root = tree.getroot()
state = State()
model = os.path.basename(sys.argv[2]).replace("Allwinner_", "").split("_")[0]
print("__model = {!r}".format(model))
print("Module_List = None")
traverse(state, root)
state.finish_this_table()
