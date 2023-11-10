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

def create_element_and_text(name, value):
    result = etree.Element(name)
    result.text = value
    return result

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
  elif suffix == ['Bit', 'Read/Write', 'Default/HEX', 'Description', 'HCD', 'HC']: 
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']  
  elif suffix == ['Bit', 'Read/Write', 'Default', 'Description', 'HCD', 'HC']: 
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

  if len(body) > 0 and len(body[-1]) > 0 and body[-1][-1].strip().endswith("register list:"): # D1 sometimes puts "... register list:" right into the previous module-decl.
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
      row[1] = row[1].strip()
      continue
    while len(row) >= 1 and row[0] == " ":
      del row[0]
    if len([x for x in row if x == " "]) > 0:
      nrow = []
      for i, x in enumerate(row):
          if len(nrow) >= len(suffix):
            nrow.append(x)
          elif x != " " or (len(nrow) == len(suffix) - 2): #pass " " to Default/Hex field
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
      if len(row) == 0:
        continue
      warning("Table formatting in PDF is unknown: header={!r}, row={!r}".format(header, row))
  return module, header, body

def unroll_Module(module):
  header = module.header
  body = module.rows
  prefix, header = header
  assert header == ["Module_Name", "Base_Address"], header
  base = None
  if len([1 for Module_Name, Base_Address in body if Module_Name.strip().endswith(" OFFSET")]) == len(body) - 1:
      for Module_Name, Base_Address in body:
        if not Module_Name.strip().endswith(" OFFSET"):
            base = eval(Base_Address, {})
            break
  for Module_Name, Base_Address in body:
    Module_Name = Module_Name.strip()
    Base_Address = Base_Address.replace("(for HDMI)", "").strip()
    Base_Address = eval(Base_Address.strip(), {})
    if Module_Name.endswith(" OFFSET"):
      Base_Address = base + Base_Address
      Module_Name = Module_Name.replace(" OFFSET", "").strip()
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
# Here will be: <cpu> with: <name>, <revision>, <endian>little</endian>, <mpuPresent>, <fpuPresent>, <nvicPrioBits>, <vendorSystickConfig>

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

def create_cluster(name, addressOffset):
    cluster = etree.Element("cluster")
    name_node = etree.Element("name")
    name_node.text = name
    cluster.append(name_node)
    addressOffset_node = etree.Element("addressOffset") # it is mandatory
    addressOffset_node.text = "0x{:x}".format(addressOffset)
    cluster.append(addressOffset_node)
    return cluster

def create_register_reference(name, addressOffset, ref_name):
  result = etree.Element("register")
  result.attrib["derivedFrom"] = ref_name
  register_name = name
  result.append(text_element("name", name))
  result.append(text_element("addressOffset", "0x{:X}".format(addressOffset)))
  return result

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
    modifiedWriteValues = {
            "R/WC": "clear",
            "WC": "clear",
            #"WAC": "clear", # after operation FINISHED--not necessarily directly after a Write.
            #"R/WAC": "clear", # after operation FINISHED--not necessarily directly after a Write.
            "R/W1C": "oneToClear",
            "R/W1S": "oneToSet",
            "R/W0C": "zeroToClear",
    }.get(access_raw.replace(" ", "").strip())
    readAction = {
            "RC": "clear",
            "RC/W": "clear",
    }.get(access_raw.replace(" ", "").strip())
    field.append(text_element("description", description))
    field.append(text_element("bitRange", "[{}:{}]".format(max_bit, min_bit)))
    if access:
      field.append(text_element("access", access))
    if modifiedWriteValues:
        field.append(text_element("modifiedWriteValues", modifiedWriteValues))
    if readAction:
        field.append(text_element("readAction", readAction))
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
re_field_name_good = re.compile(r"^(([0-9]*[A-Z][A-Z0-9]*_[A-Z0-9./_-]+[a-zA-Z0-9./_-]*|[0-9]*[A-Z][A-Z0-9./_-]+|[0-9]*[A-Z][a-z][A-Za-z]*_[A-Z][A-Za-z_]+)(\[[0-9]+(:[0-9]+)?\])?)[ .]")

connectives = set(["a", "the", "has", "is", "are", "includes", "the", "to", "for", "largest", "between", "because", "how", "whether", "indicates", "specifies", "by", "when", "of", "contains", "initiate", "related", "if", "affected", "dedicated", "support", "and"])
nouns = set(["threshold", "peak", "coefficient", "rms", "receive", "transmit", "gain", "smooth", "filter", "signal", "average", "attack", "sustain", "decay", "hold", "release", "size", "count", "enable", "mode", "time", "channel", "noise"])

re_a_of_the_b = re.compile(r"^([A-Z]+)_OF_THE_([A-Z_]+)$")
field_name_whitelist = {"2D", "3D", "RemoteWakeupEnable", "BulkListEnable", "ControlListEnable", "PeriodicListEnable", "PortSuspendStatusChange", "PortEnableStatusChange", "(read)PortEnableStatus", "OverCurrentIndicatorChang", "Frame List Size", "Run/Stop", "00: HV(Sync+DE)", "00: Copying is permitted", "Hsync detect window end time for corase detect", "Hsync detect window start time for coarse detection"}

def field_name_from_description(description, field_word_count):
        """ Returns the field name extracted from a description.  Returns the empty string if that cannot be done.
            Also returns whether the match was very good, and whether the match was very bad. """
        matched_field_name_good = False
        guessed = False
        if description:
           description = description.replace("_ ", "_") # "TF_ DRQ_EN"
           #if description.find("DRQ_EN") != -1:
           #  import pdb
           #  pdb.set_trace()
           q = description.split(". ")[0].split(",")[0]
           if field_word_count == 1 or field_word_count == 6:
               m = re_field_name_good.match("{} ".format(q))
               if m: # FOO_BAR
                   matched_field_name_good = True
                   q = m.group(1)
                   description = description.lstrip()
                   if description.startswith(q + ".") or description.startswith(q + " "):
                     description = description[len(q) + 1:].lstrip()
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
               return "", False, False, description
           #    q.append(r[0])
           #    del r[0]
           #    if r == []:
           #        break
           #    words = r
           #    while len(words) > 0 and words[0] in ["the", "a", "an"]:
           #        del words[0]
           #    q.append(words[0])
           #    del r[0]
           name = "_".join([w for w in q if w[0].upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" or any(" ".join(q).startswith(x) for x in field_name_whitelist) or re_num_al_name.match(w)]) or ""
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
           m = re_a_of_the_b.match(name)
           if m:
             a = m.group(1)
             b = m.group(2)
             name = "{}_{}".format(b, a)
           if stripped:
              guessed = True
              #info("{!r}: Guessed {!r} from {!r}".format(register_name, name, description))
        else:
            name = ""
        return name, matched_field_name_good, guessed, description

def parse_Register(rspec, field_word_count = 1):
    register_name, (register_meta, register_header), register_fields = rspec
    if register_header[0:1] != ['Bit'] or "Default/Hex" not in register_header:
        # FIXME: warning("{!r}: Unknown 'register' header {!r}, fields {!r}".format(register_name, register_header, register_fields))
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
        if len([x for x in register_field if x]) == 0 or [x.strip() for x in register_field if x] == ["Bit"]:
            continue
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
              elif max_bit == 0 and min_bit == 1: # work around R40 bug
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
        name, matched_field_name_good, guessed, description = field_name_from_description(description, field_word_count)
        if name.lower().strip() in ["reserved", "revered"] or name.lower().strip().startswith("reserved") or name.strip() == "/": # sic
            continue
        elif re_name.match(name):
            pass
        elif not name or name.strip() == "/" or re_definitely_not_name.match(name) or name.lower().strip() in ["one", "remote", "00b", "writes", "per-port", "power", "that", "end", "no", "causing", "is", "1:", "32k", "0x0", "0x1", "upsample", "en", "of", "at", "implemented"]:
            #warning("{!r}: Field name could not be determined: {!r} (tried: {!r}".format(register_name, register_field, name))
            if field_word_count < 6:
                return parse_Register(rspec, field_word_count = field_word_count + 1)
            else:
                if description.strip() != "/":
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

re_N_unicode_range = re.compile(r"[(]([NnPx])\s*=\s*([0-9])+\s*–\s*([0-9]+)[)]")
re_N_to = re.compile(r"[(]N\s*=\s*([0-9]+) to ([0-9]+)[)]")
re_n_lt = re.compile(r"[(]([0-9]+)<n<([0-9]+)[)]")
re_n_le_lt = re.compile(r"[(]([0-9]+)≤n<([0-9]+)[)]")
re_nN_tilde = re.compile(r"[(]([NnPx])\s*=\s*([0-9]+)~([0-9]+)[)]")
re_n_range = re.compile(r"[(]([NnPx])\s*=\s*([0-9, ]+)[)]")
re_direct_range = re.compile(r"\s*(0x[0-9A-Fa-f]+)\s*[~–]\s*(0x[0-9A-Fa-f]+)\s*$")
re_spaced_hex = re.compile(r"(0x[0-9A-Fa-f ]+)")
re_verbose_range = re.compile(r"[(]([NnPx]) from ([0-9]+) to ([0-9]+)[)]")

def parse_Offset1(register_offset):
    register_offset = re_spaced_hex.sub(lambda match: match.group(1).replace(" ", ""), register_offset)
    register_offset = re_direct_range.sub(lambda match: "{} + N*4(N={})".format(match.group(1), ",".join(map(str, range(0, (eval(match.group(2), {}) + 4 - eval(match.group(1), {})) // 4)))), register_offset)
    register_offset = re_nN_tilde.sub(lambda match: "({}={})".format(match.group(1), ",".join(map(str, range(int(match.group(2)), int(match.group(3)) + 1)))), register_offset)
    register_offset = re_N_unicode_range.sub(lambda match: "({}={})".format(match.group(1), ",".join(map(str, range(int(match.group(2)), int(match.group(3)) + 1)))), register_offset)
    register_offset = re_N_to.sub(lambda match: "(N={})".format(",".join(map(str, range(int(match.group(1)), int(match.group(2)) + 1)))), register_offset)
    register_offset = re_n_lt.sub(lambda match: "(n={})".format(",".join(map(str, range(int(match.group(1)) + 1, int(match.group(2)))))), register_offset)
    register_offset = re_n_le_lt.sub(lambda match: "(n={})".format(",".join(map(str, range(int(match.group(1)), int(match.group(2)))))), register_offset)
    register_offset = re_verbose_range.sub(lambda match: "({}={})".format(match.group(1), ",".join(map(str, range(int(match.group(2)), int(match.group(3)) + 1)))), register_offset) # description
    return register_offset

def parse_Offset(register):
    assert len(register.meta) == 1, register
    register_offset = register.meta[0]
    assert(register_offset.startswith("Offset:"))
    return parse_Offset1(register_offset)

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

def register_summary_instances_guess(offsetspec, part, module):
    spec = parse_Offset1(offsetspec)
    nN_match = re_n_range.search(spec)
    if nN_match:
        before_part, loop_var, loop_indices, after_part = re_n_range.split(spec)
        loop_indices = list(map(int, loop_indices.split(",")))
        for i in loop_indices:
            offset = eval(before_part, {loop_var: i})
            yield offset
    else:
        if offsetspec.find("Reserved") == -1:
            # Guess; TODO: Check suffix on description ("(x:1~7)") instead.
            eval_env = {"N": 0, "n": 0, "P": 0, "x": 0, part: 0}
            for module_name, module_baseAddress in unroll_Module(module):
                eval_env[module_name] = module_baseAddress
                eval_env[module_name.rstrip("0")] = module_baseAddress
            try:
                yield eval(spec, eval_env)
            except Exception as e:
                raise

re_ts_relative_offset_0 = re.compile(r"^(TS[A-Z]*)\s*[+]\s*(0x)?0+") # A64

re_a_slash_b = re.compile(r"^([A-Za-z]*)([0-9]+)/([0-9]+)$")
def parse_Summary(container, module):
    summary = container
    # Special case for D1: If the MODULE ends in "CCU register list: ", then move that one to the summary instead.
    if len(module.rows) > 0 and len(module.rows[-1]) == 1 and module.rows[-1][0].strip().endswith(" register list:"):
      r = module.rows[-1][0]
      del module.rows[-1]
      summary.rows.insert(0, [r])
    else:
      if len(summary.rows) > 0 and len(summary.rows[0]) == 1 and summary.rows[0][0] != "#": # often, the "#" is missing for the first row.
        summary.rows[0].insert(0, "#")
    module_prefixes = set([row[0].split("_", 1)[0] for row in module.rows if len(row) > 1 and row[0].find("_") != -1])
    # Special case for D1: For the " register list: " cases, infer the names of the peripherals they mean
    for row in summary.rows:
      if len(row) > 0 and row[0].find(" _") != -1:
        row[0] = row[0].replace(" _", "_") # R40
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
      if len(row) > 1:
        if row[0] == "#":
          row[1] = row[1].strip()
        m = re_ts_relative_offset_0.match(row[1])
        if m:
          section = m.group(1).strip()
          if len(nrows) == 0 or ["#", section] not in nrows: # check for dupes
            nrows.append(["#", section]) # for A64, which sometimes misses the section headers...
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
    assert prefix == "", "no leftover"
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
      #if part == "CSI1" and len(row) > 0 and row[0].startswith("CSI1_") and row[0].find("_C0") == -1:
      #    assert False, row
      if len(row) > 0 and row[0].find(" 0x") != -1:
          a, b = row[0].split("0x", 1)
          b = "0x{}".format(b)
          row.insert(0, a)
          row[1] = b
      if len(row) > 1 and row[1].find("  ") != -1 and len(row[1]) > 10: # and row[1].strip().endswith(" Register"): # column 1 shouldn't have the description, but does (bug in PDF)
          a, b = row[1].split("  ")
          row[1] = a
          if len(row) < 3:
            row.append("")
          row[2] = "{}{}".format(b, row[2])
      while len(row) > 3:
          a = row[-1]
          del row[-1]
          row[-1] = row[-1] + " " + a
      if row == ["TVD_TOP"] or row == ["TVD0 "]: # D1s User Manual: They forget to make those section headers bold or in any other way mark them. But since it's unlikely to have those one-column rows otherwise, special-case them.
          part = row[0]
          assert part not in parts, (part, module.rows)
          parts[part] = []
      elif row[0] == "#":
          part = row[1].strip().upper()
          assert part not in parts, (part, module.rows)
          parts[part] = []
      elif len(row) == 2:
          name, offsetspec = row
          description = name
          for offset in register_summary_instances_guess(offsetspec, part, module):
            offsets.append(offset)
          parts[part].append(tuple(row))
      elif len(row) == 3:
          name, offsetspec, description = row
          for offset in register_summary_instances_guess(offsetspec, part, module):
            offsets.append(offset)
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
    if len(offsets) != len(set(offsets)): # offsets are not unique. That means the entire thing is probably a list of ALTERNATIVES, not parts. # TODO: Find better criteria.
      return Summary(parts = [], alternatives = parts), container
    else:
      if "ALWAYS" in parts and len(parts["ALWAYS"]) == 0:
        del parts["ALWAYS"]

      return Summary(parts = parts, alternatives = []), container

def complete_input_clusters(input_clusters, subcluster_offsets):
  # If there is an offset specified in SUBCLUSTER_OFFSETS for a INPUT_CLUSTER we do not have,
  # Then make the INPUT_CLUSTER more useful by extending its entry by the instances
  # whose names start with the respective cluster name.
  additions = []
  removals = set()
  for a,_ in subcluster_offsets:
    a = a.strip().upper()
    #print("SUBA", a, input_clusters.keys(), file=sys.stderr)
    if a not in input_clusters:
      q = a
      while len(q) > 0 and q[-1] in "0123456789":
        q = q[:-1]
      if q != a:
        assert q in input_clusters, (q, a, input_clusters.keys())
        r = input_clusters[q]
        additions.append((a, r))
        removals.add(q)
  for r in removals:
    del input_clusters[r]
  for a, b in additions:
    input_clusters[a] = b
  #print("SUBA2", input_clusters.keys(), file=sys.stderr)
  return input_clusters

def calculate_increments(items):
    reference = None
    dimIncrements = []
    for item in items:
        if reference is None:
             reference = item
        dimIncrement = item - reference
        reference = item
        dimIncrements.append(dimIncrement)
    return dimIncrements[1:]

for module in root_dnode.children:
  prefix, suffix = module.header
  if module.name == "CPU_Architecture":
    svd_cpu = create_cpu(suffix, module.rows)
    svd_root.insert(svd_root.index(svd_root.find("licenseText")) + 1, svd_cpu)
    continue

  container = module
  filters = {}
  summary = None
  module_names = [module_name.strip() for module_name, *_ in module.rows]
  if len(container.children) == 1 and container.children[0].header[1][:3] in [['Register_Name', 'Offset', 'Description'], ['Register_Name', 'Offset', 'Register_name'], ['Register_Name', 'Offset', 'Register_Description']]:  # That's a summary.
    descriptions = {} # register name -> register description
    container = container.children[0]
    if len(container.header[1]) >= 3 and container.header[1][-1].endswith("Description"):
      ncolumns = len(container.header[1])
      for row in container.rows:
        if len(row) >= ncolumns:
          rname, rdescr = row[0].strip(), row[ncolumns - 1].strip()
          descriptions[rname] = rdescr
    summary, container = parse_Summary(container, module)

    # Note: Possible key: "Analog domain Register", which is not an extra module.
    if summary.alternatives:
      #from pprint import pprint
      #pprint(summary.alternatives, sys.stderr)
      for keys, alternatives in summary.alternatives.items():
        keys = [k.strip() for k in keys.split(",")]
        if len([key for key in keys if key.strip() == "TVD"]) > 0:
          keys.remove("TVD")
          for m in module_names:
            if m.startswith("TVD") and not m.startswith("TVD_"):
              keys.append(m)
        if len([key for key in keys if key.strip() == "UART"]) > 0:
          assert False
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
        #if len([key for key in keys if key.strip() == "CSI"]) > 0:
        #  assert False
        #  keys.remove("CSI")
        #  keys.append("CSI1")
        #  keys.append("CSI0")
        if len([key for key in keys if key.strip() == "TVE"]) > 0: # FIXME check that we have a module like that.
          keys.remove("TVE")
          for m in module_names:
            if m.startswith("TVE") and not m.startswith("TVE_"):
              keys.append(m)
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
  assert not (len(container.children) == 1 and container.children[0].header[1][:3] == ['Register_Name', 'Offset', 'Description']), module.rows
  assert suffix == ["Module_Name", "Base_Address"], module.header
  peripherals = [r for r in module.rows if r != []]
  if len(peripherals) == 0:
    warning("peripherals are empty for module {!r}".format(module))
    continue
  subcluster_offsets = [(module_name.strip()[:-len(" OFFSET")], eval(module_baseAddress, {})) for module_name, module_baseAddress in peripherals if module_name.strip().endswith(" OFFSET")]
  peripherals = [(module_name.strip(), module_baseAddress.replace("(for HDMI)", "")) for module_name, module_baseAddress in peripherals if not module_name.strip().endswith(" OFFSET")]
  # This can be used to introduce extra eval variables.
  d_peripherals = dict(peripherals)
  eval_env = dict(subcluster_offsets)

  def infer_register_instance_structure(visible_registers, x_module_name):
      offsets = {} # register name -> offset_spec
      common_vars_registers = {None: dict()} # {[common var]: {register name: [register offset]}}; all registers of VISIBLE_REGISTERS will show up somewhere
      # FIXME: LEDC_FIFO_DATA_X has 32 elements, but all the other LEDC fields don't. So it should actually NOT generalize. Instead, we have to support arrays of one register...
      # Alternatively, we could support some kind of fallback for the non-groupable registers (like foo[] at the end of a struct).
      for register in visible_registers:
          #if register.name == "LEDC_CTRL_REG":
          #   import pdb
          #   pdb.set_trace()
          try:
              spec = parse_Offset(register)
              offsets[register.name] = register.meta[0]
              # TODO: just call register_summary_instances_guess or something
              nN_match = re_n_range.search(spec)
              if nN_match:
                  before_part, loop_var, loop_indices, after_part = re_n_range.split(spec, maxsplit=1)
              else:
                if description := descriptions.get(register.name):
                  before_part = spec
                  description = parse_Offset1(description)
                  nN_match = re_n_range.search(description)
                if not nN_match and "n" in spec.split(" ")[1]:
                  try: # Try to get bitfield expand formula from description field. V3s
                    description = register.bits[0][2]
                    before_part = spec
                    description = parse_Offset1(description)
                    nN_match = re_n_range.search(description)
                    if nN_match: #store in meta for futher processing
                       register.meta[0] += " " + nN_match.string[nN_match.string.find("("):nN_match.string.find(")") + 1]
                  except:
                    pass  
                if nN_match:
                  _, loop_var, loop_indices, after_part = re_n_range.split(description, maxsplit=1)
              if nN_match:
                  #warning("{!r}: range match".format(register.name))
                  loop_indices = list(map(int, loop_indices.split(",")))
                  spec = before_part
                  offsets[register.name] = spec
                  key = tuple([tuple([loop_var, tuple(loop_indices)])])
                  assert loop_var in ["N", "n", "x"]
                  nN_match2 = re_n_range.search(after_part)
                  qloop_var = None
                  qloop_indices = None, None
                  if nN_match2 is not None:
                      _, qloop_var, qloop_indices, qafter_part = re_n_range.split(after_part, maxsplit=1)
                      if qloop_var == loop_var: #V3s CE_KEY[n] for example
                         warning("{!r}: qloop_var value mismatch. Skipping".format(register.name))
                         qloop_var = None
                         qloop_indices = None
                      else:
                        assert re_n_range.search(qafter_part) is None
                        qloop_indices = list(map(int, qloop_indices.split(",")))
                        key = tuple([tuple([loop_var, tuple(loop_indices)]), tuple([qloop_var, tuple(qloop_indices)])])
                  if key not in common_vars_registers:
                      common_vars_registers[key] = {}
                  assert register.name not in common_vars_registers[key]
                  common_vars_registers[key][register.name] = []
                  # Note: can contain N, n
                  for N in loop_indices:
                      eval_env[loop_var] = N
                      if qloop_var is not None: # second loop variable (P)
                          assert qloop_var == "P" and loop_var == "N" # just in case
                          eval_env[qloop_var] = 1 # P index will be handled later
                          qregister_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                          eval_env[qloop_var] = 0 # P index will be handled later
                          register_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                          # Hardcoded at another spot, too.
                          assert qregister_offset - register_offset == 4, (register_offset, qregister_offset)
                      register_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                      common_vars_registers[key][register.name].append(register_offset)
              else:
                  key = None
                  assert register.name not in common_vars_registers[key]
                  # Remove all math variables
                  while len([x for x in eval_env.keys() if len(x) == 1]) > 0:
                    eval_env.pop([x for x in eval_env.keys() if len(x) == 1][0], 0)
                  # TODO: It should be possible to support arrays somehow. Those definitely can have a + N * b or something--which should NOT be shrunk
                  register_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                  offsets[register.name] = spec # not sure # do this only after the eval succeeded
                  common_vars_registers[key][register.name] = []
                  common_vars_registers[key][register.name].append(register_offset)
          except (SyntaxError, NameError, TypeError):
              warning("Offset is too complicated: {!r}".format(spec))
              import traceback
              traceback.print_exc()
              raise
              #return {}, offsets
      if len(common_vars_registers) > 1:
          for common_vars, registers in common_vars_registers.items():
              info("{!r}: Register block: {!r}: {!r}".format(x_module_name, common_vars, registers))
      return common_vars_registers, offsets

  module_name, module_baseAddress, *rest = peripherals[0]
  module_name = module_name.strip()
  module_baseAddress = eval(module_baseAddress, eval_env)

  registers_not_in_any_peripheral = set()
  rspecs = []
  need_CSI1_fixup = False
  for dnode in container.children:
    if dnode.name == "CSI1_F2_BUFB_REG": # (R40) representant
      # TODO: ensure that the filters already have the correct name
      need_CSI1_fixup = True
      rspec = "CSI1_C0_F2_BUFB_REG", dnode.header, dnode.rows
    else:
      rspec = dnode.name, dnode.header, dnode.rows
    if len(filters) > 0: # is there any filtering going on? # only then do we care about the outcome of the filtering.
      registers_not_in_any_peripheral.add(dnode.name)
    rspecs.append(rspec)
  if need_CSI1_fixup: # R40 sometimes has the (slightly) wrong names in the summary for CSI1.
    v0 = filters["CSI1"]
    replacements = []
    for item in v0:
      if len([n for n,h,r in rspecs if n == item]) == 0:
        if len([n for n,h,r in rspecs if n == item.replace("CSI1_", "CSI1_C0_")]) > 0:
          #if item.find("BUF_CTL_REG") != -1:
          #  import pdb
          #  pdb.set_trace()
          replacements.append((item, item.replace("CSI1_", "CSI1_C0_")))
    for a,b in replacements:
      v0.remove(a)
      v0.add(b)
  registers = [x for x in [parse_Register(rspec) for rspec in rspecs] if x]
  if len(registers) == 0:
    error("{!r}: No registers found.".format(module_name))

  def all_filters_equal(filters):
    items = list(filters.items())
    if len(items) == 0:
      return True
    k0, v0 = items[0]
    for k, v in items:
      if v != v0:
        return False
    return True
  def workaround_unsummarized_registers():
    if len(filters) == 1 or (len(filters) > 1 and all_filters_equal(filters)):
      added = set()
      for main_key, visible_registers in filters.items():
        for register in registers:
          if register.name not in visible_registers:
            # Note: We could extend this here to find the summary OFFSET that has the same offset as the REGISTER.
            added.add("{!r}: Automatically adding register {!r} even though it's not mentioned in the summary (note: this is working around a bug in the PDF)".format(peripherals, register.name))
            visible_registers.add(register.name)
      for msg in added:
        info(msg)
  workaround_unsummarized_registers()

  for x_module_name, x_module_baseAddress, *rest in peripherals:
    x_module_name = x_module_name.strip()
    #if x_module_name == "CSI0":
    #  import pdb
    #  pdb.set_trace()
    try:
      x_module_baseAddress = eval(x_module_baseAddress, eval_env)
    except (ValueError, SyntaxError, NameError):
      warning("FIXME IMPLEMENT {}".format(x_module_name))
      continue
    svd_peripheral = create_peripheral(x_module_name, x_module_baseAddress, access="read-write", description=None, groupName=None) # TODO: groupName ??
    svd_peripherals.append(svd_peripheral)
    if x_module_name != module_name and len(filters) == 0: # the peripherals are equal to each other
      svd_peripheral.attrib["derivedFrom"] = module_name
    else:
      svd_registers = etree.Element("registers")
      svd_peripheral.append(svd_registers)

      visible_registers = {}
      for register in registers:
        if len(filters) == 0 or register.name in filters[x_module_name.upper()]:
          assert register.name not in visible_registers
          visible_registers[register.name] = register

      # TODO: Here, maybe figure out how to unroll all the register instances.
      # The subset of the registers that are kept by the alternative filter is the important subset.
      """
      The structure is:

      alternatives
        clusters (parts)
          instances (new; derived from the offset expressions of the visible_registers; there are at least two dimensions (N and P))
            registers
      """

      # TODO: Do that for each cluster, somehow, instead.
      # ^ common_vars_registers: {[common var]: {register name: [register offset]}}
      #if (common_loop_var, common_loop_indices) == (None, None):
      #  continue

      input_clusters = summary.parts if summary and len(summary.parts) > 0 and len(summary.alternatives) == 0 else []
      svd_clusters_by_register = {} # register -> [cluster]; if register shows in multiple clusters, that means there are two modules of it, and it shows once for each of those modules. This direction is useful in order to easily derive one register from the other. Otherwise, it's quite annoying.
      #svd_clusters = [] # [(svd_cluster, registers)]
      # Add <cluster> nodes.
      registers_not_in_any_cluster = set(visible_registers.keys())
      def process_register_block(cluster_visible_registers, svd_cluster):
          common_vars_registers, simplified_offsets = infer_register_instance_structure(cluster_visible_registers, x_module_name)
          doneregs = set()
          for loop_spec, registers_and_offsets in common_vars_registers.items():
              if loop_spec:
                  (loop_var, loop_indices), *rest_loop = loop_spec
                  lowest_offset = 2**32
                  if len(registers_and_offsets) < 2: # not worth it
                      continue
                  common_increment = None
                  for rname, offsets in registers_and_offsets.items():
                      assert len(offsets) == len(loop_indices), rname
                      if min(offsets) < lowest_offset:
                        lowest_offset = min(offsets)
                      increments = calculate_increments(offsets)
                      assert len(set(increments)) == 1, rname
                      increment = increments[0]
                      if common_increment is None:
                        common_increment = increment
                  if len(rest_loop) > 0:
                      [(qloop_var, qloop_indices)] = rest_loop
                      assert list(qloop_indices) == list(range(len(qloop_indices)))
                      assert qloop_var == "P"
                  else:
                      qloop_var = None
                      qloop_indices = None, None
                  # Make svd_cluster under svd_cluster, with [%s] and dimIndex etcetc, stash all the registers_and_offsets in there
                  if list(loop_indices) == list(range(len(loop_indices))): # 0..N-1
                    cname = "_{}{}[%s]".format(loop_var, qloop_var or "")
                    array = True
                  else:
                    cname = "_{}{}_%s".format(loop_var, qloop_var or "")
                    array = False
                  svd_loop_cluster = create_cluster(cname, lowest_offset)
                  # TODO: assert root.find("dim") is None and root.find("dimIncrement") is None and root.find("dimIndex") is None, path_string(root)
                  # Decide between "{}[%s]" withOUT dimIndex, or "{}_%s" WITH dimIndex
                  if not array:
                    svd_loop_cluster.insert(0, create_element_and_text("dimIndex", ",".join(map(str, loop_indices))))
                  svd_loop_cluster.insert(0, create_element_and_text("dimIncrement", str(common_increment)))
                  svd_loop_cluster.insert(0, create_element_and_text("dim", str(len(loop_indices))))
                  svd_cluster.append(svd_loop_cluster)
                  for rname, offsets in registers_and_offsets.items():
                      offsets = sorted(offsets)
                      register_offset = offsets[0] - lowest_offset
                      register = visible_registers[rname]
                      register_name = register.name
                      if len(rest_loop) > 0:
                          assert register_name.find("%s") == -1
                          register_name = "{}[%s]".format(register_name)
                      svd_register = create_register(register, register_name, register_offset, register_description=descriptions.get(register.name))
                      if len(rest_loop) > 0:
                          svd_register.insert(0, create_element_and_text("dimIncrement", "4")) # TODO: Remove hardcoding
                          svd_register.insert(0, create_element_and_text("dim", str(len(qloop_indices))))
                      svd_loop_cluster.append(svd_register)
                      doneregs.add(register.name)

          for register in cluster_visible_registers:
              if register.name in doneregs:
                  continue
              if register.name not in simplified_offsets:
                  warning("{!r}: Register {!r} has a too-complicated offset ({!r}). Skipping".format(module.rows, register.name, register.meta[0]))
                  continue
              register_offsets = []
              spec = simplified_offsets[register.name]
              increments = []
              try:
                increment = None
                dim = None
                rspec = register.name
                for rn in [x for x in eval_env.keys() if len(x) == 1]:
                    del eval_env[rn]
                lowest_register_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                register_offsets.append(lowest_register_offset)
              except (SyntaxError, NameError, TypeError):
                spec = parse_Offset(register)
                nN_match = re_n_range.search(spec)
                register_offsets = []
                if nN_match:
                  spec, loop_var, loop_indices, after_part = re_n_range.split(spec)
                  loop_indices = list(map(int, loop_indices.split(",")))
                  for N in loop_indices:
                    eval_env["N"] = N
                    eval_env["n"] = N
                    register_offset = eval(spec[len("Offset:"):].strip(), eval_env)
                    register_offsets.append(register_offset)
                  register_offsets = list(sorted(register_offsets))
                  lowest_register_offset = register_offsets[0]
                  increments = calculate_increments(register_offsets)
                  if len(set(increments)) == 1 and list(loop_indices) == list(range(len(loop_indices))):
                     increment = min(increments)
                     array = True
                     rspec = "{}[%s]".format(register.name)
                  else:
                     array = False
                     if len(set(increments)) == 1:
                         rspec = "{}_%s".format(register.name)
                         increment = min(increments)
                     else: # weird special case for ONE register in R40, TCON_CEU_COEF_MUL_REG: Gap in dimIndex
                         assert len(set(increments)) > 1, register.name
                         rspec = "{}_{}".format(register.name, loop_indices[0])
                         primary_rspec = rspec
                         svd_register = create_register(register, rspec, lowest_register_offset, register_description=descriptions.get(register.name))
                         svd_cluster.append(svd_register)
                         assert len(register_offsets) == len(loop_indices), register.name
                         for register_offset, N in list(zip(register_offsets, loop_indices))[1:]:
                             rspec = "{}_{}".format(register.name, N)
                             svd_cluster.append(create_register_reference(rspec, register_offset, primary_rspec))
                         if register.name in registers_not_in_any_peripheral:
                             registers_not_in_any_peripheral.remove(register.name)
                         if register.name in registers_not_in_any_cluster:
                            registers_not_in_any_cluster.remove(register.name)
                         continue
                  dim = len(register_offsets)
                else:
                  warning("{!r}: Offset2 is too complicated: {!r}, {!r}".format(register.name, spec, register.meta))
                  continue
              svd_register = create_register(register, rspec, lowest_register_offset, register_description=descriptions.get(register.name))
              if increment is not None:
                  if not array:
                      svd_register.insert(0, create_element_and_text("dimIndex", ",".join(map(str, loop_indices))))
                  svd_register.insert(0, create_element_and_text("dimIncrement", str(increment)))
                  svd_register.insert(0, create_element_and_text("dim", str(len(loop_indices))))
              # TODO: svd_cluster.append(create_register_reference("{}_{}".format(cluster_name, register.name), register_offset, register.name))
              svd_cluster.append(svd_register)
              if register.name in registers_not_in_any_peripheral:
                registers_not_in_any_peripheral.remove(register.name)
              if register.name in registers_not_in_any_cluster:
                registers_not_in_any_cluster.remove(register.name)

      ## For making the program extract single registers
      #if x_module_name == "TCON_LCD0":
      #    keys = ["TCON0_FRM_TAB_REG"] #, "HcRhStatus_Register", "USBCMD"]
      #    chosen_registers = [register for register in registers if register.name in keys]
      #    assert len(chosen_registers) == len(keys)
      #    import pdb
      #    pdb.set_trace()
      #    process_register_block(chosen_registers, svd_registers)
      #    continue
      #else:
      #    continue

      if input_clusters and len(input_clusters) >= 2: # this avoids creating clusters like "TWI0,TWI1,TWI2,TWI3" inside TWI2.
        input_clusters = complete_input_clusters(input_clusters, subcluster_offsets)
        for input_cluster_name, input_cluster_members in sorted(input_clusters.items()):
          eval_env[input_cluster_name] = 0 # since we grouped it, don't offset twice!
          # Make a more general env var (TSF1 -> TSF)
          q = input_cluster_name
          while len(q) > 0 and q[-1] in "0123456789":
              q = q[:-1]
          eval_env[q] = 0
          addressOffset = 0
          # Find addressOffset to use for this, if any
          for a,b in subcluster_offsets:
            if a.strip().upper() == input_cluster_name.upper():
              addressOffset = b
              break
          svd_cluster = create_cluster(input_cluster_name, addressOffset)
          svd_registers.append(svd_cluster) # FIXME: dupe?

          input_cluster_member_keys = set([x[0].strip() for x in input_cluster_members])
          cluster_visible_registers = [v for k, v in visible_registers.items() if k in input_cluster_member_keys]
          process_register_block(cluster_visible_registers, svd_cluster)
      # Remaining globals
      global_registers = [v for k, v in visible_registers.items() if k in registers_not_in_any_cluster]
      process_register_block(global_registers, svd_registers)

      #FIXME: assert len(registers_not_in_any_cluster) == 0, registers_not_in_any_cluster

      # Remove empty clusters
      removals = set()
      for node in svd_registers:
        if node.tag == "cluster":
          if len([a.find("name").text for a in node if a.tag not in ["name", "addressOffset", "dimIndex", "dim", "dimIncrement"]]) == 0:
            removals.add(node)
      for r in removals:
        warning("{!r}: Removing cluster {!r} since it's empty".format(module.rows, r.find("name").text))
        svd_registers.remove(r)

  if len(registers_not_in_any_peripheral) > 0:
    warning("{!r}: Registers not used in any peripheral: {!r}".format(module.rows, sorted(list(registers_not_in_any_peripheral))))

sys.stdout.flush()
et.write(sys.stdout.buffer, pretty_print=True)
sys.stdout.flush()
