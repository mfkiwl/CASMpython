import argparse
import json
import os
import os.path
import sys

import numpy as np

from casm.api import casm_capture
from casm.misc import noindent
from casm.project import Project, Selection, query
from casm.project.structure import get_casm_structure_property

# import ase is required at execution

path_help = """
Path to CASM project. Default=current working directory.
"""

# "<CASM_species>": {
#   "chemical_symbol": "O",
#   "charge_state": -2,
#   "magnetic_moment": 1.
# }

def _check_output(stdout, returncode, args):
    if returncode:
        print(stdout)
        raise Exception("Error with '" + args + "'")
    try:
        return json.loads(stdout)
    except:
        print(stdout)
        raise Exception("Error parsing '" + args + "' results")

def write_casm_structure(casm_structure, output_dir, force=False):
    filename = os.path.join(output_dir, "structure.casm.json")

    if os.path.exists(filename) and not force:
        raise Exception("casm convert error: " + filename + " already exists")
    with open(filename, 'w') as f:
        data = noindent.singleline_arrays_json_printable(casm_structure)
        f.write(json.dumps(data, cls=noindent.NoIndentEncoder, indent=2, sort_keys=True))
    return filename


class ASEIntermediary(object):
    """Use ase.Atoms as an intermediary for structure conversion

    Attributes
    ----------

      casm_to_ase_chemical_symbols: dict
        Dict of <casm_atom_type>:<ase_chemical_symbol>. Conversion performed for any casm atom_type found in the dict.

      ase_to_casm_chemical_symbols: dict
        Dict of <casm_atom_type>:<ase_chemical_symbol>. Conversion performed for any casm atom_type found in the dict.

    """

    def __init__(self, casm_to_ase_chemical_symbols={}):
        self.casm_to_ase_chemical_symbols=casm_to_ase_chemical_symbols
        self.ase_to_casm_chemical_symbols={casm_to_ase_chemical_symbols[value]:key for key in casm_to_ase_chemical_symbols}

    def make_structure(self, casm_structure):
        """Convert a CASM structure to an ase.Atoms instance

        Arguments
        ---------
          casm_structure: dict
            A CASM structure

        Notes
        -----

        Currently supports:
        - Set ase `cell` from casm `lattice_vectors`/`lattice` (required)
        - Set ase `chemical_symbols` from casm `atom_types` (required)
        - Set ase `positions`/`scaled_positions` from casm `atom_coords` (required)
        - Set ase `FixScaled` or `FixAtoms` from casm `atom_properties/selectivedynamics/value` (optional)
        - Set ase `initial_magnetic_moments` from casm `atom_properties/<flavor>magspin/value` (optional)
        - Recognizes `atom_properties`, `atom_dofs`, `atom_vals` or `atom_values` as aliases

        Returns
        -------
          ase_structure: ase.Atoms instance
            A structure as an ase.Atoms instance
        """
        import ase

        cell = None
        if "lattice_vectors" in casm_structure:
            cell = casm_structure["lattice_vectors"]
        elif "lattice" in casm_structure:
            cell = casm_structure["lattice"]
        else:
            raise Exception("Error: no `lattice_vectors` or `lattice` found in CASM structure")


        # required - "atom_type" -> "chemical_symbols"
        symbols = [self.casm_to_ase_chemical_symbols.get(x, x) for x in casm_structure["atom_type"]]
        try:
            ase_structure = ase.Atoms(symbols=symbols, cell=cell, pbc=True)
        except KeyError as e:
            print("casm_structure[\"atom_type\"]:", casm_structure["atom_type"])
            print("casm_to_ase_chemical_symbols:", self.casm_to_ase_chemical_symbols)
            print("chemical_symbols:", symbols)
            raise Exception("Error setting ase chemical symbols. Any CASM atom_type that is not an chemical symbol understood by ase must have a conversion listed in a dict given by --chemical_symbols") from e

        # required - "coord_mode","atom_coords" -> "positions"
        coord_mode = casm_structure["coord_mode"]
        casm_coords_are_frac = False
        if coord_mode.lower() == "direct" or coord_mode.lower() == "fractional":
            casm_coords_are_frac = True

        atom_coords = np.array(casm_structure["atom_coords"])
        if casm_coords_are_frac:
            ase_structure.set_scaled_positions(atom_coords)
        else:
            ase_structure.set_positions(atom_coords)

        # optional "magspin" -> "initial_magnetic_moments"
        magspin = get_casm_structure_property(casm_structure, "atom", "magspin")
        if magspin is not None:
            ase_structure.set_initial_magnetic_moments(np.array(magspin))

        # optional "selectivedynamics" -> constraints
        selective_flags = get_casm_structure_property(casm_structure, "atom", "selectivedynamics")
        if selective_flags is not None:
            # begin, code snippet adapted from `ase.io.vasp`
            from ase.constraints import FixAtoms, FixScaled
            constraints = []
            indices = []
            for ind, sflags_float in enumerate(selective_flags):
                sflags = [bool(round(x)) for x in sflags_float]
                if sflags.any() and not sflags.all():
                    constraints.append(FixScaled(atoms.get_cell(), ind, sflags))
                elif sflags.all():
                    indices.append(ind)
            if indices:
                constraints.append(FixAtoms(indices))
            if constraints:
                ase_structure.set_constraint(constraints)
            # end

        return ase_structure

    def make_casm_structure(self, ase_structure):
        """Convert an ase.Atoms instance to a CASM structure

        Arguments
        ---------
          ase_structure: ase.Atoms instance
            A structure as an ase.Atoms instance

        Notes
        -----

        Currently supports:
        - Use ase `cell` for casm `lattice_vectors` (required)
        - Use ase `chemical_symbols` for casm `atom_types` (required)
        - Use ase `scaled_positions`/`positions` for casm `atom_coords` (required)
        - Uses `atom_properties` for storing atom properties

        Todo:
        - Use ase `FixScaled` or `FixAtoms` for casm `atom_properties/selectivedynamics/value` (optional)
        - Use ase `initial_magnetic_moments`/`magnetic_moments` for casm `atom_properties/<flavor>magspin/value` (optional)

        Returns
        -------
          casm_structure: dict
            A CASM structure
        """
        casm_structure = dict()
        casm_structure["lattice_vectors"] = ase_structure.cell.tolist()
        casm_structure["coord_mode"] = "Fractional"
        casm_structure["atom_coords"] = ase_structure.get_scaled_positions().tolist()
        casm_structure["atom_types"] = [self.ase_to_casm_chemical_symbols.get(x, x) for x in ase_structure.get_chemical_symbols()]
        return casm_structure

    def read_structure(self, filename, format):
        """Read an ase.Atoms instance from a file in the specified format

        Arguments
        ---------
          filename: str
              The name of the file to be read.

          format: str
            The input structure format. Accepts formats recognized by ase.io.read or "casm" to read a CASM structure file.

        Returns
        -------
          ase_structure: ase.Atoms instance
            A structure as an ase.Atoms instance
        """
        import ase.io
        if format.lower() == "casm":
            # read CASM structure and convert to Atoms
            with open(filename, 'r') as f:
                casm_structure = json.load(f)
            return self.make_structure(casm_structure)
        else:
            return ase.io.read(filename=filename,index=None, format=format)

    def write_structure(self, ase_structure, format, output_dir, force=False):
        """Take an ase.Atoms instance and write to file in requested format

        Arguments
        ---------
          ase_structure: ase.Atoms instance
            A structure as an ase.Atoms instance

        format: str
            The output structure format. Accepts formats recognized by ase.io.write or "casm" to write a CASM structure file.

        output_dir: str
            The directory where the converted structure file will be written. The output file will be named `structure.<ext>`, where `<ext>` is the output format. If format="json", the extension will be "ase.json"; if format="casm", the extension will be "casm.json".

        force: bool (optional, default=False)
            Whether to force overwrite existing files.

        Returns
        -------
            filename: str
                The name of the file.
        """
        import ase.io
        if format == "json":
            ext = "ase.json"
        elif format == "casm":
            ext = "casm.json"
        else:
            ext = format
        filename = os.path.join(output_dir, "structure." + ext)
        if os.path.exists(filename) and not force:
            raise Exception("casm convert error: " + filename + " already exists")
        if format.lower() == "casm":
            casm_structure = self.make_casm_structure(ase_structure)
            filename = write_casm_structure(casm_structure, output_dir, force=force)
        else:
            ase.io.write(filename=filename, images=ase_structure, format=format)

        return filename

    def convert_file(self, input_filename, input_format, output_format, force=False):
        """Use ASE to convert a struture file"""

        # use directory containing input file by default
        output_dir = os.path.dirname(input_filename)

        # make output dir if not existing
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        elif not os.path.isdir(output_dir):
            raise Exception("casm convert error: " + output_dir + " must be a directory")

        ase_structure = self.read_structure(input_filename, input_format)
        output_filename = self.write_structure(ase_structure, output_format, output_dir, force=force)
        return output_filename

def make_parser():
    parser = argparse.ArgumentParser(
        description='Convert between CASM structures and other formats')
    parser.add_argument('--config-selection',
                        help="Selection of configurations to convert",
                        type=str,
                        default="")
    parser.add_argument('--config-names',
                        help="Name of configurations to convert",
                        nargs='*',
                        default=None)
    parser.add_argument('--input',
                        help="CASM structure files to convert",
                        nargs='*',
                        default=None)
    parser.add_argument('--input-format',
                        help="Input file structure format",
                        type=str,
                        default="")
    parser.add_argument('--output-format',
                        help="Output format",
                        type=str,
                        default="")
    parser.add_argument('--force',
                        help="Force write",
                        action="store_true",
                        default=False)
    parser.add_argument('--path', help=path_help, type=str, default=None)
    parser.add_argument('--output-dir',
                        help="Output location. Default is configuration directory for multiple input, or input file location for single structure file input.",
                        type=str,
                        default="")
    parser.add_argument('--chemical-symbols',
                        help="Optional file with JSON dictionary of <casm atom_type>:<ase chemical_symbol> conversions.",
                        type=str,
                        default="")
    return parser

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = make_parser()
    args = parser.parse_args(argv)

    # could imagine an input option to select package used for conversion, then perform check here to see if it is available
    try:
        import ase
        import ase.io
        casm_to_ase_chemical_symbols={}
        if args.chemical_symbols:
            with open(args.chemical_symbols,'r') as f:
                casm_to_ase_chemical_symbols=json.load(f)
        intermediary = ASEIntermediary(casm_to_ase_chemical_symbols)
    except Exception as e:
        raise Exception("`casm convert` requires installation of ASE,\nthe Atomic Simulation Environment: https://wiki.fysik.dtu.dk/ase/about.html.\nInstallation may be as simple as `pip install ase`.") from e


    # if single CASM structure file to convert
    if args.input:
        for input in args.input:
            filename = intermediary.convert_file(os.path.abspath(input), args.input_format, args.output_format, force=args.force)
            print(filename)
            return

    # if querying multiple casm structures to convert:
    if args.path is None:
        args.path = os.getcwd()
    proj = Project(os.path.abspath(args.path))

    output_dir = None
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # use "<root>/training_data/<configname>/<outputname>" by default
        output_dir = proj.dir.configuration_dir("")

    # make output_dir if not existing
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    elif not os.path.isdir(output_dir):
        raise Exception("casm convert error: " + output_dir + " must be a directory")

    # collect casm structures as name:structure pairs
    casm_structures = {}

    if args.config_selection:
        casm_args = "query -k structure -c " + args.config_selection + " -j -o STDOUT"
        stdout, stderr, returncode = casm_capture(casm_args, root=proj.path, combine_output=False)
        data = _check_output(stdout, returncode, casm_args)
        for config in data:
            if config["selected"]:
                casm_structures[config["name"]] = config["structure"]

    if args.config_names:
        config_names_str = " ".join(args.config_names)
        casm_args = "query -k structure -c NONE --confignames " + config_names_str + " -j -o STDOUT"
        stdout, stderr, returncode = casm_capture(casm_args, root=proj.path, combine_output=False)
        data = _check_output(stdout, returncode, casm_args)
        for config in data:
            casm_structures[config["name"]] = config["structure"]

    # convert and write
    for name, casm_structure in casm_structures.items():
        configdir = os.path.join(output_dir, name)
        os.makedirs(configdir, exist_ok=True)
        if args.output_format.lower() == "casm":
            filename = write_casm_structure(casm_structure, configdir, force=args.force)
        else:
            structure = intermediary.make_structure(casm_structure)
            filename = intermediary.write_structure(structure, args.output_format, configdir, force=args.force)
        print(filename)

if __name__ == "__main__":
    try:
        main_cli()
    except Exception as e:
        print(e)