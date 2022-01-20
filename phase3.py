#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import re
import sys
from logging import debug, info, warning, error, critical
import logging
logging.basicConfig(level=logging.INFO)

from lxml import etree

import phase2_result
from pprint import pprint

del phase2_result.Module_List

re_enum = re.compile(r"^[0-9xA-F]+: ")

#phase2_result__names

def clean_table(module, header, body, name):
  prefix = []
  suffix = []
  for item in header:
    if item.find(":") != -1:
      prefix.append(item.strip())
    else:
      for x in item.replace("Module Name", "Module_Name").replace("Base Address", "Base_Address").split():
        suffix.append(x)
  if suffix == ['Bit', 'Read/Write', 'Default/Hex', 'Description'] and len(body) >= 1 and body[0] == ["HCD ", "HC "]: # R40 bug in HcInterruptStatus
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']
    del body[0]
  elif suffix == ['Bit', 'Read/Write', 'Default/Hex', 'Description', 'HCD', 'HC']:
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']

  header = (prefix, suffix)
  while body[0:1] == [[]] or body[0:1] == [[" "]]:
    del body[0]
  for row in body:
    while row[-1:] == [" "] or row[-1:] == ["CCU register list: "]:
      del row[-1]
  while body[-1:] == [[]] or body[-1:] == [[' ']]:
     del body[-1]
  if module is None:
      return module, header, body
  access_possibilities = ["R/W1C", "R/W", "R", "W", "/"]
  for row in body:
    if row == []:
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
      warning("Table formatting in PDF is unknown: module={!r}, header={!r}, row={!r}".format(module, header, row))
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

registers = {}

for n in dir(phase2_result):
  if n.startswith("__"):
    continue
  try:
    module, header, body = getattr(phase2_result, n)
  except ValueError:
    continue
  except TypeError:
    continue
  #if not module: # A64
  #  module = "unsorted", ["Module_Name", "Base_Address"], [["x", "0"]] # FIXME
  if module:
    module_module, module_header, module_body = module
    module_module = None # clean tree
    module = clean_table(module_module, module_header, module_body, n)
    module_module, module_header, module_body = module
    if module_header[1] != ["Module_Name", "Base_Address"]: # those are not supported
      continue
    module = dict([(k, v) for k, v in unroll_instances(module)])
  value = clean_table(module, header, body, n)
  setattr(phase2_result, n, value)
  module, header, body = value
  module = repr(module)
  if module not in registers:
    registers[module] = []
  registers[module].append((n, header, body))

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
  q = meaning.split()
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
        if s.endswith("_no") or s.endswith("_not") or s.endswith("_is") or s.endswith("_between") or s.endswith("_with") or s.endswith("_without") or s.endswith("_will") or s.endswith("_always") or s.endswith("_don’t") or s.endswith("_must") or s.endswith("_a") or s.endswith("_use") or s.endswith("_the") or s.endswith("do"):
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
            if meaning.strip().lower() in ["reserved", "revered"]: # sic
              continue
            variant_name = generate_enumeratedValue_name(n, meaning or n, parts = counter)
            if variant_name is None:
              warning("register {!r} field {!r} enum variants are not unique. Giving up.".format(register_name, name))
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
              if max_bit == 0 and min_bit > 10: # work around A64 bug
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
                  default_part = int(default_part, 16)
                  if default_part < 2**(max_bit - min_bit + 1):
                      default_mask |= (2**(max_bit - min_bit + 1) - 1) << min_bit
                      default_value |= default_part << min_bit
                  else:
                      warning("{!r}: Default {} for field {!r} does not fit into slot with bitrange {}:{}".format(register_name, default_part, register_field, max_bit, min_bit))
                except ValueError:
                  warning("{!r}: Default {} for field {!r} was not understood".format(register_name, default_part, register_field))
            except (NameError, SyntaxError):
                error("{!r}: Could not parse default value {!r}".format(register_name, default_part))
                import traceback
        guessed = False
        if description:
           words = description.split(". ")[0].replace(" is set by hardware to ", " ").replace(" by HC to ", " to ").replace(" to point to ", " to ").replace(" to enable or disable ", " ").replace(" to enable/disable ", " ").replace(" by HCD ", " ").replace(" when HC ", " ").replace(" is set by an OS HCD ", " ").replace(" is set by HCD ", " ").replace(" is set by HC ", " ").replace(" content of ", " ").replace("hyscale en", "hyscale_en").split("\n", 1)[0].split()
           stripped = False
           while len(words) > 0 and words[0] in ["This", "field", "bit", "is", "are", "set", "to", "indicates", "indicate", "specifies", "specify", "how", "describes", "determines", "used", "whether", "there", "any", "the", "a", "an", "value", "which", "loaded", "into", "The", "the", "that", "specifies", "by", "when", "of", "contains", "byte", "implemented", "incremented", "immediately", "initiated", "initiate"]:
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
           name = "_".join(words[0:field_word_count]) or ""
           name = name.rstrip(".").rstrip(",").rstrip(":").rstrip()
           name = name.replace("(Read)", "(read)")
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
        else:
            name = ""
        if name.lower().strip() in ["reserved", "revered"]: # sic
            continue
        elif re_name.match(name):
            pass
        elif not name or name.strip() == "/" or re_definitely_not_name.match(name) or name.lower().strip() in ["one", "remote", "00b", "writes", "per-port", "power", "that", "end", "no", "causing", "is", "1:", "32k", "0x0", "0x1", "upsample", "en", "of", "at", "implemented"]:
            #warning("{!r}: Field name could not be determined: {!r} (tried: {!r}".format(register_name, register_field, name))
            if field_word_count < 5:
                return parse_Register(rspec, field_word_count = field_word_count + 1)
            else:
                warning("{!r}: Field name could not be determined: {!r} (tried: {!r}".format(register_name, register_field, name))
                continue
        else:
            name = "" # assert re_name.match(name), name
        name = name.replace(".", "_") # XXX shouldn't svd2rust do that?
        name = "_{}".format(name)
        if name.endswith("_A") or name.endswith("_THE") or name.endswith("_HAS") or name.endswith("_ARE") or name.endswith("_INCLUDES") or name.endswith("_THE") or name.endswith("_TO") or name.endswith("_FOR") or name.endswith("_OF") or name.endswith("_NOT") or name.endswith("_THE") or name.endswith("_LARGEST") or name.endswith("_BETWEEN"):
          # we assume there will be more words following on the next call of parse_Register
          name = ""
        else:
          name = name[1:]
        if name:
            if guessed:
                name = "*{}".format(name)
                #info("{!r}: Guessed field name {!r} from {!r}".format(register_name, name, description))
            bits.append(((max_bit, min_bit), name, description, access))
        else:
            if field_word_count < 5:
                return parse_Register(rspec, field_word_count = field_word_count + 1)
            else:
                warning("{!r}: Field names are not all known; for example the one described by: {!r}".format(register_name, description))
    field_names = [name for _, name, _, _ in bits]
    if len(set(field_names)) != len(field_names):
        if field_word_count < 5:
            return parse_Register(rspec, field_word_count = field_word_count + 1)
        else:
            warning("{!r}: Field names are not unique: {!r}".format(register_name, field_names))

    for ((max_bit, min_bit), name, description, access) in bits:
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

for module, rspecs in registers.items():
  module = eval(module, {})
  if module is None: # for example CPU Architecture!
     for a_name,a_header,a_body in rspecs:
       if a_name == "CPU_Architecture":
         a_prefix, a_suffix = a_header
         svd_cpu = create_cpu(a_suffix, a_body)
         svd_root.append(svd_cpu)
     continue
  peripherals = sorted(module.items())
  module_name, module_baseAddress = peripherals[0]

  #print("MOD {}: ".format(module), end=" QQ ")
  #print()
  svd_peripheral = create_peripheral(module_name, module_baseAddress, access="read-write", description=None, groupName=None) # FIXME ??
  svd_peripherals.append(svd_peripheral)
  for x_module_name, x_module_baseAddress in peripherals[1:]:
    svd_x_peripheral = create_peripheral(x_module_name, x_module_baseAddress, access="read-write", description=None, groupName=None) # FIXME ??
    svd_x_peripheral.attrib["derivedFrom"] = module_name
    svd_peripherals.append(svd_x_peripheral)

  svd_registers = etree.Element("registers")
  svd_peripheral.append(svd_registers)

  common_loop_var, common_loop_min, common_loop_max = None, None, None
  registers = [x for x in [parse_Register(rspec) for rspec in rspecs] if x]
  for register in registers:
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

sys.stdout.flush()
et.write(sys.stdout.buffer, pretty_print=True)
sys.stdout.flush()
