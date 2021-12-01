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
  if suffix == ['Bit', 'Read/Write', 'Default/Hex', 'Description', 'HCD', 'HC']:
    suffix = ['Bit', 'Read/Write HCD', 'Read/Write HC', 'Default/Hex', 'Description']

  header = (prefix, suffix)
  while body[0:1] == [[]] or body[0:1] == [[" "]]:
    del body[0]
  access_possibilities = ["R/W1C", "R/W", "R", "W", "/"]
  for row in body:
    while row[-1:] == [" "] or row[-1:] == ["CCU register list: "]:
      del row[-1]
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
      row[len(row) - 2] = row[len(row) - 2] + " " + s
      del row[len(row) - 1]
    if len(row) != len(suffix):
      warning("Table formatting in PDF is unknown: module={!r}, header={!r}, row={!r}".format(module, header, row))
  while body[-1:] == [[]] or body[-1:] == [[' ']]:
     del body[-1]
  return module, header, body

def unroll_instances(module):
  _, header, body = module
  prefix, header = header
  assert header == ["Module_Name", "Base_Address"]
  #print("BODY", body, file=sys.stderr)
  for Module_Name, Base_Address in body:
    Module_Name = Module_Name.strip()
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
  if module:
    #print("MOD", n, module, file=sys.stderr)
    module_module, module_header, module_body = module
    module_module = None # clean tree
    module = clean_table(module_module, module_header, module_body, n)
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

svd_peripherals = etree.Element("peripherals")
svd_root.append(svd_peripherals)

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

svd_peripherals_by_path = {}

def create_register(table_definition, name, addressOffset, description=None):
  result = etree.Element("register")
  register_name = name
  result.append(text_element("name", name))
  result.append(text_element("description", description or name))
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
    # TODO: enumeratedValues, enumeratedValue
    fields.append(field)
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
re_name = re.compile(r"[0-9]*[A-Z_]+|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en")
re_name_read = re.compile(r"^[(]read[)]([0-9]*[A-Z_a-z]+|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en)$")
re_name_write = re.compile(r"^[(]write[)]([0-9]*[A-Z_a-z]+|bist_en_a|vc_addr|vc_di|vc_clk|bist_done|vc_do|resume_sel|wide_burst_gate|flip_field|hyscale_en)$")
def parse_Register(rspec):
    register_name, (register_meta, register_header), register_fields = rspec
    if register_header[0:1] != ['Bit'] or "Default/Hex" not in register_header:
        warning("{!r}: Unknown 'register' header {!r}".format(register_name, register_header))
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
        if default_part.strip() in ["/", "None", "UDF", ""]:
            pass
        else:
            try:
                default_part = eval(default_part, {})
                if default_part < 2**(max_bit - min_bit + 1):
                    default_mask |= (2**(max_bit - min_bit + 1) - 1) << min_bit
                    default_value |= default_part << min_bit
                else:
                    warning("{!r}: Default {} for field {!r} does not fit into slot with bitrange {}:{}".format(register_name, default_part, register_field, max_bit, min_bit))
            except (NameError, SyntaxError):
                error("{!r}: Could not parse default value {!r}".format(register_name, default_part))
                import traceback
        if description:
            name = description.replace("hyscale en", "hyscale_en").split()[0] or ""
            name = name.rstrip(".").rstrip(",").rstrip()
            name = name.replace("(Read)", "(read)")
            m = re_name_read.match(name)
            if m: # "(read)A" vs "(write)B"
              name = "{}_R".format(m.group(1))
            m = re_name_write.match(name)
            if m: # "(read)A" vs "(write)B"
              name = "{}_W".format(m.group(1))
        else:
            name = ""
        if re_name.match(name):
            pass
        elif not name or name.strip() == "/" or re_definitely_not_name.match(name) or name.strip() in ["one", "remote", "00b", "writes", "per-port", "power", "that", "end", "no", "causing", "is", "1:", "reserved", "32k", "0x0", "0x1", "upsample", "en"]:
            warning("{!r}: Field name could not be determined: {!r}".format(register_name, register_field))
            continue
        else:
            assert re_name.match(name), name
        name = name.replace(".", "_") # XXX shouldn't svd2rust do that?
        bits.append(((max_bit, min_bit), name, description, access))

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

for module, rspecs in registers.items():
  module = eval(module, {})
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
      svd_register = create_register(register, register.name, register_offset, description=None) # FIXME: description
      svd_registers.append(svd_register)

sys.stdout.flush()
et.write(sys.stdout.buffer, pretty_print=True)
sys.stdout.flush()
