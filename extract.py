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
  ({'color': '#000000', 'family': 'ABCDEE+Calibri', 'size': '13'}, "table-cell"), # used once
  ({'color': '#000000', 'family': 'Calibri', 'size': '120'}, "garbage"),

  # R40, A64
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '15'}, "h4"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '16'}, "h4"), # R40
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '90'}, "garbage"),
  ({'color': '#005ebd', 'family': 'ABCDEE+Calibri,Bold', 'size': '19'}, "h3"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '21'}, "h3"), # CPU Architecture
  ({'color': '#0f0f00', 'family': 'ABCDEE+Calibri,Bold', 'size': '21'}, "h3"), # Register List in A64
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '23'}, "h2"),
  ({'color': '#000000', 'family': 'ABCDEE+Calibri,Bold', 'size': '18'}, "garbage-if-empty"), # Otherwise it throws off table header detection--and the text is empty anyway (TODO: check).
  ({'color': '#000000', 'family': 'Times New Roman,BoldItalic', 'size': 15}, "garbage-if-empty"),
  ({'color': '#000000', 'family': 'Times New Roman', 'size': '15'}, "garbage-if-empty"),
]

def hashable_fontspec(d):
  result = tuple(sorted(d.items()))
  return result

def xdict(fontspec_to_meaning):
  return dict([(hashable_fontspec(k),v) for k, v in fontspec_to_meaning])

# Check for dupes
assert len(xdict(fontspec_to_meaning)) == len(fontspec_to_meaning)
fontspec_to_meaning = xdict(fontspec_to_meaning)

with open(sys.argv[1]) as f:
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
  def start_table(self, rname):
      self.finish_this_table()
      print()
      print("# START TABLE", rname)
      print("{} = Module_List, [".format(quote(rname)))
      self.in_table = rname
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
    if self.in_register_name_multipart: # A64. It has "Register Name: <b>Foo</b>"
      assert (attrib["meaning"] == "h4" and xx == {"b"}) or attrib["meaning"] == "table-cell" or attrib["meaning"] == "h3", (self.page_number, attrib, xx)
      if text.strip(): # and self.in_table_header:
        self.in_register_name_multipart = False
        # Note: This has another copy!
        rname = text.strip()
        if text.strip() == "Bit": # entirely missing name
          rname = "".join(c for c in self.h4 if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
        rname = rname.split("(n=")[0] # "NDFC_USER_DATAn(n=0~15)" in R40
        if rname == "HcPeriodCurrentED(PCED)": # R40
            rname = "HcPeriodCurrentED" # FIXME
        rname = rname.replace("_C0~3", "") # in R40 # FIXME
        if self.in_table != rname:
          #assert text.strip() != "Read/Write"
          self.finish_this_table()
          self.start_table(rname)
          assert self.offset is not None, (rname, self.page_number)
          print("{!r},".format("Offset: " + self.offset))
          self.offset = None
        if text.strip() != "Bit":
          return
    text = text.replace("Offset :0x", "Offset: 0x")
    if attrib["meaning"] == "garbage":
      return
    if attrib["meaning"] == "garbage-if-empty" and text.strip() == "":
      return
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
    if attrib["meaning"] == "h3" and xx == {"b"}: # and text.strip().endswith(" Register Description"):
      self.finish_this_table()
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
    elif attrib["meaning"] in ["h4", "table-cell"] and text.strip().startswith("Module Name") and not self.in_table_header: # module table. Case when "Module Name" is a column twice in the same table is also handled.  A64 sometimes doesn't have xx == {"b"}
      self.finish_this_table()
      rname = "Module List"
      if self.in_table != rname:
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
        rname = rname.split("(n=")[0] # "NDFC_USER_DATAn(n=0~15)" in R40
        if rname == "HcPeriodCurrentED(PCED)": # R40
            rname = "HcPeriodCurrentED" # FIXME
        rname = rname.replace("_C0~3", "") # in R40 # FIXME
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
              self.finish_this_table()
      #else:
      #    self.finish_this_table()
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
          attrib["meaning"] = "table-cell"
          xx = {}
      if attrib["meaning"] == "h4" and xx == {"b"}:
        if len(self.table_columns) == 0:
          self.table_left = int(attrib["left"])
        else:
          assert int(attrib["left"]) > self.table_left, (self.in_table, text)
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
        else:
          print("{!r}, ".format(text))
      elif attrib["meaning"] == "h4" and self.in_table and not self.in_table_header and len(self.table_columns) > 3 and self.in_column_P(int(attrib['left']), len(self.table_columns) - 1):
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
      x = list(attrib.keys())
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
