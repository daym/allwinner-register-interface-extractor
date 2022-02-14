#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import re
import sys
from logging import debug, info, warning, error, critical
import logging
logging.basicConfig(level=logging.INFO)

from lxml import etree
from typing import NamedTuple, List

import phase2_result
from pprint import pprint

del phase2_result.Module_List

re_enum = re.compile(r"^[0-9xA-F]+: ")
re_num_al_name = re.compile("^[0-9]*[A-Z]+$")

#phase2_result__names

def clean_table(module, header, body, name):
  prefix = []
  suffix = []
  for item in header:
    if item.find(":") != -1:
      prefix.append(item.strip())
    else:
      for x in item.replace("Module Name", "Module_Name").replace("Module name", "Module_Name").replace("Base Address", "Base_Address").replace("Base address", "Base_Address").replace("Register Name", "Register_Name").replace("Register name", "Register_name").replace("Register Description", "Register_Description").split():
        suffix.append(x)
  if suffix == ['Bit', 'Read/Write', 'Default/Hex', 'Description'] and len(body) >= 1 and body[0] == ["HCD ", "HC "]: # R40 bug in HcInterruptStatus
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']
    del body[0]
  elif suffix == ['Bit', 'Read/Write', 'Default/Hex', 'Description', 'HCD', 'HC']:
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']

  header = (prefix, suffix)
  while body[0:1] == [[]] or body[0:1] == [[" "]]:
    del body[0]
  #for row in body:
  #  while row[-1:] == [" "] or row[-1:] == ["CCU register list: "]:
  #    del row[-1]
  any_match = True
  while any_match:
    any_match = False
    nrows = []
    for row in body:
      if len(row) > 1 and row[-1].strip().endswith("register list:"): # D1 sometimes puts "... register list:" right into the previous line
        any_match = True
        s = row[-1]
        del row[-1]
        nrows.append(row)
        nrows.append([s])
      else:
        nrows.append(row)
    body[:] = nrows

  if body[-1][-1].strip().endswith("register list:"): # D1 sometimes puts "... register list:" right into the previous module-decl.
    s = body[-1][-1]
    del body[-1][-1]
    while body[-1:] == [[]] or body[-1:] == [[' ']]:
     del body[-1]
    body.append([s])
  while body[-1:] == [[]] or body[-1:] == [[' ']]:
     del body[-1]

  if module is None:
     if len(suffix) > 1:
         for row in body:
            while len(row) > len(suffix):
              s = row[-1]
              del row[-1]
              row[-1] = "{} {}".format(row[-1], s)
     return module, header, body
  access_possibilities = ["R/W1C", "R/W", "R", "W", "/"]
  if len(suffix) == 0: # ???
      warning("Did not find proper header for {!r} {!r} {!r}.".format(header, body, name))
      return module, header, body
  for row in body:
    if row == []:
      continue
    if row[0:1] == ["#"]:
      continue
    while len(row) >= 1 and row[0] == " ":
      del row[0]
    if len([x for x in row if x == " "]) > 0:
      nrow = []
      for i, x in enumerate(row):
          if len(nrow) >= len(suffix):
            nrow.append(x)
          elif x != " ":
            nrow.append(x)
      row[:] = nrow
    number_of_access_specs = len([x for x in suffix if x.find("Read/Write") != -1])
    for i in range(number_of_access_specs):
      if len(row) >= 1:
        row[0] = row[0].rstrip()
        for access_possibility in access_possibilities:
          pattern = " {}".format(access_possibility)
          if row[0].endswith(pattern):
            row[0] = row[0][:-len(pattern)]
            row.insert(1, access_possibility)
            break
    if len(row) >= 2:
      parts = row[1].split()
      if len(parts) > 1:
         a1 = parts[0].strip()
         a2 = parts[1].strip()
         if a1 in access_possibilities and a2 in access_possibilities:
           assert suffix == ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']
           row[1] = a1
           row.insert(2, a2)
    while len(row) > len(suffix):
      s = row[len(row) - 1]
      sep = "\n" if re_enum.match(s) else " "
      row[len(row) - 2] = row[len(row) - 2] + sep + s
      del row[len(row) - 1]
    if len(row) != len(suffix):
      warning("Table formatting in PDF is unknown: header={!r}, row={!r}".format(header, row))
  return module, header, body

def unroll_instances(module):
  _, header, body = module
  prefix, header = header
  assert header == ["Module_Name", "Base_Address"], header
  #print("BODY", body, file=sys.stderr)
  for Module_Name, Base_Address in body:
    Module_Name = Module_Name.strip()
    Base_Address = Base_Address.replace("(for HDMI)", "").strip()
    Base_Address = eval(Base_Address.strip(), {})
    yield Module_Name, Base_Address
  #assert len(body) == 1, (header, body)
  # AssertionError: (['Module_Name', 'Base_Address'], [['I2S/PCM0 ', '0x02032000 '], ['I2S/PCM1 ', '0x02033000 '], ['I2S/PCM2 ', '0x02034000   ', ' ']])

# In the tree, all the dependencies point up to the ancestors. We have to reverse the edge direction, basically.
# The phase2_result directory does NOT contain all the nodes. Some have been shadowed!

from collections import namedtuple

def clean_up_input():
    class Dnode(NamedTuple):
        name: str
        header: List
        rows: List
        children: List

    dnode_by_id = {}
    root_dnode = Dnode(name = "ROOT", header = ([], []), rows = [], children = [])
    def walk_up(module, name):
        # Every new module is represented by a DNode.
        # children_by_id is used as a memoizer so we find the NEW modules only.
        # The roots are remembered in ROOTS.
        if id(module) in dnode_by_id:
            return dnode_by_id[id(module)]
        if module is None:
            return root_dnode
        module_module, module_header, module_body = module
        x_module = clean_table(module_module, module_header, module_body, name = None)
        x_module_module, x_module_header, x_module_body = x_module

        dnode = Dnode(name = name, header = x_module_header, rows = x_module_body, children = [])
        dnode_by_id[id(module)] = dnode
        if len(module_header) > 0 and module_header[0].strip() == "Module Name":
            parent_dnode = root_dnode
        else:
            parent_dnode = walk_up(module_module, None)
        parent_dnode.children.append(dnode)
        return dnode

    # Loop over all visible bindings in phase2_result
    for n in dir(phase2_result):
        if n.startswith("__") or n == "Module_List" or n == "Register List":
            pass
        else:
            x_module = getattr(phase2_result, n)
            # Traverse ancestors.
            # Note: (Eventually) loops over all objects in phase2_result
            walk_up(x_module, n)
            # container.append()

    return root_dnode

#  registers[module].append((n, header, body))

__model = phase2_result.__model

def text_element(key, text):
  result = etree.Element(key)
  #result.append(etree.TextNode(text))
  result.text = str(text)
  return result

svd_root = etree.Element("device")
svd_root.attrib["schemaVersion"] = "1.3"

svd_root.append(text_element("vendor", "Allwinner"))
svd_root.append(text_element("vendorID", "sunxi"))
svd_root.append(text_element("name", __model.replace(" ", "_")))
svd_root.append(text_element("series", __model))
svd_root.append(text_element("version", "0.1")) # FIXME: version of this description, adding CMSIS-SVD 1.1 tags
svd_root.append(text_element("description", __model))
svd_root.append(text_element("licenseText", "questionable"))
# TODO: <cpu> with: <name>, <revision>, <endian>little</endian>, <mpuPresent>, <fpuPresent>, <nvicPrioBits>, <vendorSystickConfig>
svd_root.append(text_element("addressUnitBits", 8)) # min. addressable
svd_root.append(text_element("width", 64)) # bus width # FIXME.

# Set defaults for registers:
svd_root.append(text_element("size", 32))
svd_root.append(text_element("access", "read-write"))
#svd_root.append(text_element("resetValue", "0"))
svd_root.append(text_element("resetMask", "0xFFFFFFFF"))

def create_peripheral(name, baseAddress, access="read-write", description=None, groupName=None):
  result = etree.Element("peripheral")
  result.append(text_element("name", name))
  result.append(text_element("description", description or name))
  result.append(text_element("groupName", groupName or "generic"))
  result.append(text_element("baseAddress", "0x{:X}".format(baseAddress)))
  result.append(text_element("access", access))
  return result

def create_addressBlock(offset, size, usage="registers"):
  result = etree.Element("addressBlock")
  result.append(text_element("offset", offset))
  result.append(text_element("size", size))
  result.append(text_element("usage", usage))
  return result

re_digit = re.compile(r"^[0-9]")

def generate_enumeratedValue_name(key, meaning, parts = 1):
  q = meaning.strip().split()
  while len(q) > 0 and q[0].lower() in ["using", "the"]:
     del q[0]
  if len(q) < parts:
    return None
  name = "_".join(q[0:parts]).rstrip(",").rstrip(";").rstrip(".").strip()
  if len(q) > parts:
    suffix = q[parts].strip()
    if suffix.startswith("k") or suffix.startswith("mV") or suffix.startswith("dB") or suffix == "V" or suffix == "ms" or suffix.startswith("uA") or suffix.startswith("kHz") or suffix in ["s", "cycles", "sample", "samples", "bit", "bits", "disable", "enable", "both", "and", "status", "pending", "available", "mode", "data", "detect", "line", "timeout", "idle", "transmission", "empty", "full", "edge", "level", "Edge", "Level", "Cycle", "cycle"]: # keep units and important suffixes
      name = "{}_{}".format(name, suffix)
    #elif suffix == "not":
    #  name = "{}_{}".format(name, suffix)
    else:
      while len(q) > parts:
        s = ("_" + name).lower()
        if s.endswith("_no") or s.endswith("_not") or s.endswith("_is") or s.endswith("_between") or s.endswith("_with") or s.endswith("_without") or s.endswith("_will") or s.endswith("_always") or s.endswith("_don’t") or s.endswith("_must") or s.endswith("_a") or s.endswith("_use") or s.endswith("_the") or s.endswith("do") or s.endswith("_only") or s.endswith("_to"):
          suffix = q[parts].strip()
          name = "{}_{}".format(name, suffix)
          parts = parts + 1
        else:
          break
  name = name.replace("-bit", "_bit").replace("-byte", "_byte").replace("-wire", "_wire").strip().strip(",").strip(";").rstrip(".").rstrip(":").replace("“", "").replace("”", "")
  #if name.startswith("the_"):
  #  name = name[len("the_"):]
  if len(name) == 0:
    name = key
  name = "_" + name
  for a, b in [
    ("_don’t", "_dont"),
    ("*", "_times_"),
    ("‘", "_quote_"),
    ("’", "_quote_"),
    ("+", "_plus_"),
    ("_j-state", "_j_state"),
    ("_k-state", "_k_state"),
    ("_bi-", "_bi"),
    ("_by-", "_by"),
    ("_DE-", "_de"),
    ("_de-", "_de"),
    ("_no-", "_no_"),
    ("_re-", "_re_"),
    ("_read-", "_read_"),
    ("_write-", "_write_"),
    ("_one-", "_one_"),
    ("_single-", "_single_"),
    ("_left-", "_left_"),
    ("_right-", "_right_"),
    ("_full-", "_full_"),
    ("_half-", "_half_"),
    ("_set-", "_set_"),
    ("_non-", "_non_"),
    ("_over-", "_over"),
    ("_u-law", "_ulaw"),
    ("_A-law", "_Alaw"),
    ("_s-Video", "_s_Video"),
    ("-", "_minus_"),
    ("=", "_equals_"),
    (".", "_point_"),
    ("%", "_percent_"),
    ("/", "_slash_"),
    (":", "_colon_"),
    ("→", "_"),
    ("—", "_"),
    (",", "_comma_"),
    ("…", ""),
    ("~", "_tilde_"),
    ("^", "_circumflex_"),
    ("{", "_openingbrace_"),
    ("}", "_closingbrace_"),
    ("(", "_openingparen_"),
    (")", "_closingparen_"),
    ("<", "_lt_"),
    (">", "_gt_"),
    ("&", "_amp_"),
    ("“", ""), # dquot
    ("”", ""), # dquot
    ("¼", "_onequarter_"),
    ("½", "_onehalf_"),
    ("–", "_"),
    ("°", "_deg_"),
    (";", "_semicolon_"),
  ]:
     def upper2(a):
        return a[0:2].upper() + a[2:]
     name = name.replace(a, b).replace(upper2(a), b)
  if name.startswith("_"):
     name = name[len("_"):]
  if not name:
     name = key
  if re_digit.match(name):
     name = "_{}".format(name)
  return name

def create_enumeratedValue(name, key, meaning):
  result = etree.Element("enumeratedValue")
  #print("XXNAME {!r}".format(name), file=sys.stderr)
  result.append(text_element("name", name)) # Note: Supposedly optional
  result.append(text_element("description", meaning))
  result.append(text_element("value", key))
  return result

re_enum_column_2 = re.compile(r"^([^:]*)  (Others|Other|1X|0x[0-9A-F]+|[01]+):(.*)")

svd_peripherals_by_path = {}

def split_at_is(s):
     if s is None:
       return "", s
     i = s.find("_is_")
     if i != -1:
       return s[:i], s[i + len("_is_"):]
     else:
       i = s.find("_mode_")
       if i == -1:
         i = s.find("_Mode_")
       if i != -1:
         return s[:i], s[i + len("_mode_"):]
       else:
         return "", s

def create_register(table_definition, name, addressOffset, register_description=None):
  result = etree.Element("register")
  register_name = name
  result.append(text_element("name", name))
  result.append(text_element("description", register_description or name))
  # FIXME  result.append(text_element("alternateRegister", primary_registers_by_absolute_address[addressOffset]))
  result.append(text_element("addressOffset", "0x{:X}".format(addressOffset)))
  # FIXME: result.append(text_element("size", table_definition.size))
  # TODO: result.append(text_element("access", access))
  result.append(text_element("resetValue", "0x{:X}".format(table_definition.reset_value)))
  result.append(text_element("resetMask", "0x{:X}".format(table_definition.reset_mask)))
  # TODO: result.append(text_element("modifiedWriteValues", "oneToClear"))
  fields = etree.Element("fields")
  result.append(fields)
  bits = table_definition.bits
  for (max_bit, min_bit), name, description, access_raw in bits:
    if description.find("R/W") != -1: # maybe parse error
      warning("{!r}: field {!r}: Maybe parse error; description={!r}".format(register_name, name, description))

    counter = 0
    while True:
      counter = counter + 1
      enums = []
      lines = [line.split(":", 1) for line in description.split("\n") if re_enum.match(line)]
      #if [line.split(":", 1) for line in description.split("\n") if
      #if len([1 for n, meaning in lines if meaning.find(":") != -1]) > 0:
      #  print("QQ", lines, file=sys.stderr)

      # Check for columns like "0x00: foo    0x10: bar" and flatten those
      if len([1 for n, meaning in lines if re_enum_column_2.match(meaning)]) > 0:
         nlines = []
         for n, meaning in lines:
            m = re_enum_column_2.search(meaning)
            while m:
              meaning, n_2, meaning_2 = m.group(1), m.group(2), m.group(3)
              assert not re_enum_column_2.match(meaning)
              nlines.append((n, meaning))
              n = n_2
              meaning = meaning_2
              m = re_enum_column_2.search(meaning)
            nlines.append((n, meaning))
         lines = nlines
         assert len([1 for n, meaning in lines if re_enum_column_2.match(meaning)]) == 0, (register_name, name, lines)
         #warning("XXX register {!r} field {!r} enum variants are in columns: {!r}".format(register_name, name, lines))
      for n, meaning in lines:
            n = n.strip()
            meaning = meaning.strip()
            if meaning.strip().lower() in ["reserved", "revered", "/"]: # sic
              continue
            variant_name = generate_enumeratedValue_name(n, meaning or n, parts = counter)
            if variant_name is None:
              warning("register {!r} field {!r} enum variants are not unique ({!r}, counter = {!r}). Giving up.".format(register_name, name, lines, counter))
              enums = []
              break
            if variant_name.lower().startswith(name.lower() + "_") and len(variant_name.lower()) > len(name.lower() + "_"):
                variant_name = variant_name[len(name.lower() + "_"):]
            enums.append((variant_name, n, meaning))
      if len(set([variant_name.lower() for variant_name, n, meaning in enums])) == len(enums):
        break
      #else:
      #  info("register {!r} field {!r} enum variants {!r} are not unique.".format(register_name, name, enums))
    if register_name == "TWI_EFR" and name == "DBN" and (max_bit, min_bit) == (0, 1): # Errata in Allwinner_R40_User_Manual_V1.0.pdf
        max_bit, min_bit = 1, 0
    field = etree.Element("field")
    field.append(text_element("name", name.replace("[", "_").replace(":", "_").replace("]", "_")))
    #print("Q", ((max_bit, min_bit), name, description, access_raw), file=sys.stderr)
    access = {
            "R": "read-only",
            "RO": "read-only",
            "RC": "read-only",
            "RC/W": "read-only",
            "R/W": "read-write",
            "W/R": "read-write", # ???
            "RW": "read-write",
            "R/w": "read-write",
            "R/WC": "read-write",
            "R/W1C": "read-write",
            "R/W1S": "read-write",
            "R/W0C": "read-write",
            "R/WAC": "read-write",
            "W": "write-only",
            "WC": "write-only",
            "WAC": "write-only",
            "WO": "write-only", # A64
            "R/Wor": "read-write", # TODO: Special-case "R/W or R" with a case analysis
            "": None, # ?
    }[access_raw.replace(" ", "").strip()]
    if access:
      field.append(text_element("access", access))
    modifiedWriteValues = {
            "R/WC": "clear",
            "WC": "clear",
            #"WAC": "clear", # after operation FINISHED--not necessarily directly after a Write.
            #"R/WAC": "clear", # after operation FINISHED--not necessarily directly after a Write.
            "R/W1C": "oneToClear",
            "R/W1S": "oneToSet",
            "R/W0C": "zeroToClear",
    }.get(access_raw.replace(" ", "").strip())
    if modifiedWriteValues:
        field.append(text_element("modifiedWriteValues", modifiedWriteValues))
    readAction = {
            "RC": "clear",
            "RC/W": "clear",
    }.get(access_raw.replace(" ", "").strip())
    if readAction:
        field.append(text_element("readAction", readAction))
    field.append(text_element("description", description))
    field.append(text_element("bitRange", "[{}:{}]".format(max_bit, min_bit)))
    if enums:
        enumeratedValues = etree.Element("enumeratedValues")
        for variant_name, n, meaning in enums:
          if n.strip().lower() in ["other", "others"] and meaning.lower() in ["reserved", "revered"]: # sic
              continue
          num_bits = max_bit - min_bit + 1
          assert not (len(n) == 3 and n.startswith("0x") and num_bits == 3), (n, meaning, name, register_name)
          if n.startswith("0x"):
              if len(n) > len("0x"): # ok
                  pass
              else:
                  if n in ["Other", "Others"] and meaning.strip() == "/":
                      pass
                  else:
                      warning("Could not interpret enumeratedValue {!r}: {!r} in field {!r} in register {!r}".format(n, meaning, name, register_name))
                  continue
          else: # binary
              if len([x for x in n if x not in ["0", "1"]]) == 0:
                if len(n) == num_bits:
                  n = "0b{}".format(n)
                else:
                  warning("Could not interpret enumeratedValue {!r}: {!r} in field {!r} in register {!r} (num_bits = {!r})".format(n, meaning, name, register_name, num_bits))
                  continue
              elif len([x for x in n if x not in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]]) == 0: # decimal
                 n = int(n)
                 if n >= 0 and n < 2**num_bits:
                    n = str(n)
                 else:
                    warning("Could not interpret enumeratedValue {!r}: {!r} in field {!r} in register {!r} (num_bits = {!r})".format(n, meaning, name, register_name, num_bits))
                    continue
              else:
                 warning("Could not interpret enumeratedValue {!r}: {!r} in field {!r} in register {!r} (num_bits = {!r})".format(n, meaning, name, register_name, num_bits))
                 continue
          enumeratedValue = create_enumeratedValue(variant_name, n, meaning or n)
          enumeratedValues.append(enumeratedValue)
        if len(enumeratedValues) > 0:
          prefixes = [split_at_is(v.find("./name").text)[0] for v in enumeratedValues]
          if len(set([x for x in prefixes if x != ""])) <= 1: # always the same prefix
            shorter_variants = [split_at_is(v.find("./name").text)[1] for v in enumeratedValues]
            if len(shorter_variants) == len(set(shorter_variants)):
               for enumeratedValue in enumeratedValues:
                   _, enumeratedValue.find("./name").text = split_at_is(enumeratedValue.find("./name").text)
          field.append(enumeratedValues)
    fields.append(field)
  return result

def create_cpu(suffix, body):
  assert suffix == ["Item"], suffix
  assert len(body) == 1
  body = body[0]
  result = etree.Element("cpu")
  i = 0
  while i < len(body):
    if i > 0 and body[i].startswith("-"):
        body[i - 1] = body[i - 1] + body[i]
        del body[i]
    else:
        i = i + 1
  body = [x.strip() for x in body]
  #QQ [['Quad-core ARM Cortex-A7 Processor ', 'ARMv7 ISA standard ARM instruction set ', 'Thumb-2 Technology ', 'Jazeller RCT ', 'NEON Advanced SIMD ', 'VFPv4 floating point ', 'Large Physical Address Extensions(LPAE) ', '32KB L1 Instruction cache and 32KB L1 Data cache for per CPU ', '512KB L2 cache shared ']]
  cpu_name = "other"
  cpu_fpuPresent = False
  for item in body:
      item = item.replace("per CPU", "per C")
      item = item.strip()
      if item.startswith("VFPv4 floating point"):
          cpu_fpuPresent = True
      elif item.startswith("XuanTie C906 RISC-V CPU"): # the latter is RV64GCV
          cpu_fpuPresent = True
          cpu_name = item
      elif item.endswith("Processor") or item.endswith("CPU"):
          cpu_name = item.replace("Processor", "").replace("CPU", "").strip()
          if cpu_name.endswith("ARM Cortex-A7"):
              cpu_name = "CA7"
          elif cpu_name.endswith("ARM Cortex-A53"):
              cpu_name = "CA53"
  result.append(text_element("name", cpu_name)) # I think technically it's "selectable" endian.
  result.append(text_element("revision", "0")) # yeah... no.
  result.append(text_element("endian", "little")) # I think technically it's "selectable" endian.
  result.append(text_element("mpuPresent", "true"))
  result.append(text_element("fpuPresent", "true" if cpu_fpuPresent else "false"))
  if cpu_fpuPresent:
      result.append(text_element("fpuDP", "true"))
  # icachePresent, dcachePresent
  result.append(text_element("nvicPrioBits", "0")) # FIXME: is mandatory but no idea how to find it
  result.append(text_element("vendorSystickConfig", "false")) # FIXME: does it or does it not implement its own systick timer
  return result

et = etree.ElementTree(svd_root)
#etree.register_namespace("", "urn:iso:std:iso:20022:tech:xsd:CMSIS-SVD.xsd")
#etree.register_namespace("xs", "http://www.w3.org/2001/XMLSchema-instance")
XS = "http://www.w3.org/2001/XMLSchema-instance"
svd_root.set("{%s}noNamespaceSchemaLocation" % XS, "CMSIS-SVD.xsd")
#svd_root.attrib["xmlns:xs"] = "http://www.w3.org/2001/XMLSchema-instance"
#svd_root.attrib["xs:noNamespaceSchemaLocation"] = "CMSIS-SVD.xsd"
#svd_root.set("xmlns", "urn:iso:std:iso:20022:tech:xsd:CMSIS-SVD.xsd")
#svd_root.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema-instance")

"""
  <peripherals>
    <peripheral>
      <name>DF</name>
      <description>DF</description>
      <groupName>generic</groupName>
      <baseAddress>0</baseAddress>
      <access>read-write</access>
      <registers>
        <register ...>
        </register>
        <register derivedFrom="FabricIndirectConfigAccessAddress_n0">
          <name>FabricIndirectConfigAccessAddress_n1</name>
          <addressOffset>0xE00C4054</addressOffset>
          <size>32</size>
        </register>
"""

from collections import namedtuple
Register = namedtuple("Register", ["name", "meta", "header", "bits", "reset_value", "reset_mask"])
re_definitely_not_name = re.compile("^[0-9]*$")
re_name = re.compile(r"^([0-9]*[A-Z_0-9]+[A-Z_0-9./-][A-Z_0-9]*|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en)$")
re_name_read = re.compile(r"^[(]read[)]([0-9]*[A-Z_a-z]+|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en)$")
re_name_write = re.compile(r"^[(]write[)]([0-9]*[A-Z_a-z]+|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en)$")

# This also matches mixed-case field names like "Foo_Bar" (those happen sometimes)
re_field_name_good = re.compile(r"^(([0-9]*[A-Z][A-Z0-9]*_[A-Z0-9./_-]+[a-zA-Z0-9./_-]*|[0-9]*[A-Z][A-Z0-9./_-]+|[0-9]*[A-Z][a-z][A-Za-z]*_[A-Z][A-Za-z_]+)(\[[0-9]+(:[0-9]+)?\])?)\s")

connectives = set(["a", "the", "has", "is", "are", "includes", "the", "to", "for", "largest", "between", "because", "how", "whether", "indicates", "specifies", "by", "when", "of", "contains", "initiate", "related", "if", "affected", "dedicated", "support", "and"])
nouns = set(["threshold", "peak", "coefficient", "rms", "receive", "transmit", "gain", "smooth", "filter", "signal", "average", "attack", "sustain", "decay", "hold", "release", "size", "count", "enable", "mode", "time", "channel", "noise"])

def field_name_from_description(description, field_word_count):
        """ Returns the field name extracted from a description.  Returns the empty string if that cannot be done.
            Also returns whether the match was very good, and whether the match was very bad. """
        matched_field_name_good = False
        guessed = False
        if description:
           q = description.split(". ")[0].split(",")[0]
           if field_word_count == 1 or field_word_count == 6:
               m = re_field_name_good.match("{} ".format(q))
               if m: # FOO_BAR
                   matched_field_name_good = True
                   q = m.group(1)
                   #q = q.replace("[", "_").replace("]", "_").replace(":", "_") # it's better if those pseudo fields don't come out--but maybe we want the extra info.
           if not matched_field_name_good:
               q = q.split(":")[0]
           words = q.replace(" is set by hardware to ", " ").replace(" by HC to ", " to ").replace(" to point to ", " to ").replace(" to enable or disable ", " ").replace(" to enable/disable ", " ").replace(" by HCD ", " ").replace(" when HC ", " ").replace(" is set by an OS HCD ", " ").replace(" is set by HCD ", " ").replace(" is set by HC ", " ").replace(" content of ", " ").replace("hyscale en", "hyscale_en").split("\n", 1)[0].split()
           stripped = False
           while len(words) > 0 and (words[0] in ["This", "field", "bit", "set", "indicate", "specify", "describes", "determines", "used", "there", "any", "the", "a", "an", "value", "which", "loaded", "into", "The", "the", "that", "byte", "implemented", "incremented", "immediately", "initiated", "Each"] or words[0] in connectives):
              del words[0]
              stripped = True
           if words[0:2] == ["address", "of"]:
              del words[0]
              del words[0]
           #elif words[0:3] == ["base", "address", "of"]:
           #   del words[0]
           #   del words[0]
           elif words[0:4] == ["enable", "the", "processing", "of"]:
              del words[0:4]
           while len(words) > 0 and words[0] in ["the", "a", "implemented", "is"]:
              del words[0]
           q = words[0:field_word_count]
           r = words[field_word_count:]
           #connective_count = 0
           if len(r) > 0 and not matched_field_name_good and (r[0] in connectives or r[0].lower() in nouns) and field_word_count < 6:
               return "", False, False
           #    q.append(r[0])
           #    del r[0]
           #    if r == []:
           #        break
           #    words = r
           #    while len(words) > 0 and words[0] in ["the", "a", "an"]:
           #        del words[0]
           #    q.append(words[0])
           #    del r[0]
           name = "_".join([w for w in q if w[0].upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" or re_num_al_name.match(w)]) or ""
           name = name.rstrip(".").rstrip(",").rstrip(":").rstrip()
           name = name.replace("(Read)", "(read)")
           name = name.replace("[POTPGT]", "") # redundant, and would cause it to fail.
           m = re_name_read.match(name)
           if m: # "(read)A" vs "(write)B"
             name = "{}_R".format(m.group(1))
           m = re_name_write.match(name)
           if m: # "(read)A" vs "(write)B"
             name = "{}_W".format(m.group(1))
           name = name.upper()
           #print("NAME", name, file=sys.stderr)
           if not re_name.match(name):
             name = ""
           if stripped:
              guessed = True
              #info("{!r}: Guessed {!r} from {!r}".format(register_name, name, description))
        else:
            name = ""
        return name, matched_field_name_good, guessed

def parse_Register(rspec, field_word_count = 1):
    register_name, (register_meta, register_header), register_fields = rspec
    if register_header[0:1] != ['Bit'] or "Default/Hex" not in register_header:
        warning("{!r}: Unknown 'register' header {!r}, fields {!r}".format(register_name, register_header, register_fields))
        return None
    bits = []
    default_value = 0
    default_mask = 0
    for register_field in register_fields:
        # FIELD ['3 ', 'R/W ', '0x0 ', 'RMD_EN  Ramp Manual Down Enable  0: Disabled  1: Enabled ']
        while len(register_field) < len(register_header):
            register_field.append("")
        while len(register_field) > len(register_header):
            s = register_field[-1]
            del register_field[-1]
            register_field[-1] = register_field[-1] + " " + s
        if register_header == ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']:
            # FIXME: Provide access_method parameter and choose which ACCESS to use
            bitrange, access, access2, default_part, description = register_field
        else:
            bitrange, access, default_part, description = register_field
        if access.strip() == "/": # no access
            #info("{!r}: Field {!r} cannot be accessed".format(register_name, register_field))
            continue
        parts = bitrange.split(":")
        if len(parts) == 2:
            max_bit, min_bit = parts
            try:
                max_bit = int(max_bit.strip())
                min_bit = int(min_bit.strip())
            except ValueError:
                warning("{!r}: Invalid field {!r}: Bitrange error".format(register_name, register_field))
                continue
            if max_bit < min_bit: # bug
              if max_bit == 15 and min_bit == 18: # reg HCCPARAMS in A64
                max_bit, min_bit = min_bit, max_bit
              elif max_bit == 0 and min_bit > 10: # work around A64 bug
                max_bit, min_bit = min_bit, max_bit
              else:
                error("{!r}: Invalid field {!r}: Bitrange error".format(register_name, register_field))
        elif len(parts) != 1:
            warning("Field could not be parsed as a bitrange: {!r}".format(parts))
            continue
        else:
            max_bit, min_bit = parts[0], parts[0]
            try:
                max_bit = int(max_bit.strip())
                min_bit = int(min_bit.strip())
            except ValueError:
                warning("{!r}: Invalid field {!r}: Bitrange error".format(register_name, register_field))
                continue
        default_part = default_part.strip().rstrip(".")
        default_part = default_part.split("(")[0] # strip description
        if default_part.strip() in ["/", "None", "UDF", ""]:
            pass
        else:
            try:
                try:
                  if default_part.startswith("0x"):
                      default_part = default_part[len("0x"):]
                  default_part = int(default_part, 16)
                  if default_part < 2**(max_bit - min_bit + 1):
                      default_mask |= (2**(max_bit - min_bit + 1) - 1) << min_bit
                      default_value |= default_part << min_bit
                  else:
                      warning("{!r}: Default {} for field {!r} does not fit into slot with bitrange {}:{}".format(register_name, default_part, register_field, max_bit, min_bit))
                except ValueError:
                  warning("{!r}: Default {!r} for field {!r} was not understood".format(register_name, default_part, register_field))
            except (NameError, SyntaxError):
                error("{!r}: Could not parse default value {!r}".format(register_name, default_part))
                import traceback
        guessed = False
        name, matched_field_name_good, guessed = field_name_from_description(description, field_word_count)
        if name.lower().strip() in ["reserved", "revered"] or name.lower().strip().startswith("reserved") or name.strip() == "/": # sic
            continue
        elif re_name.match(name):
            pass
        elif not name or name.strip() == "/" or re_definitely_not_name.match(name) or name.lower().strip() in ["one", "remote", "00b", "writes", "per-port", "power", "that", "end", "no", "causing", "is", "1:", "32k", "0x0", "0x1", "upsample", "en", "of", "at", "implemented"]:
            #warning("{!r}: Field name could not be determined: {!r} (tried: {!r}".format(register_name, register_field, name))
            if field_word_count < 6:
                return parse_Register(rspec, field_word_count = field_word_count + 1)
            else:
                warning("{!r}: Field name could not be determined: {!r} (tried: {!r})".format(register_name, register_field, name))
                #if register_name.strip().startswith("BUS_SOFT_RST_REG3"):
                #  import pdb
                #  pdb.set_trace()
                continue
        else:
            name = "" # assert re_name.match(name), name
        name = name.replace(".", "_") # XXX shouldn't svd2rust do that?
        name = "_{}".format(name)
        if any(name.endswith("_{}".format(x.upper())) for x in connectives): # field name cannot end in a connective
          # we assume there will be more words following on the next call of parse_Register
          name = ""
        else:
          name = name[1:]
        if name:
            if name.endswith("_SETTING"): # what else would it be?
                name = name[:-len("_SETTING")]
            if guessed:
                name = "*{}".format(name)
                #info("{!r}: Guessed field name {!r} from {!r}".format(register_name, name, description))
            bits.append(((max_bit, min_bit), name, description, access))
        else:
            if field_word_count < 6:
                return parse_Register(rspec, field_word_count = field_word_count + 1)
            else:
                warning("{!r}: Field names are not all known; for example the one described by: {!r}".format(register_name, description))
    field_names = [name for _, name, _, _ in bits]
    if len(set(field_names)) != len(field_names):
        if field_word_count < 6:
            return parse_Register(rspec, field_word_count = field_word_count + 1)
        else:
            warning("{!r}: Field names are not unique: {!r}".format(register_name, field_names))

    #print("REG {!r}".format(register_name))
    for ((max_bit, min_bit), name, description, access) in bits:
        #print("* ", (max_bit, min_bit), name, access)
        if name.startswith("*"):
          info("{!r}: Guessed field name {!r}".format(register_name, name.lstrip("*")))
    bits = [((max_bit, min_bit), name.lstrip("*"), description, access) for ((max_bit, min_bit), name, description, access) in bits]

    return Register(name = register_name, meta = register_meta, header = register_header, bits = bits, reset_value = default_value, reset_mask = default_mask)

re_N_unicode_range = re.compile(r"N\s*=\s*([0-9])+–([0-9]+)")
re_N_to = re.compile(r"N\s*=\s*([0-9]+) to ([0-9]+)")
re_n_lt = re.compile(r"([0-9]+)<n<([0-9]+)")
re_n_le_lt = re.compile(r"([0-9]+)≤n<([0-9]+)")
re_nN_tilde = re.compile(r"[(]([NnP])=([0-9]+)~([0-9]+)[)]")

def parse_Offset(spec):
    register_offset = spec
    register_offset = re_N_unicode_range.sub(lambda match: "N={}~{}".format(match.group(1), match.group(2)), register_offset)
    register_offset = re_N_to.sub(lambda match: "N={}~{}".format(match.group(1), match.group(2)), register_offset)
    register_offset = re_n_lt.sub(lambda match: "n={}~{}".format(int(match.group(1)) + 1, int(match.group(2)) - 1), register_offset)
    register_offset = re_n_le_lt.sub(lambda match: "n={}~{}".format(int(match.group(1)), int(match.group(2)) - 1), register_offset)
    return register_offset

svd_peripherals = etree.Element("peripherals")
svd_root.append(svd_peripherals)

def pprint2(dnode, indent):
        prefix = indent * " "
        print("{}{}: {!r} (rows = {})".format(prefix, dnode.name, dnode.header, repr(dnode.rows)[:50]))
        #dnode.rows
        for child in dnode.children:
            pprint2(child, indent + 4)

root_dnode = clean_up_input()
#print("QQQ")
#pprint2(root_dnode, 0)

#  registers[module].append((n, header, body))

# CPU_Architecture: ([], ['Item']) (rows = [['Quad-core ARM Cortex', '-A7 Processor ', 'ARMv7)

class Summary(NamedTuple):
    parts: List  # FIXME: Dict
    alternatives: List # FIXME: Dict

re_a_slash_b = re.compile(r"^([A-Za-z]*)([0-9]+)/([0-9]+)$")
def parse_Summary(container, module):
    summary = container
    # Special case for D1: If the MODULE ends in "CCU register list: ", then move that one to the summary instead.
    if len(module.rows[-1]) == 1 and module.rows[-1][0].strip().endswith(" register list:"):
      r = module.rows[-1][0]
      del module.rows[-1]
      summary.rows.insert(0, [r])
    else:
      if len(summary.rows) > 0 and len(summary.rows[0]) == 1 and summary.rows[0][0] != "#": # often, the "#" is missing for the first row.
        summary.rows[0].insert(0, "#")
    module_prefixes = set([row[0].split("_", 1)[0] for row in module.rows if len(row) > 1 and row[0].find("_") != -1])
    # Special case for D1: For the " register list: " cases, infer the names of the peripherals they mean
    for row in summary.rows:
      if len(row) > 0 and row[0].strip().lower() == "analog domain register": # it's not bold--so it cannot be detected by extract.py
        row.insert(0, "#")
      if len(row) == 1 and row[0].strip().endswith(" register list:"):
        n = row[0].strip()[:-len(" register list:")].strip().replace(" ", "_")
        m = re_a_slash_b.match(n)
        p1 = n
        p2 = n
        if m:
          p = m.group(1)
          a = m.group(2)
          b = m.group(3)
          p1 = "{}{}".format(p, a)
          p2 = "{}{}".format(p, b)
        if len(module_prefixes) == 1 and not n.startswith(list(module_prefixes)[0]): # Example: "CSIC"
          module_prefix = list(module_prefixes)[0]
          p1 = "{}_{}".format(module_prefix, p1)
          p2 = "{}_{}".format(module_prefix, p2)
        choices = set([p1, p2])
        row[:] = ["#", ",".join(choices)]
    summary.rows[:] = [r for r in summary.rows if r != []]

    nrows = []
    prefix = ""
    for row in summary.rows:
      if len(row) > 0 and row[0].endswith("_") and len(row[0]) > 15: # ['TCON_CLK_GATE_AND_HDMI_SRC_', 'MSGBOX_WR_INT_THRESHOLD_']: # word wrap
        prefix = row[0]
      elif len(row) > 0 and row[0].endswith("_ENTR") and len(row[0]) > 15:
        prefix = row[0]
      elif len(row) > 0 and row[0].strip() == "CSIC_DMA_BUF_ADDR_FIFO0_ENTR" and len(row[0]) > 15:
        prefix = row[0]
      elif len(row) > 0 and row[0].strip() == "CSIC_DMA_BUF_ADDR_FIFO_CON_R" and len(row[0]) > 15:
        prefix = row[0]
      else:
        nrows.append(["{}{}".format(prefix, row[0])] + row[1:])
        prefix = ""
    summary.rows[:] = nrows
    #print("MODULE", module.rows, file=sys.stderr)
    #print("SUM", summary.rows, file=sys.stderr)

    parts = {}
    #mainkey = ",".join([r[0].strip() for r in module.rows if r[0].strip()])
    mainkey = "ALWAYS"
    part = mainkey
    parts[part] = []
    offsets = []
    for row in summary.rows:
      if len(row) > 0 and row[0].find(" 0x") != -1:
          a, b = row[0].split("0x", 1)
          row.insert(0, a)
          row[1] = b
      while len(row) > 3:
          a = row[-1]
          del row[-1]
          row[-1] = row[-1] + " " + a
      if row[0] == "#":
          part = row[1].strip().upper()
          assert part not in parts, (part, module.rows)
          parts[part] = []
      elif len(row) == 2:
          name, offset = row
          description = name
          offsets.append(offset.strip())
          parts[part].append(tuple(row))
      elif len(row) == 3:
          name, offset, description = row
          offsets.append(offset.strip())
          parts[part].append(tuple(row))
      else:
          if repr(row).find("Reserved") != -1:
            pass
          else:
            assert len(row) == 3, (row, module.rows)
      #print("SUMMARY", row, file=sys.stderr)
    x_mainkey = ",".join([r[0].strip() for r in module.rows if r[0].strip()]).upper()
    if len(parts) == 1 or (x_mainkey in ["Audio Codec".upper(), "AC"] and "Analog domain Register".upper() in parts): # the latter is indirect-access.
      parts[x_mainkey] = parts[mainkey]
      del parts[mainkey]
    if parts.get("mainkey") and len(parts[mainkey]) == 0:
      del parts[mainkey]
    if len(offsets) != len(set(offsets)): # offsets are not unique. That means the entire thing is probably a list of ALTERNATIVES, not parts.
      return Summary(parts = [], alternatives = parts), container
    else:
      return Summary(parts = parts, alternatives = []), container

for module in root_dnode.children:
  prefix, suffix = module.header
  if module.name == "CPU_Architecture":
    svd_cpu = create_cpu(suffix, module.rows)
    svd_root.append(svd_cpu)
    continue

  #print("PERIPH", peripherals)
  container = module
  filters = {}
  if len(container.children) == 1 and container.children[0].header[1] in [['Register_Name', 'Offset', 'Description'], ['Register_Name', 'Offset', 'Register_name'], ['Register_Name', 'Offset', 'Register_Description']]:  # That's a summary.
    container = container.children[0]
    summary, container = parse_Summary(container, module)
    # Note: Possible key: "Analog domain Register", which is not an extra module.
    if summary.alternatives:
      #from pprint import pprint
      #pprint(summary.alternatives, sys.stderr)
      for keys, alternatives in summary.alternatives.items():
        keys = [k.strip() for k in keys.split(",")]
        if len([key for key in keys if key.strip() == "TVD"]) > 0:
          keys.remove("TVD")
          keys.append("TVD0")
          keys.append("TVD1")
          keys.append("TVD2")
          keys.append("TVD3")
        if len([key for key in keys if key.strip() == "UART"]) > 0:
          keys.remove("UART")
          keys.append("UART0")
          keys.append("UART1")
          keys.append("UART2")
          keys.append("UART3")
          keys.append("UART4")
          keys.append("UART5")
          keys.append("UART6")
          keys.append("UART7")
          keys.append("UART8")
          keys.append("UART9")
        if len([key for key in keys if key.strip() == "CSI"]) > 0:
          keys.remove("CSI")
          keys.append("CSI1")
          keys.append("CSI0")
        for key in keys:
          key = key.strip().upper()
          assert key
          #assert key == "ALWAYS" or key == "ANALOG DOMAIN REGISTER" or key in d_peripherals, (key, module.rows)
          assert key not in filters
          filters[key] = set(x[0].strip() for x in alternatives)
      #print("SUM2", filters, file=sys.stderr)
      #from pprint import pprint
      #pprint(summary.alternatives, sys.stderr)
      #sys.exit(1)
    # Skip it for now. FIXME: Handle it.
  assert not (len(container.children) == 1 and container.children[0].header[1] == ['Register_Name', 'Offset', 'Description']), module.rows
  assert suffix == ["Module_Name", "Base_Address"], module.header
  peripherals = [r for r in module.rows if r != []]
  peripherals = [(module_name.strip(), module_baseAddress.replace("(for HDMI)", "")) for module_name, module_baseAddress in peripherals]
  d_peripherals = dict(peripherals)

  module_name, module_baseAddress, *rest = peripherals[0]
  module_name = module_name.strip()
  module_baseAddress = eval(module_baseAddress, {})

  registers_not_in_any_peripheral = set()
  rspecs = []
  for dnode in container.children:
    rspec = dnode.name, dnode.header, dnode.rows
    registers_not_in_any_peripheral.add(dnode.name)
    rspecs.append(rspec)
  for x_module_name, x_module_baseAddress, *rest in peripherals:
    x_module_name = x_module_name.strip()
    #if x_module_name == "CSI0":
    #  import pdb
    #  pdb.set_trace()
    try:
      x_module_baseAddress = eval(x_module_baseAddress, {})
    except (ValueError, SyntaxError, NameError):
      warning("FIXME IMPLEMENT {}".format(x_module_name))
      continue
    svd_peripheral = create_peripheral(x_module_name, x_module_baseAddress, access="read-write", description=None, groupName=None) # FIXME ??
    svd_peripherals.append(svd_peripheral)
    if x_module_name != module_name and len(filters) == 0: # the peripherals are equal to each other
      svd_peripheral.attrib["derivedFrom"] = module_name
    else:
      svd_registers = etree.Element("registers")
      svd_peripheral.append(svd_registers)

      #rspecs = container.children

      common_loop_var, common_loop_min, common_loop_max = None, None, None

      registers = [x for x in [parse_Register(rspec) for rspec in rspecs] if x]
      #print("FILTERS", filters, file=sys.stderr)
      for register in registers:
          #print("FILTERS", filters.keys())
          if len(filters) > 0 and register.name not in filters[x_module_name.upper()]:
            info("Filtered out register {!r} because {!r}.{!r} is not supposed to be in this alterantive.".format(register.name, module_name, register.name))
            continue
          assert len(register.meta) == 1
          register_offset = register.meta[0]
          assert(register_offset.startswith("Offset:"))
          try:
              register_offset = parse_Offset(register_offset)
              nN_match = re_nN_tilde.search(register_offset)
              if nN_match:
                  before_part, loop_var, loop_min, loop_max, after_part = re_nN_tilde.split(register_offset)
                  loop_min = int(loop_min)
                  loop_max = int(loop_max)
                  register_offset = before_part
                  if (common_loop_var, common_loop_min, common_loop_max) == (None, None, None):
                      common_loop_var, common_loop_min, common_loop_max = loop_var, loop_min, loop_max
                  if (common_loop_var, common_loop_min, common_loop_max) != (loop_var, loop_min, loop_max):
                      warning("{!r}: Inconsistent peripheral array (skipping the entire thing): ({!r}, {!r}, {!r}) vs ({!r}, {!r}, {!r})".format(register.name, loop_var, loop_min, loop_max, common_loop_var, common_loop_min, common_loop_max))
                      continue
              else:
                  loop_min = 0
                  loop_max = 0
              # Note: can contain N, n
              spec = register_offset
              for N in range(loop_min, loop_max + 1):
                  register_offset = eval(spec[len("Offset:"):].strip(), {"n": N, "N": N})
          except (SyntaxError, NameError, TypeError):
              warning("Offset is too complicated: {!r}".format(register_offset))
              import traceback
              traceback.print_exc()
              continue
          svd_register = create_register(register, register.name, register_offset, register_description=None) # FIXME: description
          svd_registers.append(svd_register)
          if register.name in registers_not_in_any_peripheral:
            registers_not_in_any_peripheral.remove(register.name)
          #if register.name + "_REG" in registers_not_in_any_peripheral: # R40... sigh
          #  registers_not_in_any_peripheral.remove(register.name + "_REG")

  if len(registers_not_in_any_peripheral) > 0:
    # TODO: if there is exactly one filter for all the peripherals, add these registers anyway
    warning("{!r}: Registers not used in any peripheral: {!r}".format(module.rows, sorted(list(registers_not_in_any_peripheral))))

sys.stdout.flush()
et.write(sys.stdout.buffer, pretty_print=True)
sys.stdout.flush()
