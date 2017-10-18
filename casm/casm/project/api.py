import ctypes
import glob
import json
import os
from distutils.spawn import find_executable
from os.path import dirname, join
from sys import platform

import sh

class API(object):
  """
  Class to provide access to the libccasm C API.

  Acts like a singleton by loading libcasm and libccasm into a class member the
  first time (and only the first time) that a new API instance is constructed.

  Each API instance uses the same shared class member to make calls.
  """
  class __API(object):
    """
    Hidden class of which there will be only one instance

    Attributes
    ----------

      lib_casm: ctypes.CDLL
        Handle to libcasm.*

      lib_ccasm: ctypes.CDLL
        Handle to libccasm.*

    """
    def __init__(self):
      """Loads dynamic libraries"""
      
      try:
          casm_path = find_executable('casm')
          if platform == 'darwin':
              libcasm_path = sh.grep(sh.otool('-L', casm_path), 'libcasm').split()[0]
              libcasm_path = libcasm_path.replace('@loader_path', dirname(casm_path))
          else:
              libcasm_path = sh.grep(sh.ldd(casm_path), 'libcasm').split()[2]
          libccasm_path = libcasm_path.replace('libcasm', 'libccasm')
          
          self.lib_casm = ctypes.CDLL(libcasm_path, mode=ctypes.RTLD_GLOBAL)
          self.lib_ccasm = ctypes.CDLL(libccasm_path, mode=ctypes.RTLD_GLOBAL)
      except Exception as e:
          print "Error loading casm libraries"
          casm_path = find_executable('casm')
          print "Find 'casm':", casm_path
          if platform == 'darwin':
              print "Find 'libcasm':"
              print sh.otool('-L', casm_path)
          else:
              print "Find 'libcasm':"
              print sh.ldd(casm_path)
          raise e
      
      #### Argument types

      self.lib_ccasm.casm_STDOUT.restype = ctypes.c_void_p

      self.lib_ccasm.casm_STDERR.restype = ctypes.c_void_p

      self.lib_ccasm.casm_nullstream.restype = ctypes.c_void_p

      self.lib_ccasm.casm_ostringstream_new.restype = ctypes.c_void_p

      self.lib_ccasm.casm_ostringstream_delete.argtypes = [ctypes.c_void_p]
      self.lib_ccasm.casm_ostringstream_delete.restype = None

      self.lib_ccasm.casm_ostringstream_size.argtypes = [ctypes.c_void_p]
      self.lib_ccasm.casm_ostringstream_size.restype = ctypes.c_ulong

      self.lib_ccasm.casm_ostringstream_strcpy.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char)]
      self.lib_ccasm.casm_ostringstream_strcpy.restype = ctypes.POINTER(ctypes.c_char)


      self.lib_ccasm.casm_primclex_new.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
      self.lib_ccasm.casm_primclex_new.restype = ctypes.c_void_p

      self.lib_ccasm.casm_primclex_delete.argtypes = [ctypes.c_void_p]
      self.lib_ccasm.casm_primclex_delete.restype = None

      self.lib_ccasm.casm_primclex_refresh.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool, ctypes.c_bool]
      self.lib_ccasm.casm_primclex_refresh.restype = None

      self.lib_ccasm.casm_capi.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
      self.lib_ccasm.casm_capi.restype = ctypes.c_int

  __api = None

  def __init__(self):
    """
    Acts like a singleton by loading libcasm and libccasm into a class member the
    first time (and only the first time) that a new API instance is constructed.

    Each API instance uses the same shared class member to make calls.
    """
    if API.__api is None:
      API.__api = API.__API()
    return

  def stdout(self):
    """
    Get a pointer to a CASM::Log that writes to std::cout.

    This does not need to be deleted manually.
    """
    return API.__api.lib_ccasm.casm_STDOUT()

  def stderr(self):
    """
    Get a pointer to a CASM::Log that writes to std::cerr

    This does not need to be deleted manually.
    """
    return API.__api.lib_ccasm.casm_STDERR()

  def nullstream(self):
    """
    Get a pointer to a CASM::Log that writes to null.

    This does not need to be deleted manually.
    """
    return API.__api.lib_ccasm.casm_nullstream()

  def ostringstream_new(self):
    """
    Construct a CASM::OStringStreamLog that writes to std::ostringstream.

    Returns
    -------
      ptr: CASM::OStringStreamLog pointer
        Used for capturing CASM output in a string.
        This ptr needs to be deleted manually by using API.ostringstream_delete(ptr)
    """
    return API.__api.lib_ccasm.casm_ostringstream_new()

  def ostringstream_to_str(self, ptr):
    """
    Copy the value of a CASM::OStringStreamLog to a Python string.

    Arguments
    ---------

      ptr: CASM::OStringStreamLog pointer


    Returns
    -------
      s: str
        The contents of a CASM::OStringStreamLog

    """
    c_str = ctypes.create_string_buffer(API.__api.lib_ccasm.casm_ostringstream_size(ptr))
    API.__api.lib_ccasm.casm_ostringstream_strcpy(ptr, c_str)
    return c_str.value

  def ostringstream_delete(self, ptr):
    """
    Delete a CASM::OStringStreamLog

    Arguments
    ---------

      ptr: CASM::OStringStreamLog pointer

    """
    API.__api.lib_ccasm.casm_ostringstream_delete(ptr)
    return

  def primclex_new(self, path, log, debug_log, err_log):
    """
    Construct a new CASM::PrimClex

    Arguments
    ---------

      path: str
        The path to a CASM project

      log: CASM::Log pointer
        A pointer to a CASM::Log to write standard output

      debug_log: CASM::Log pointer
        A pointer to a CASM::Log to write debug output

      err_log: CASM::Log pointer
        A pointer to a CASM::Log to write error output


    Notes
    -------

    CASM::Log pointers can be obtained from:
      1) API.stdout()
      2) API.stderr()
      3) API.nullstream()
      4) API.ostringstream()


    Returns
    -------
      ptr: CASM::PrimClex pointer

    """
    return API.__api.lib_ccasm.casm_primclex_new(path, log, debug_log, err_log)

  def primclex_refresh(self, ptr, read_settings=False, read_composition=False, read_chem_ref=False, read_configs=False, clear_clex=False):
    """
    Call CASM::PrimClex::refresh to reload PrimClex data from settings files

    Arguments
    ---------

      ptr: CASM::PrimClex pointer

      read_settings: bool, optional, default=False
        If True, read project_settings.json

      read_composition: bool, optional, default=False
        If True, read composition_axes.json

      read_chem_ref: bool, optional, default=False
        If True, read chemical_reference.json

      read_configs: bool, optional, default=False
        If True, read SCEL and config_list.json

      clear_clex: bool, optional, default=False
        If True, clear stored orbitrees, clexulators, and eci


    Note
    ----

      This does not check if what you request will cause problems.

    """
    API.__api.lib_ccasm.casm_primclex_refresh(ptr, read_settings, read_composition, read_chem_ref, read_configs, clear_clex)
    return

  def primclex_delete(self, ptr):
    """
    Delete a CASM::PrimClex

    Arguments
    ---------

      ptr: CASM::PrimClex pointer

    """
    API.__api.lib_ccasm.casm_primclex_delete(ptr)
    return


  def __call__(self, args, primclex, root, log, debug_log, err_log):
    """
    Make an API call

    Arguments
    ---------

      args: str
        A string containing the arguments for the casm command to be executed.

          Ex: "select --set-on -o /abspath/to/my_selection"
          Ex: "query -k 'configname selected' -v -o STDOUT"

      primclex: CASM::PrimClex pointer
        A pointer to a CASM::PrimClex, as obtained from API.primclex_new()

      root: str
        A string giving the path to a root directory of a CASM project, typically
        casm.project.Project.path

      log: CASM::Log pointer
        A pointer to a CASM::Log to write standard output

      debug_log: CASM::Log pointer
        A pointer to a CASM::Log to write debug output

      err_log: CASM::Log pointer
        A pointer to a CASM::Log to write error output


    Notes
    -------

    CASM::Log pointers can be obtained from:
      1) API.stdout()
      2) API.stderr()
      3) API.nullstream()
      4) API.ostringstream()


    Returns
    -------
      returncode: int

        Possible values:

          0: No error

          1: ERR_INVALID_ARG
            Command line input is not valid

          2: ERR_UNKNOWN
            Misc. or Unknown error

          3: ERR_NO_PROJ
            No CASM project can be found in expected location

          4: ERR_INVALID_INPUT_FILE
            An expected input file is invalid

          5: ERR_MISSING_INPUT_FILE
            An expected input file can not be found

          6: ERR_EXISTING_FILE
            A file might be overwritten

          7: ERR_MISSING_DEPENDS
            Requested command can not be performed because some dependency needs
            to be done first (i.e. no basis set, so can't use clexulator)

          8: ERR_OTHER_PROJ
            Unknown attempting to overwrite another CASM project

    """
    return API.__api.lib_ccasm.casm_capi(args, primclex, root, log, debug_log, err_log)

